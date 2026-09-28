"""Atomic request intake with encrypted evidence and payload-bound idempotency."""

import base64
import hashlib
import json
from dataclasses import dataclass
from pathlib import PurePath

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from flowpilot.audit import append_event
from flowpilot.db import new_id, utcnow
from flowpilot.documents import MEDIA_TYPES, extract_pages
from flowpilot.models import Document, Job, Workflow
from flowpilot.security import SecretBox
from flowpilot.workflow_service import WorkflowConflict


@dataclass(frozen=True)
class Attachment:
    filename: str
    content: bytes
    pages: list[tuple[int, str]]
    checksum: str


def prepare_attachment(filename: str, data: bytes, *, max_bytes: int) -> Attachment:
    filename = PurePath(filename.replace("\\", "/")).name
    if not filename or len(filename) > 255:
        raise ValueError("Filename must contain 1–255 characters")
    pages = extract_pages(filename, data, max_bytes=max_bytes)
    return Attachment(filename, data, pages, hashlib.sha256(data).hexdigest())


def save_attachments(
    db: Session, workflow: Workflow, attachments: list[Attachment], box: SecretBox
):
    existing = set(
        db.scalars(
            select(Document.checksum).where(
                Document.workflow_id == workflow.id, Document.revision == workflow.revision
            )
        )
    )
    for attachment in attachments:
        if attachment.checksum in existing:
            continue
        db.add(
            Document(
                workflow_id=workflow.id,
                revision=workflow.revision,
                filename=attachment.filename,
                media_type=MEDIA_TYPES[PurePath(attachment.filename).suffix.lower()],
                checksum=attachment.checksum,
                size_bytes=len(attachment.content),
                content_ciphertext=box.encrypt(base64.b64encode(attachment.content).decode()),
                text_ciphertext=box.encrypt(json.dumps(attachment.pages)),
            )
        )
        existing.add(attachment.checksum)
    db.flush()


def accept_request(
    db: Session,
    *,
    requester_id: str,
    title: str,
    request_text: str,
    idempotency_key: str,
    attachments: list[Attachment],
    box: SecretBox,
    request_id: str,
) -> Workflow:
    manifest = sorted({(a.filename, a.checksum) for a in attachments})
    payload_hash = hashlib.sha256(
        json.dumps(
            {"title": title, "request_text": request_text, "documents": manifest}, sort_keys=True
        ).encode()
    ).hexdigest()
    identifier = db.scalar(
        insert(Workflow)
        .values(
            id=new_id(),
            requester_id=requester_id,
            title=title,
            request_ciphertext=box.encrypt(request_text),
            idempotency_key=idempotency_key,
            request_hash=payload_hash,
            status="RECEIVED",
            revision=1,
            version=1,
            model_metadata={},
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        .on_conflict_do_nothing(index_elements=["requester_id", "idempotency_key"])
        .returning(Workflow.id)
    )
    if not identifier:
        row = db.scalar(
            select(Workflow).where(
                Workflow.requester_id == requester_id, Workflow.idempotency_key == idempotency_key
            )
        )
        if row.request_hash != payload_hash:
            raise WorkflowConflict(
                "Idempotency key was already used with different request content"
            )
        return row
    row = db.get(Workflow, identifier)
    save_attachments(db, row, attachments, box)
    append_event(
        db,
        row.id,
        event_type="REQUEST_RECEIVED",
        actor_id=requester_id,
        payload={"revision": 1, "document_count": len({a.checksum for a in attachments})},
        request_id=request_id,
    )
    db.add(
        Job(
            kind="process_request",
            resource_id=row.id,
            idempotency_key=f"process:{row.id}:1",
            payload={"revision": 1},
        )
    )
    db.flush()
    return row
