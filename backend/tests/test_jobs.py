from datetime import timedelta

import pytest

from flowpilot.db import utcnow
from flowpilot.jobs import LeaseLost, claim, complete, fail, heartbeat
from flowpilot.models import Job

pytestmark = pytest.mark.postgres


def queued(db, key="one", **kwargs):
    job = Job(kind="test", resource_id="resource", idempotency_key=key, payload={}, **kwargs)
    db.add(job)
    db.flush()
    return job


def test_claim_is_exclusive_and_completion_requires_lease(db):
    row = queued(db)
    now = utcnow()
    lease = claim(db, now=now)
    assert lease.id == row.id
    assert claim(db, now=now) is None
    complete(db, lease, now=now)
    assert row.status == "completed"
    with pytest.raises(LeaseLost):
        complete(db, lease, now=now)


def test_expired_lease_is_reclaimed_and_old_worker_is_fenced(db):
    queued(db)
    now = utcnow()
    old = claim(db, now=now, lease_seconds=10)
    new = claim(db, now=now + timedelta(seconds=11))
    assert new.id == old.id and new.token != old.token
    with pytest.raises(LeaseLost):
        complete(db, old, now=now + timedelta(seconds=12))
    complete(db, new, now=now + timedelta(seconds=12))


def test_transient_failure_waits_for_backoff(db):
    row = queued(db)
    now = utcnow()
    lease = claim(db, now=now)
    assert fail(db, lease, code="timeout", retryable=True, now=now) == "queued"
    assert row.available_at > now
    assert claim(db, now=now) is None
    assert claim(db, now=row.available_at) is not None


def test_permanent_failure_does_not_retry(db):
    row = queued(db)
    now = utcnow()
    lease = claim(db, now=now)
    assert fail(db, lease, code="invalid_schema", retryable=False, now=now) == "failed"
    assert row.last_error_code == "invalid_schema"
    assert claim(db, now=now + timedelta(days=1)) is None


def test_retry_budget_exhaustion_is_terminal(db):
    row = queued(db, max_attempts=1)
    now = utcnow()
    lease = claim(db, now=now)
    assert fail(db, lease, code="timeout", retryable=True, now=now) == "failed"
    assert row.attempts == 1


def test_repeated_worker_crashes_cannot_retry_forever(db):
    row = queued(db, max_attempts=1)
    now = utcnow()
    claim(db, now=now, lease_seconds=10)
    assert claim(db, now=now + timedelta(seconds=11)) is None
    db.refresh(row)
    assert row.status == "failed"
    assert row.last_error_code == "lease_exhausted"


def test_heartbeat_extends_only_current_lease(db):
    row = queued(db)
    now = utcnow()
    lease = claim(db, now=now, lease_seconds=10)
    heartbeat(db, lease, now=now + timedelta(seconds=5), lease_seconds=20)
    assert row.lease_until == now + timedelta(seconds=25)
    with pytest.raises(LeaseLost):
        heartbeat(db, lease, now=now + timedelta(seconds=26))


def test_parallel_workers_skip_rows_locked_by_other_transactions():
    import os
    from uuid import uuid4

    from sqlalchemy import create_engine, delete
    from sqlalchemy.orm import Session

    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires PostgreSQL")
    engine = create_engine(url)
    ids = []
    try:
        with Session(engine) as setup, setup.begin():
            for _ in range(2):
                job = Job(
                    kind="concurrency",
                    resource_id="resource",
                    idempotency_key=str(uuid4()),
                    payload={},
                )
                setup.add(job)
                setup.flush()
                ids.append(job.id)
        with Session(engine) as first, Session(engine) as second:
            with first.begin(), second.begin():
                one = claim(first)
                two = claim(second)
                assert one.id != two.id
                assert {one.id, two.id} == set(ids)
                complete(first, one)
                complete(second, two)
    finally:
        with Session(engine) as cleanup, cleanup.begin():
            cleanup.execute(delete(Job).where(Job.id.in_(ids)))
        engine.dispose()


@pytest.mark.parametrize("operation", ["complete", "heartbeat", "fail"])
def test_lease_expiring_while_waiting_for_row_lock_is_rejected(operation):
    import os
    import threading
    import time
    from uuid import uuid4

    from sqlalchemy import create_engine, delete, select
    from sqlalchemy.orm import Session

    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Requires PostgreSQL")
    engine = create_engine(url)
    job_id = None
    failures = []
    started = threading.Event()

    def worker():
        try:
            with Session(engine) as session, session.begin():
                started.set()
                if operation == "fail":
                    fail(session, lease, code="timeout", retryable=True)
                else:
                    {"complete": complete, "heartbeat": heartbeat}[operation](session, lease)
        except Exception as exc:
            failures.append(exc)

    try:
        with Session(engine) as setup, setup.begin():
            row = Job(
                kind="lease-test", resource_id="resource", idempotency_key=str(uuid4()), payload={}
            )
            setup.add(row)
            setup.flush()
            job_id = row.id
            lease = claim(setup, lease_seconds=1)
        with Session(engine) as blocker, blocker.begin():
            blocker.scalar(select(Job).where(Job.id == job_id).with_for_update())
            thread = threading.Thread(target=worker)
            thread.start()
            assert started.wait(timeout=2)
            time.sleep(1.25)
        thread.join(timeout=3)
        assert not thread.is_alive()
        assert len(failures) == 1 and isinstance(failures[0], LeaseLost)
    finally:
        with Session(engine) as cleanup, cleanup.begin():
            cleanup.execute(delete(Job).where(Job.id == job_id))
        engine.dispose()
