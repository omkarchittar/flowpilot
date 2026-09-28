"""Revision-bound approval and idempotent local side effects.

These services require a caller-owned transaction. They never commit halfway through
an approval, side effect or corresponding audit event.
"""

import hashlib
from datetime import date
from time import perf_counter

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from flowpilot.audit import append_event
from flowpilot.domain import (
    Decision,
    Role,
    State,
    VendorCandidate,
    authorize_decision,
    transition,
    validate_vendor,
)
from flowpilot.models import Approval, Job, Notification, ToolExecution, User, Vendor, Workflow
from flowpilot.security import SecretBox


class WorkflowConflict(ValueError):
    pass


def locked_workflow(db: Session, workflow_id: str) -> Workflow:
    row = db.scalar(
        select(Workflow)
        .where(Workflow.id == workflow_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if row is None:
        raise LookupError("Workflow not found")
    return row


def change_state(db: Session, workflow: Workflow, target: State, *, actor_id: str, request_id: str):
    previous = workflow.status
    workflow.status = transition(State(previous), target)
    append_event(
        db,
        workflow.id,
        event_type="STATE_CHANGED",
        actor_id=actor_id,
        payload={"from": previous, "to": target, "revision": workflow.revision},
        request_id=request_id,
    )


def read_candidate(workflow: Workflow, box: SecretBox) -> VendorCandidate:
    if not workflow.candidate_ciphertext:
        raise WorkflowConflict("No extracted vendor data is available")
    return VendorCandidate.model_validate_json(box.decrypt(workflow.candidate_ciphertext))


def duplicate_exists(db: Session, candidate: VendorCandidate, box: SecretBox) -> bool:
    if not candidate.tax_id:
        return False
    return (
        db.scalar(
            select(Vendor.id).where(Vendor.tax_fingerprint == box.fingerprint(candidate.tax_id))
        )
        is not None
    )


def decide(
    db: Session,
    workflow_id: str,
    *,
    actor: User,
    revision: int,
    decision: Decision,
    comment: str,
    box: SecretBox,
    request_id: str,
    today: date,
) -> Workflow:
    workflow = locked_workflow(db, workflow_id)
    if not actor.active:
        raise PermissionError("Account is inactive")
    authorize_decision(
        Role(actor.role), decision, actor_id=actor.id, requester_id=workflow.requester_id
    )
    if workflow.revision != revision:
        raise WorkflowConflict("Workflow revision changed; reload before deciding")
    prior = db.scalar(
        select(Approval).where(Approval.workflow_id == workflow_id, Approval.revision == revision)
    )
    if prior:
        if prior.actor_id == actor.id and prior.decision == decision and prior.comment == comment:
            return workflow
        raise WorkflowConflict("This revision already has a decision")
    if workflow.status != State.PENDING_APPROVAL:
        raise WorkflowConflict("Workflow is not pending approval")
    if len(comment) > 2000:
        raise ValueError("Decision comment exceeds 2000 characters")
    if decision == Decision.APPROVE:
        candidate = read_candidate(workflow, box)
        report = validate_vendor(
            candidate, today=today, duplicate=duplicate_exists(db, candidate, box)
        )
        if not report.ready:
            raise WorkflowConflict("Current validation policy blocks approval")
    db.add(
        Approval(
            workflow_id=workflow.id,
            revision=revision,
            actor_id=actor.id,
            decision=decision,
            comment=comment,
        )
    )
    append_event(
        db,
        workflow.id,
        event_type="APPROVAL_DECISION",
        actor_id=actor.id,
        payload={"decision": decision, "revision": revision},
        request_id=request_id,
    )
    target = {
        Decision.APPROVE: State.EXECUTING,
        Decision.REJECT: State.REJECTED,
        Decision.REQUEST_CHANGES: State.NEEDS_INFORMATION,
    }[decision]
    change_state(db, workflow, target, actor_id=actor.id, request_id=request_id)
    if decision == Decision.APPROVE:
        db.add(
            Job(
                kind="execute_vendor",
                resource_id=workflow.id,
                idempotency_key=f"execute:{workflow.id}:{revision}",
                payload={"revision": revision},
            )
        )
    db.flush()
    return workflow


def revise_request(
    db: Session,
    workflow_id: str,
    *,
    actor: User,
    revision: int,
    request_text: str,
    box: SecretBox,
    request_id: str,
) -> Workflow:
    workflow = locked_workflow(db, workflow_id)
    if not actor.active or (actor.id != workflow.requester_id and actor.role != Role.ADMIN):
        raise PermissionError("Cannot change this workflow")
    if workflow.revision != revision or workflow.status not in {
        State.NEEDS_INFORMATION,
        State.NEEDS_MANUAL_REVIEW,
    }:
        raise WorkflowConflict("Workflow cannot be revised in its current state or revision")
    if not 10 <= len(request_text.strip()) <= 20000:
        raise ValueError("Request must contain 10–20000 characters")
    workflow.revision += 1
    workflow.request_ciphertext = box.encrypt(request_text)
    # request_hash identifies the original submission idempotency key; it must not
    # change when this workflow receives a new revision.
    workflow.candidate_ciphertext = None
    workflow.validation = None
    workflow.model_metadata = {}
    append_event(
        db,
        workflow.id,
        event_type="REQUEST_REVISED",
        actor_id=actor.id,
        payload={"revision": workflow.revision},
        request_id=request_id,
    )
    change_state(db, workflow, State.CLASSIFYING, actor_id=actor.id, request_id=request_id)
    db.add(
        Job(
            kind="process_request",
            resource_id=workflow.id,
            idempotency_key=f"process:{workflow.id}:{workflow.revision}",
            payload={"revision": workflow.revision},
        )
    )
    db.flush()
    return workflow


def execute_approved(
    db: Session, workflow_id: str, *, box: SecretBox, request_id: str, today: date
) -> Vendor | None:
    started = perf_counter()
    workflow = locked_workflow(db, workflow_id)
    existing = db.scalar(select(Vendor).where(Vendor.workflow_id == workflow.id))
    if workflow.status == State.COMPLETED and existing:
        return existing
    if workflow.status != State.EXECUTING:
        raise WorkflowConflict("Workflow is not approved for execution")
    approval = db.scalar(
        select(Approval).where(
            Approval.workflow_id == workflow.id,
            Approval.revision == workflow.revision,
            Approval.decision == Decision.APPROVE,
        )
    )
    if not approval or approval.actor_id == workflow.requester_id:
        raise WorkflowConflict("Current revision has no independent human approval")
    actor = db.get(User, approval.actor_id)
    if not actor or not actor.active or actor.role not in {Role.APPROVER, Role.ADMIN}:
        raise WorkflowConflict("Approver no longer has authority")
    candidate = read_candidate(workflow, box)
    # Serialize the same tax identity across separate workflows before duplicate
    # validation. Uniqueness remains the final database backstop.
    fingerprint = box.fingerprint(candidate.tax_id or "")
    lock_key = int.from_bytes(bytes.fromhex(fingerprint)[:8], "big", signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_key})
    report = validate_vendor(candidate, today=today, duplicate=duplicate_exists(db, candidate, box))
    if not report.ready:
        workflow.validation = report.model_dump(mode="json")
        append_event(
            db,
            workflow.id,
            event_type="EXECUTION_BLOCKED",
            actor_id="system",
            payload={"issue_codes": [issue.code for issue in report.issues]},
            request_id=request_id,
        )
        change_state(
            db, workflow, State.NEEDS_MANUAL_REVIEW, actor_id="system", request_id=request_id
        )
        return None
    vendor = Vendor(
        workflow_id=workflow.id,
        company_name=candidate.company_name,
        tax_fingerprint=fingerprint,
        tax_ciphertext=box.encrypt(candidate.tax_id),
        contact_email=candidate.contact_email,
    )
    db.add(vendor)
    db.flush()
    key = f"vendor:{workflow.id}:{workflow.revision}"
    payload_hash = hashlib.sha256(candidate.model_dump_json().encode()).hexdigest()
    result = {"vendor_id": vendor.id}
    db.add(
        ToolExecution(
            workflow_id=workflow.id,
            revision=workflow.revision,
            tool="create_vendor",
            idempotency_key=key,
            payload_hash=payload_hash,
            result=result,
            duration_ms=int((perf_counter() - started) * 1000),
        )
    )
    append_event(
        db,
        workflow.id,
        event_type="TOOL_CALLED",
        actor_id="system",
        tool="create_vendor",
        payload={**result, "status": "success", "idempotency_key": key},
        request_id=request_id,
    )
    notification_started = perf_counter()
    notification_key = f"notification:{workflow.id}:{workflow.revision}"
    notification = Notification(
        workflow_id=workflow.id,
        recipient_id=workflow.requester_id,
        idempotency_key=notification_key,
        subject="Vendor onboarding completed",
        message=f"{candidate.company_name} is registered and ready for your team.",
    )
    db.add(notification)
    db.flush()
    db.add(
        ToolExecution(
            workflow_id=workflow.id,
            revision=workflow.revision,
            tool="send_notification",
            idempotency_key=notification_key,
            payload_hash=payload_hash,
            result={"notification_id": notification.id, "channel": "in_app"},
            duration_ms=int((perf_counter() - notification_started) * 1000),
        )
    )
    append_event(
        db,
        workflow.id,
        event_type="TOOL_CALLED",
        actor_id="system",
        tool="send_notification",
        payload={"notification_id": notification.id, "channel": "in_app", "status": "success"},
        request_id=request_id,
    )
    change_state(db, workflow, State.COMPLETED, actor_id="system", request_id=request_id)
    db.flush()
    return vendor
