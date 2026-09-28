"""Relational invariants are enforced in PostgreSQL as well as domain services."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from flowpilot.db import Base, new_id, utcnow


class Identity:
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Identity, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(320), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(20), default="requester")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (
        CheckConstraint("role IN ('requester','reviewer','approver','admin')", name="valid_role"),
    )


class AuthSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Job(Identity, Base):
    __tablename__ = "jobs"
    kind: Mapped[str] = mapped_column(String(40))
    resource_id: Mapped[str] = mapped_column(String(36), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String(36))
    last_error_code: Mapped[str | None] = mapped_column(String(80))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("status IN ('queued','running','completed','failed')", name="valid_status"),
        CheckConstraint("attempts >= 0 AND max_attempts > 0", name="valid_attempts"),
        Index("ix_jobs_claim", "status", "available_at"),
    )


class Workflow(Identity, Base):
    __tablename__ = "workflows"
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    request_ciphertext: Mapped[str] = mapped_column(Text)
    idempotency_key: Mapped[str] = mapped_column(String(200))
    request_hash: Mapped[str] = mapped_column(String(64))
    workflow_type: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default="RECEIVED", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    version: Mapped[int] = mapped_column(Integer, default=1)
    candidate_ciphertext: Mapped[str | None] = mapped_column(Text)
    validation: Mapped[dict | None] = mapped_column(JSONB)
    model_metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    __mapper_args__ = {"version_id_col": version}
    __table_args__ = (
        UniqueConstraint("requester_id", "idempotency_key"),
        CheckConstraint("revision > 0", name="positive_revision"),
        CheckConstraint(
            "status IN ('RECEIVED','CLASSIFYING','EXTRACTING','VALIDATING',"
            "'NEEDS_INFORMATION','PENDING_APPROVAL','EXECUTING','COMPLETED',"
            "'REJECTED','NEEDS_MANUAL_REVIEW')",
            name="valid_state",
        ),
    )


class Document(Identity, Base):
    __tablename__ = "documents"
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    checksum: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    content_ciphertext: Mapped[str] = mapped_column(Text)
    text_ciphertext: Mapped[str | None] = mapped_column(Text)
    document_type: Mapped[str | None] = mapped_column(String(40))
    extraction: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("workflow_id", "revision", "checksum"),
        CheckConstraint("size_bytes > 0", name="positive_size"),
    )


class Approval(Identity, Base):
    __tablename__ = "approvals"
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(20))
    comment: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (
        UniqueConstraint("workflow_id", "revision"),
        CheckConstraint(
            "decision IN ('approve','reject','request_changes')", name="valid_decision"
        ),
    )


class AuditEvent(Identity, Base):
    __tablename__ = "audit_events"
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(40))
    actor_id: Mapped[str] = mapped_column(String(100))
    tool: Mapped[str | None] = mapped_column(String(60))
    payload: Mapped[dict] = mapped_column(JSONB)
    previous_hash: Mapped[str] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(100), index=True)
    __table_args__ = (
        UniqueConstraint("workflow_id", "sequence"),
        CheckConstraint("sequence > 0", name="positive_sequence"),
    )


class ToolExecution(Identity, Base):
    __tablename__ = "tool_executions"
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(60))
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict] = mapped_column(JSONB)
    duration_ms: Mapped[int] = mapped_column(Integer)
    __table_args__ = (CheckConstraint("duration_ms >= 0", name="nonnegative_duration"),)


class Vendor(Identity, Base):
    __tablename__ = "vendors"
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), unique=True)
    company_name: Mapped[str] = mapped_column(String(200))
    tax_fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    tax_ciphertext: Mapped[str] = mapped_column(Text)
    contact_email: Mapped[str] = mapped_column(String(320))


class Notification(Identity, Base):
    __tablename__ = "notifications"
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), index=True)
    recipient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    subject: Mapped[str] = mapped_column(String(200))
    message: Mapped[str] = mapped_column(Text)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LoginThrottle(Base):
    __tablename__ = "login_throttles"
    subject_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    attempts: Mapped[int] = mapped_column(Integer)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    __table_args__ = (CheckConstraint("attempts > 0", name="positive_attempts"),)
