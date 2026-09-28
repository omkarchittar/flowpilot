"""Authenticated workflow commands and deliberately limited read models."""

import base64
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import Field, ValidationError
from sqlalchemy import func, select

from flowpilot.audit import GENESIS, verify_chain
from flowpilot.auth import Actor, Db, Input
from flowpilot.domain import Decision, Role, State
from flowpilot.intake import accept_request, prepare_attachment, save_attachments
from flowpilot.models import Approval, AuditEvent, Document, Notification, User, Workflow
from flowpilot.security import SecretBox
from flowpilot.workflow_service import decide, read_candidate, revise_request

router = APIRouter(prefix="/api", tags=["workflows"])
IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=8, max_length=200, pattern=r"^[A-Za-z0-9:_-]+$")
]


class IntakeInput(Input):
    title: str = Field(min_length=1, max_length=200)
    request_text: str = Field(min_length=10, max_length=20000)


class DecisionInput(Input):
    revision: int = Field(ge=1)
    decision: Decision
    comment: str = Field(default="", max_length=2000)


def secret_box(request: Request) -> SecretBox:
    value = request.app.state.settings.encryption_key
    if value is None or not value.get_secret_value():
        raise HTTPException(503, "Encryption is not configured")
    try:
        return SecretBox(value.get_secret_value())
    except (ValueError, TypeError) as exc:
        raise HTTPException(503, "Encryption is not configured correctly") from exc


def authorized_workflow(db, workflow_id: str, actor: User) -> Workflow:
    row = db.get(Workflow, workflow_id)
    if row is None or (actor.role == Role.REQUESTER and row.requester_id != actor.id):
        raise HTTPException(404, "Workflow not found")
    return row


def workflow_view(row: Workflow) -> dict:
    return {
        field: getattr(row, field)
        for field in [
            "id",
            "title",
            "status",
            "workflow_type",
            "requester_id",
            "revision",
            "created_at",
            "updated_at",
            "validation",
            "model_metadata",
        ]
    }


def read_files(files: list[UploadFile], maximum: int):
    if len(files) > 20:
        raise HTTPException(422, "At most 20 documents may be attached")
    attachments = []
    remaining = maximum
    try:
        for file in files:
            data = file.file.read(remaining + 1)
            if len(data) > remaining:
                raise HTTPException(413, "Combined attachments exceed the upload limit")
            remaining -= len(data)
            attachments.append(prepare_attachment(file.filename or "", data, max_bytes=maximum))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    finally:
        for file in files:
            file.file.close()
    return attachments


@router.get("/request-options")
def request_options(request: Request, actor: Actor):
    return {
        "upload_limit_bytes": request.app.state.settings.upload_limit_bytes,
        "max_documents": 20,
        "accepted_extensions": [".pdf", ".txt", ".md"],
    }


@router.post("/intake", status_code=201)
def intake(
    body: IntakeInput, request: Request, db: Db, actor: Actor, idempotency_key: IdempotencyKey
):
    row = accept_request(
        db,
        requester_id=actor.id,
        title=body.title,
        request_text=body.request_text,
        idempotency_key=idempotency_key,
        attachments=[],
        box=secret_box(request),
        request_id=request.state.request_id,
    )
    return workflow_view(row)


@router.post("/workflows", status_code=201)
def create_workflow(
    request: Request,
    db: Db,
    actor: Actor,
    idempotency_key: IdempotencyKey,
    title: Annotated[str, Form(min_length=1, max_length=200)],
    request_text: Annotated[str, Form(min_length=10, max_length=20000)],
    files: Annotated[list[UploadFile] | None, File()] = None,
):
    try:
        body = IntakeInput(title=title, request_text=request_text)
    except ValidationError as exc:
        raise HTTPException(422, "Invalid workflow request") from exc
    box = secret_box(request)
    attachments = read_files(files or [], request.app.state.settings.upload_limit_bytes)
    row = accept_request(
        db,
        requester_id=actor.id,
        title=body.title,
        request_text=body.request_text,
        idempotency_key=idempotency_key,
        attachments=attachments,
        box=box,
        request_id=request.state.request_id,
    )
    return workflow_view(row)


def visible(actor: User):
    return Workflow.requester_id == actor.id if actor.role == Role.REQUESTER else True


@router.get("/workflows")
def list_workflows(
    db: Db,
    actor: Actor,
    status: State | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    filters = [visible(actor)]
    if status is not None:
        filters.append(Workflow.status == status)
    rows = db.scalars(
        select(Workflow)
        .where(*filters)
        .order_by(Workflow.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return {
        "items": [workflow_view(row) for row in rows],
        "total": db.scalar(select(func.count()).select_from(Workflow).where(*filters)),
        "offset": offset,
        "limit": limit,
    }


@router.get("/overview")
def overview(db: Db, actor: Actor):
    counts = dict(
        db.execute(
            select(Workflow.status, func.count()).where(visible(actor)).group_by(Workflow.status)
        ).all()
    )
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "pending_approval": counts.get(State.PENDING_APPROVAL, 0),
        "completed": counts.get(State.COMPLETED, 0),
        "manual_review": counts.get(State.NEEDS_MANUAL_REVIEW, 0),
    }


@router.get("/workflows/{workflow_id}")
def workflow_detail(workflow_id: str, request: Request, db: Db, actor: Actor):
    row = authorized_workflow(db, workflow_id, actor)
    view = workflow_view(row)
    view["review_brief"] = row.review_brief
    if row.candidate_ciphertext:
        candidate = read_candidate(row, secret_box(request)).model_dump(mode="json")
        candidate["tax_id"] = (
            "••-•••" + candidate["tax_id"][-4:] if candidate.get("tax_id") else None
        )
        view["candidate"] = candidate
    else:
        view["candidate"] = None
    documents = db.scalars(
        select(Document)
        .where(Document.workflow_id == row.id, Document.revision == row.revision)
        .order_by(Document.created_at)
    )
    view["documents"] = [
        {
            "id": d.id,
            "filename": d.filename,
            "media_type": d.media_type,
            "size_bytes": d.size_bytes,
            "document_type": d.document_type,
            "revision": d.revision,
        }
        for d in documents
    ]
    approvals = db.scalars(
        select(Approval).where(Approval.workflow_id == row.id).order_by(Approval.created_at)
    )
    view["approvals"] = [
        {
            "id": a.id,
            "actor_id": a.actor_id,
            "revision": a.revision,
            "decision": a.decision,
            "comment": a.comment,
            "created_at": a.created_at,
        }
        for a in approvals
    ]
    return view


@router.get("/workflows/{workflow_id}/audit")
def workflow_audit(
    workflow_id: str,
    db: Db,
    actor: Actor,
    after: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    authorized_workflow(db, workflow_id, actor)
    anchor = GENESIS
    if after:
        anchor = db.scalar(
            select(AuditEvent.event_hash).where(
                AuditEvent.workflow_id == workflow_id, AuditEvent.sequence == after
            )
        )
        if anchor is None:
            raise HTTPException(422, "Audit cursor does not exist")
    rows = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.workflow_id == workflow_id, AuditEvent.sequence > after)
        .order_by(AuditEvent.sequence)
        .limit(limit + 1)
    ).all()
    return {
        "items": [
            {
                field: getattr(e, field)
                for field in [
                    "id",
                    "sequence",
                    "event_type",
                    "actor_id",
                    "tool",
                    "payload",
                    "event_hash",
                    "previous_hash",
                    "request_id",
                    "created_at",
                ]
            }
            for e in rows[:limit]
        ],
        "verified": verify_chain(rows[:limit], previous_hash=anchor, start_sequence=after + 1),
        "verification_scope": "page",
        "anchor_hash": anchor,
        "has_more": len(rows) > limit,
        "next_cursor": rows[min(len(rows), limit) - 1].sequence if rows else after,
    }


@router.post("/workflows/{workflow_id}/decisions")
def decision(workflow_id: str, body: DecisionInput, request: Request, db: Db, actor: Actor):
    authorized_workflow(db, workflow_id, actor)
    row = decide(
        db,
        workflow_id,
        actor=actor,
        revision=body.revision,
        decision=body.decision,
        comment=body.comment,
        box=secret_box(request),
        request_id=request.state.request_id,
        today=datetime.now(UTC).date(),
    )
    return workflow_view(row)


@router.post("/workflows/{workflow_id}/revisions")
def revise(
    workflow_id: str,
    request: Request,
    db: Db,
    actor: Actor,
    revision: Annotated[int, Form(ge=1)],
    request_text: Annotated[str, Form(min_length=10, max_length=20000)],
    files: Annotated[list[UploadFile] | None, File()] = None,
):
    old = authorized_workflow(db, workflow_id, actor)
    box = secret_box(request)
    attachments = read_files(files or [], request.app.state.settings.upload_limit_bytes)
    previous = list(
        db.scalars(
            select(Document).where(Document.workflow_id == old.id, Document.revision == revision)
        )
    )
    replaced = {a.filename for a in attachments}
    retained = [d for d in previous if d.filename not in replaced]
    combined = {d.checksum: d.size_bytes for d in retained}
    combined.update({a.checksum: len(a.content) for a in attachments})
    if len(combined) > 20:
        raise HTTPException(422, "A revision may contain at most 20 documents")
    if sum(combined.values()) > request.app.state.settings.upload_limit_bytes:
        raise HTTPException(413, "Combined revision attachments exceed the upload limit")
    row = revise_request(
        db,
        workflow_id,
        actor=actor,
        revision=revision,
        request_text=request_text,
        box=box,
        request_id=request.state.request_id,
    )
    # Revisions retain immutable prior evidence unless the user supplies a replacement
    # with the same filename. All extraction is recomputed for the new revision.
    replaced = {a.filename for a in attachments}
    for d in previous:
        if d.filename not in replaced:
            db.add(
                Document(
                    workflow_id=row.id,
                    revision=row.revision,
                    filename=d.filename,
                    media_type=d.media_type,
                    checksum=d.checksum,
                    size_bytes=d.size_bytes,
                    content_ciphertext=d.content_ciphertext,
                    text_ciphertext=d.text_ciphertext,
                )
            )
    db.flush()
    save_attachments(db, row, attachments, box)
    return workflow_view(row)


@router.get("/documents/{document_id}/download")
def download_document(document_id: str, request: Request, db: Db, actor: Actor):
    row = db.get(Document, document_id)
    if row is None:
        raise HTTPException(404, "Document not found")
    authorized_workflow(db, row.workflow_id, actor)
    content = base64.b64decode(secret_box(request).decrypt(row.content_ciphertext), validate=True)
    return Response(
        content,
        media_type=row.media_type,
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(row.filename, safe="")
        },
    )


@router.get("/notifications")
def notifications(db: Db, actor: Actor):
    rows = db.scalars(
        select(Notification)
        .where(Notification.recipient_id == actor.id)
        .order_by(Notification.created_at.desc())
        .limit(100)
    )
    return [
        {
            "id": n.id,
            "workflow_id": n.workflow_id,
            "subject": n.subject,
            "message": n.message,
            "read_at": n.read_at,
            "created_at": n.created_at,
        }
        for n in rows
    ]


@router.post("/notifications/{notification_id}/read", status_code=204)
def read_notification(notification_id: str, db: Db, actor: Actor):
    row = db.get(Notification, notification_id)
    if row is None or row.recipient_id != actor.id:
        raise HTTPException(404, "Notification not found")
    row.read_at = datetime.now(UTC)
