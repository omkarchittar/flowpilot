"""Durable PostgreSQL queue with expiring leases and stale-worker fencing.

The caller commits claim before doing work. Complete/fail must be in the same
transaction as corresponding domain mutations. Check assert_owned in a short
transaction before external IO, release locks, then recheck before final writes. Use heartbeats for work longer than a lease.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from flowpilot.db import new_id, utcnow
from flowpilot.models import Job


class LeaseLost(RuntimeError):
    pass


@dataclass(frozen=True)
class Lease:
    id: str
    token: str
    kind: str
    resource_id: str
    payload: dict
    attempt: int


def claim(db: Session, *, now: datetime | None = None, lease_seconds: int = 120) -> Lease | None:
    now = now or utcnow()
    if not 1 <= lease_seconds <= 3600:
        raise ValueError("Lease duration must be 1–3600 seconds")
    eligible = or_(
        and_(Job.status == "queued", Job.available_at <= now),
        and_(Job.status == "running", Job.lease_until <= now),
    )
    # SKIP LOCKED permits independent workers to make progress on different jobs.
    while row := db.scalar(
        select(Job)
        .where(eligible)
        .order_by(Job.available_at, Job.id)
        .with_for_update(skip_locked=True)
        .limit(1)
        .execution_options(populate_existing=True)
    ):
        if row.attempts >= row.max_attempts:
            row.status = "failed"
            row.last_error_code = "lease_exhausted"
            row.completed_at = now
            row.lease_until = None
            row.lease_token = None
            db.flush()
            continue
        row.status = "running"
        row.attempts += 1
        row.lease_token = new_id()
        row.lease_until = now + timedelta(seconds=lease_seconds)
        db.flush()
        return Lease(
            row.id, row.lease_token, row.kind, row.resource_id, dict(row.payload), row.attempts
        )
    return None


def assert_owned(db: Session, lease: Lease, *, now: datetime | None = None) -> Job:
    row = db.scalar(
        select(Job)
        .where(Job.id == lease.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = now or utcnow()  # Sample only after a potentially blocking row lock.
    if (
        row is None
        or row.status != "running"
        or row.lease_token != lease.token
        or row.lease_until is None
        or row.lease_until <= now
    ):
        raise LeaseLost("Job lease is no longer owned by this worker")
    return row


def complete(db: Session, lease: Lease, *, now: datetime | None = None) -> None:
    row = assert_owned(db, lease, now=now)
    now = now or utcnow()
    row.status, row.completed_at = "completed", now
    row.lease_until = row.lease_token = None
    db.flush()


def fail(
    db: Session, lease: Lease, *, code: str, retryable: bool, now: datetime | None = None
) -> str:
    row = assert_owned(db, lease, now=now)
    now = now or utcnow()
    # Only stable internal codes belong here; never exception messages or prompts.
    if (
        not code
        or len(code) > 80
        or any(not (c.isascii() and (c.isalnum() or c == "_")) for c in code)
    ):
        raise ValueError("Failure codes must use lowercase-safe identifiers")
    row.last_error_code = code
    row.lease_until = row.lease_token = None
    if retryable and row.attempts < row.max_attempts:
        row.status = "queued"
        row.available_at = now + timedelta(seconds=min(60, 2**row.attempts))
    else:
        row.status, row.completed_at = "failed", now
    db.flush()
    return row.status


def heartbeat(
    db: Session, lease: Lease, *, now: datetime | None = None, lease_seconds: int = 120
) -> None:
    if not 1 <= lease_seconds <= 3600:
        raise ValueError("Lease duration must be 1–3600 seconds")
    row = assert_owned(db, lease, now=now)
    now = now or utcnow()
    row.lease_until = now + timedelta(seconds=lease_seconds)
    db.flush()
