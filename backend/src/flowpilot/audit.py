"""Transactional, sequenced audit events. Call within the state-changing transaction."""

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.orm import Session

from flowpilot.db import new_id, utcnow
from flowpilot.models import AuditEvent, Workflow
from flowpilot.security import redact

GENESIS = "0" * 64


def event_digest(event: AuditEvent) -> str:
    data = {
        "id": event.id,
        "workflow_id": event.workflow_id,
        "sequence": event.sequence,
        "event_type": event.event_type,
        "actor_id": event.actor_id,
        "tool": event.tool,
        "payload": event.payload,
        "previous_hash": event.previous_hash,
        "request_id": event.request_id,
        "created_at": event.created_at.astimezone(UTC).isoformat(),
    }
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def append_event(
    db: Session,
    workflow_id: str,
    *,
    event_type: str,
    actor_id: str,
    payload: dict,
    request_id: str,
    tool: str | None = None,
) -> AuditEvent:
    # This row lock also serializes sequences when separate services emit events.
    workflow = db.scalar(select(Workflow).where(Workflow.id == workflow_id).with_for_update())
    if workflow is None:
        raise ValueError("Workflow not found")
    previous = db.scalar(
        select(AuditEvent)
        .where(AuditEvent.workflow_id == workflow_id)
        .order_by(AuditEvent.sequence.desc())
        .limit(1)
    )
    event = AuditEvent(
        id=new_id(),
        created_at=utcnow(),
        workflow_id=workflow_id,
        sequence=previous.sequence + 1 if previous else 1,
        previous_hash=previous.event_hash if previous else GENESIS,
        event_type=event_type,
        actor_id=actor_id,
        tool=tool,
        payload=redact(payload),
        request_id=request_id,
    )
    event.event_hash = event_digest(event)
    db.add(event)
    db.flush()
    return event


def verify_chain(
    events: Sequence[AuditEvent], *, previous_hash: str = GENESIS, start_sequence: int = 1
) -> bool:
    previous = previous_hash
    workflow_id = events[0].workflow_id if events else None
    for sequence, event in enumerate(events, start=start_sequence):
        if (
            event.workflow_id != workflow_id
            or event.sequence != sequence
            or event.previous_hash != previous
            or event.event_hash != event_digest(event)
        ):
            return False
        previous = event.event_hash
    return True
