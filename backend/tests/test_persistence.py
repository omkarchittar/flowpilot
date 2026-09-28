import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm.exc import StaleDataError

from flowpilot.models import Approval, AuditEvent, Base, User, Vendor, Workflow

pytestmark = pytest.mark.postgres


def workflow(db):
    user = User(
        email="requester@example.com", name="Requester", password_hash="unused", role="requester"
    )
    db.add(user)
    db.flush()
    row = Workflow(
        requester_id=user.id,
        title="Onboard Acme",
        request_ciphertext="encrypted",
        idempotency_key="request-1",
        request_hash="a" * 64,
    )
    db.add(row)
    db.flush()
    return row


def test_vendor_tax_fingerprint_is_unique(db):
    w = workflow(db)
    db.add(
        Vendor(
            workflow_id=w.id,
            company_name="Acme",
            tax_fingerprint="a" * 64,
            tax_ciphertext="encrypted",
            contact_email="jane@acme.example",
        )
    )
    db.flush()
    db.add(
        Vendor(
            workflow_id=w.id,
            company_name="Alias",
            tax_fingerprint="a" * 64,
            tax_ciphertext="encrypted",
            contact_email="jane@acme.example",
        )
    )
    with pytest.raises(IntegrityError):
        db.flush()


def test_approval_decision_is_unique_per_revision(db):
    w = workflow(db)
    for i in range(2):
        db.add(
            Approval(
                workflow_id=w.id,
                revision=1,
                actor_id=w.requester_id,
                decision="reject",
                comment="Missing requirements",
            )
        )
        if i == 0:
            db.flush()
    with pytest.raises(IntegrityError):
        db.flush()


@pytest.mark.parametrize(
    "operation", ["UPDATE audit_events SET event_type='FORGED'", "DELETE FROM audit_events"]
)
def test_audit_events_are_append_only_even_through_raw_sql(db, operation):
    w = workflow(db)
    event = AuditEvent(
        workflow_id=w.id,
        sequence=1,
        event_type="RECEIVED",
        actor_id=w.requester_id,
        payload={},
        previous_hash="0" * 64,
        event_hash="a" * 64,
        request_id="trace-1",
    )
    db.add(event)
    db.flush()
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text(operation + " WHERE workflow_id=:id"), {"id": w.id})


def test_stale_workflow_update_is_rejected(db):
    w = workflow(db)
    old_version = w.version
    db.execute(text("UPDATE workflows SET version=version+1 WHERE id=:id"), {"id": w.id})
    assert w.version == old_version
    w.title = "Stale overwrite"
    with pytest.raises(StaleDataError):
        db.flush()


def test_unknown_state_is_rejected_by_database(db):
    w = workflow(db)
    w.status = "APPROVED_BY_AI"
    with pytest.raises(IntegrityError):
        db.flush()


def test_table_names_cover_workflow_contract():
    assert {
        "users",
        "sessions",
        "workflows",
        "documents",
        "approvals",
        "audit_events",
        "tool_executions",
        "vendors",
        "notifications",
        "jobs",
    } <= set(Base.metadata.tables)
