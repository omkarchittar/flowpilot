from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import func, select
from test_extraction import extraction_payload

from flowpilot.config import Settings
from flowpilot.domain import Decision
from flowpilot.intake import accept_request, prepare_attachment
from flowpilot.models import AuditEvent, Job, User, Vendor
from flowpilot.providers import Classification, Extraction, ModelResult, ProviderError, ReviewBrief
from flowpilot.security import SecretBox
from flowpilot.worker import run_once
from flowpilot.workflow_service import decide

pytestmark = pytest.mark.postgres


class Transactions:
    """Real PostgreSQL savepoints preserve isolation from the outer test rollback."""

    def __init__(self, db):
        self.db = db

    @contextmanager
    def transaction(self):
        with self.db.begin_nested():
            yield self.db


class FixtureProvider:
    def __init__(self, kind="vendor_onboarding", confidence=0.99, failures=0):
        self.kind, self.confidence, self.failures = kind, confidence, failures

    def classify(self, request_text):
        if self.failures:
            self.failures -= 1
            raise ProviderError("provider_http_503", retryable=True)
        return ModelResult(
            Classification(request_type=self.kind, confidence=self.confidence),
            "fixture-contract",
            30,
            10,
            2,
            "classify-v1",
        )

    def review_brief(self, context):
        return fixture_review_brief(context)

    def extract(self, sources):
        payload = extraction_payload()
        ids = {
            kind: next(
                (
                    key
                    for key, value in sources.items()
                    if key != "request" and value.startswith(prefix)
                ),
                None,
            )
            for kind, prefix in [
                ("tax", "Tax form"),
                ("insurance", "Insurance certificate"),
                ("bank", "Bank confirmation"),
            ]
        }
        for field in [
            "company_name",
            "tax_id",
            "contact_name",
            "contact_email",
            "insurance_expiration",
        ]:
            payload[field]["source_id"] = ids["tax"]
        payload["documents"] = [
            {**d, "source_id": ids[d["source_id"]]}
            for d in payload["documents"]
            if ids[d["source_id"]]
        ]
        return ModelResult(
            Extraction.model_validate(payload), "fixture-contract", 100, 60, 4, "extract-v1"
        )


def fixture_review_brief(context):
    return ModelResult(
        ReviewBrief(
            assessment=context["assessment"],
            summary="Controlled fixture: review the policy findings and source evidence before any decision.",
            issue_refs=[issue["id"] for issue in context["issues"]],
        ),
        "controlled-review-fixture",
        90,
        35,
        2,
        "review-brief-v1",
    )


@pytest.fixture
def work(db):
    key = Fernet.generate_key().decode()
    box = SecretBox(key)
    users = [
        User(email=email, name=role, password_hash="unused", role=role)
        for email, role in [
            ("requester@example.com", "requester"),
            ("approver@example.com", "approver"),
        ]
    ]
    db.add_all(users)
    db.flush()
    texts = [
        "Tax form. Acme Robotics. 12-3456789. Jane Doe. jane@example.com. 2027-12-31",
        "Insurance certificate for Acme Robotics",
        "Bank confirmation for Acme Robotics",
    ]
    attachments = [
        prepare_attachment(f"{i}.txt", text.encode(), max_bytes=10000)
        for i, text in enumerate(texts)
    ]
    workflow = accept_request(
        db,
        requester_id=users[0].id,
        title="Acme onboarding",
        request_text="Please onboard Acme Robotics.",
        idempotency_key="scenario-1",
        attachments=attachments,
        box=box,
        request_id="test",
    )
    return Transactions(db), Settings(encryption_key=SecretStr(key)), workflow, users[1], box


def test_request_to_approval_to_execution_requires_human_and_leaves_complete_audit(work, db):
    database, settings, workflow, approver, box = work
    assert run_once(database, settings, provider_factory=lambda: FixtureProvider())
    assert workflow.status == "PENDING_APPROVAL"
    assert run_once(database, settings, provider_factory=FixtureProvider)
    assert workflow.review_brief["status"] == "complete"
    assert db.scalar(select(func.count()).select_from(Vendor)) == 0
    tools = set(db.scalars(select(AuditEvent.tool).where(AuditEvent.workflow_id == workflow.id)))
    assert {"extract_document", "validate_vendor", "check_duplicate_vendor"} <= tools
    decide(
        db,
        workflow.id,
        actor=approver,
        revision=1,
        decision=Decision.APPROVE,
        comment="",
        box=box,
        request_id="human",
        today=datetime.now(UTC).date(),
    )
    assert run_once(database, settings, provider_factory=lambda: FixtureProvider())
    assert workflow.status == "COMPLETED"
    assert db.scalar(select(func.count()).select_from(Vendor)) == 1
    assert not run_once(database, settings, provider_factory=lambda: FixtureProvider())


@pytest.mark.parametrize(
    "kind,confidence",
    [
        ("invoice_review", 0.99),
        ("contract_request", 0.99),
        ("unknown", 0.99),
        ("vendor_onboarding", 0.4),
    ],
)
def test_unsupported_or_low_confidence_classification_escalates(work, kind, confidence):
    database, settings, workflow, _, _ = work
    run_once(database, settings, provider_factory=lambda: FixtureProvider(kind, confidence))
    assert workflow.status == "NEEDS_MANUAL_REVIEW"


def test_transient_provider_error_retries_with_auditable_backoff(work, db):
    database, settings, workflow, _, _ = work
    provider = FixtureProvider(failures=1)
    run_once(database, settings, provider_factory=lambda: provider)
    job = db.scalar(select(Job).where(Job.resource_id == workflow.id))
    assert job.status == "queued"
    assert workflow.status == "CLASSIFYING"
    assert job.available_at > datetime.now(UTC)
    job.available_at = datetime.now(UTC)
    db.flush()
    run_once(database, settings, provider_factory=lambda: provider)
    assert workflow.status == "PENDING_APPROVAL"
    events = list(
        db.scalars(select(AuditEvent.event_type).where(AuditEvent.workflow_id == workflow.id))
    )
    assert "RETRY" in events


def test_exhausted_provider_retries_escalate_for_manual_review(work, db):
    database, settings, workflow, _, _ = work
    job = db.scalar(select(Job).where(Job.resource_id == workflow.id))
    job.max_attempts = 1
    db.flush()
    run_once(database, settings, provider_factory=lambda: FixtureProvider(failures=1))
    assert workflow.status == "NEEDS_MANUAL_REVIEW"
    assert job.status == "failed"
