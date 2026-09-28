from datetime import date

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import func, select
from test_domain import candidate

from flowpilot.audit import append_event, verify_chain
from flowpilot.domain import Decision, State
from flowpilot.models import Approval, AuditEvent, Notification, User, Vendor, Workflow
from flowpilot.security import SecretBox
from flowpilot.workflow_service import WorkflowConflict, decide, execute_approved, revise_request

pytestmark = pytest.mark.postgres


def ready_workflow(db):
    box = SecretBox(Fernet.generate_key().decode())
    requester = User(
        email="requester@example.com", name="Requester", role="requester", password_hash="unused"
    )
    approver = User(
        email="approver@example.com", name="Approver", role="approver", password_hash="unused"
    )
    db.add_all([requester, approver])
    db.flush()
    w = Workflow(
        requester_id=requester.id,
        title="Acme onboarding",
        request_ciphertext=box.encrypt("Onboard Acme"),
        idempotency_key="w1",
        request_hash="a" * 64,
        status=State.PENDING_APPROVAL,
        candidate_ciphertext=box.encrypt(candidate().model_dump_json()),
    )
    db.add(w)
    db.flush()
    append_event(
        db,
        w.id,
        event_type="STATE_CHANGED",
        actor_id="system",
        payload={"to": State.PENDING_APPROVAL},
        request_id="test",
    )
    return w, requester, approver, box


def test_audit_chain_is_verifiable_and_redacted(db):
    w, _, _, _ = ready_workflow(db)
    append_event(
        db,
        w.id,
        event_type="TOOL_CALLED",
        actor_id="system",
        payload={"tax_id": "12-3456789", "status": "success"},
        request_id="test",
    )
    events = db.scalars(
        select(AuditEvent).where(AuditEvent.workflow_id == w.id).order_by(AuditEvent.sequence)
    ).all()
    assert verify_chain(events)
    assert events[-1].payload["tax_id"] == "[REDACTED]"
    events[-1].payload = {"status": "tampered"}
    assert not verify_chain(events)
    db.expunge(events[-1])


def test_execution_without_approval_has_no_side_effect(db):
    w, _, _, box = ready_workflow(db)
    with pytest.raises(WorkflowConflict):
        execute_approved(db, w.id, box=box, request_id="test", today=date(2026, 9, 28))
    assert db.scalar(select(func.count()).select_from(Vendor)) == 0


def test_approval_and_replayed_execution_create_one_vendor_and_notification(db):
    w, _, approver, box = ready_workflow(db)
    decide(
        db,
        w.id,
        actor=approver,
        revision=1,
        decision=Decision.APPROVE,
        comment="",
        box=box,
        request_id="test",
        today=date(2026, 9, 28),
    )
    first = execute_approved(db, w.id, box=box, request_id="test", today=date(2026, 9, 28))
    second = execute_approved(db, w.id, box=box, request_id="retry", today=date(2026, 9, 28))
    assert first.id == second.id
    assert w.status == State.COMPLETED
    assert db.scalar(select(func.count()).select_from(Vendor)) == 1
    assert db.scalar(select(func.count()).select_from(Notification)) == 1
    assert verify_chain(
        db.scalars(
            select(AuditEvent).where(AuditEvent.workflow_id == w.id).order_by(AuditEvent.sequence)
        ).all()
    )


def test_stale_revision_cannot_be_approved(db):
    w, _, approver, box = ready_workflow(db)
    with pytest.raises(WorkflowConflict, match="revision"):
        decide(
            db,
            w.id,
            actor=approver,
            revision=2,
            decision=Decision.APPROVE,
            comment="",
            box=box,
            request_id="test",
            today=date(2026, 9, 28),
        )
    assert db.scalar(select(func.count()).select_from(Approval)) == 0


def test_request_changes_and_revision_invalidate_old_extraction(db):
    w, requester, approver, box = ready_workflow(db)
    decide(
        db,
        w.id,
        actor=approver,
        revision=1,
        decision=Decision.REQUEST_CHANGES,
        comment="Update insurance",
        box=box,
        request_id="test",
        today=date(2026, 9, 28),
    )
    assert w.status == State.NEEDS_INFORMATION
    revise_request(
        db,
        w.id,
        actor=requester,
        revision=1,
        request_text="New insurance attached",
        box=box,
        request_id="test",
    )
    assert w.revision == 2
    assert w.candidate_ciphertext is None
    assert w.status == State.CLASSIFYING


def test_approval_revalidates_policy_at_decision_time(db):
    w, _, approver, box = ready_workflow(db)
    with pytest.raises(WorkflowConflict, match="validation"):
        decide(
            db,
            w.id,
            actor=approver,
            revision=1,
            decision=Decision.APPROVE,
            comment="",
            box=box,
            request_id="test",
            today=date(2027, 1, 2),
        )
    assert w.status == State.PENDING_APPROVAL


def test_execution_revalidates_expiry_after_approval(db):
    w, _, approver, box = ready_workflow(db)
    decide(
        db,
        w.id,
        actor=approver,
        revision=1,
        decision=Decision.APPROVE,
        comment="",
        box=box,
        request_id="test",
        today=date(2026, 9, 28),
    )
    result = execute_approved(db, w.id, box=box, request_id="test", today=date(2027, 1, 2))
    assert result is None
    assert w.status == State.NEEDS_MANUAL_REVIEW
    assert db.scalar(select(func.count()).select_from(Vendor)) == 0


def test_requester_cannot_decide_own_workflow(db):
    w, requester, _, box = ready_workflow(db)
    with pytest.raises(PermissionError):
        decide(
            db,
            w.id,
            actor=requester,
            revision=1,
            decision=Decision.APPROVE,
            comment="",
            box=box,
            request_id="test",
            today=date(2026, 9, 28),
        )
    assert w.status == State.PENDING_APPROVAL
