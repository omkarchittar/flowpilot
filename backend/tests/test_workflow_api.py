import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from test_auth import PASSWORD

from flowpilot.models import Document, Job, User, Workflow
from flowpilot.security import SecretBox, hash_password

pytestmark = pytest.mark.postgres


def token(client, email="member@example.com"):
    result = client.post("/api/auth/token", json={"email": email, "password": PASSWORD})
    return {"Authorization": "Bearer " + result.json()["access_token"]}


def configure(client):
    key = Fernet.generate_key().decode()
    from pydantic import SecretStr

    client.app.state.settings.encryption_key = SecretStr(key)
    return SecretBox(key)


def test_atomic_workflow_submission_persists_encrypted_request_documents_and_job(api, db):
    client, _, _ = api
    box = configure(client)
    headers = {**token(client), "Idempotency-Key": "onboard-acme-1"}
    payload = {"title": "Onboard Acme", "request_text": "Please onboard Acme. Tax ID: 12-3456789."}
    files = [("files", ("tax.txt", b"Acme tax form 12-3456789", "text/plain"))]
    response = client.post("/api/workflows", data=payload, files=files, headers=headers)
    assert response.status_code == 201
    result = response.json()
    assert result["status"] == "RECEIVED"
    assert "12-3456789" not in response.text
    row = db.get(Workflow, result["id"])
    assert box.decrypt(row.request_ciphertext) == payload["request_text"]
    document = db.scalar(select(Document).where(Document.workflow_id == row.id))
    assert "12-3456789" not in document.content_ciphertext
    job = db.scalar(select(Job).where(Job.resource_id == row.id))
    assert job.kind == "process_request"
    replay = client.post("/api/workflows", data=payload, files=files, headers=headers)
    assert replay.json()["id"] == row.id
    conflict = client.post(
        "/api/workflows", data={**payload, "title": "Different"}, files=files, headers=headers
    )
    assert conflict.status_code == 409


def test_requester_cannot_access_other_workflow_but_reviewer_can(api, db):
    client, _, _ = api
    configure(client)
    owner = token(client)
    result = client.post(
        "/api/intake",
        headers={**owner, "Idempotency-Key": "request-1"},
        json={"title": "Onboard Acme", "request_text": "Please onboard Acme Robotics."},
    ).json()
    for email, role in [("other@example.com", "requester"), ("reviewer@example.com", "reviewer")]:
        db.add(User(email=email, name=role, role=role, password_hash=hash_password(PASSWORD)))
    db.flush()
    other = token(client, "other@example.com")
    assert client.get("/api/workflows", headers=other).json()["items"] == []
    assert client.get("/api/workflows/" + result["id"], headers=other).status_code == 404
    reviewer = token(client, "reviewer@example.com")
    assert client.get("/api/workflows/" + result["id"], headers=reviewer).status_code == 200
    assert (
        client.get("/api/workflows/" + result["id"] + "/audit", headers=reviewer).json()["verified"]
        is True
    )


def test_api_rejects_role_and_status_injection(api):
    client, _, _ = api
    configure(client)
    response = client.post(
        "/api/intake",
        headers={**token(client), "Idempotency-Key": "attack"},
        json={
            "title": "Attack",
            "request_text": "Please onboard this vendor.",
            "status": "COMPLETED",
            "role": "admin",
        },
    )
    assert response.status_code == 422


def test_missing_encryption_key_fails_explicitly(api):
    client, _, _ = api
    response = client.post(
        "/api/intake",
        headers={**token(client), "Idempotency-Key": "missing-key"},
        json={"title": "New request", "request_text": "Please onboard this vendor."},
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "http_503"


@pytest.mark.parametrize("limit", ["count", "bytes"])
def test_revision_checks_combined_retained_and_new_documents(api, db, limit):
    client, _, _ = api
    configure(client)
    headers = token(client)
    count = 20 if limit == "count" else 1
    content = b"A" * 60
    files = [
        ("files", (f"evidence-{i}.txt", content + str(i).encode(), "text/plain"))
        for i in range(count)
    ]
    result = client.post(
        "/api/workflows",
        headers={**headers, "Idempotency-Key": "revision-limits"},
        data={"title": "Acme", "request_text": "Please onboard Acme."},
        files=files,
    )
    assert result.status_code == 201
    workflow = db.get(Workflow, result.json()["id"])
    workflow.status = "NEEDS_INFORMATION"
    db.flush()
    if limit == "bytes":
        client.app.state.settings.upload_limit_bytes = 100
    response = client.post(
        f"/api/workflows/{workflow.id}/revisions",
        headers=headers,
        data={"revision": 1, "request_text": "Updated onboarding information."},
        files=[("files", ("additional.txt", b"B" * 60, "text/plain"))],
    )
    assert response.status_code == (422 if limit == "count" else 413)
    db.refresh(workflow)
    assert workflow.revision == 1


def test_audit_cursor_returns_every_event_with_verified_page_links(api, db):
    from flowpilot.audit import append_event

    client, _, _ = api
    configure(client)
    headers = token(client)
    result = client.post(
        "/api/intake",
        headers={**headers, "Idempotency-Key": "audit-pagination"},
        json={"title": "Acme", "request_text": "Please onboard Acme."},
    ).json()
    for n in range(5):
        append_event(
            db,
            result["id"],
            event_type="RETRY",
            actor_id="system",
            payload={"attempt": n},
            request_id="test",
        )
    cursor = 0
    sequences = []
    while True:
        page = client.get(
            f"/api/workflows/{result['id']}/audit",
            headers=headers,
            params={"after": cursor, "limit": 2},
        ).json()
        assert page["verified"] is True
        assert page["verification_scope"] == "page"
        sequences.extend(item["sequence"] for item in page["items"])
        if not page["has_more"]:
            break
        cursor = page["next_cursor"]
    assert sequences == list(range(1, 7))


def test_authorized_detail_exposes_persisted_brief_with_provenance(api, db):
    from test_orchestration import FixtureProvider, Transactions

    from flowpilot.worker import run_once

    client, _, _ = api
    configure(client)
    owner = token(client)
    created = client.post(
        "/api/intake",
        headers={**owner, "Idempotency-Key": "brief-api"},
        json={"title": "Review request", "request_text": "Please onboard this fictional vendor."},
    ).json()
    database = Transactions(db)
    run_once(database, client.app.state.settings, provider_factory=FixtureProvider)
    run_once(database, client.app.state.settings, provider_factory=FixtureProvider)
    response = client.get("/api/workflows/" + created["id"], headers=owner)
    brief = response.json()["review_brief"]
    assert brief["status"] == "complete"
    assert brief["result"]["assessment"] == "blocked"
    assert brief["metadata"]["model"] == "controlled-review-fixture"
    assert "request_text" not in brief["context"]
    db.add(
        User(
            email="outsider@example.com",
            name="Other",
            role="requester",
            password_hash=hash_password(PASSWORD),
        )
    )
    db.flush()
    denied = client.get(
        "/api/workflows/" + created["id"], headers=token(client, "outsider@example.com")
    )
    assert denied.status_code == 404 and "review_brief" not in denied.text
