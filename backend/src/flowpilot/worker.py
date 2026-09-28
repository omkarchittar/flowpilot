"""Run the durable workflow worker separately with python -m flowpilot.worker."""

import argparse
import json
import logging
import signal
import threading
from contextlib import contextmanager
from datetime import UTC, datetime

from sqlalchemy import select

from flowpilot.audit import append_event
from flowpilot.config import Settings
from flowpilot.db import Database
from flowpilot.domain import State
from flowpilot.jobs import LeaseLost, assert_owned, claim, complete, fail, heartbeat
from flowpilot.models import Job, Workflow
from flowpilot.orchestration import process_request
from flowpilot.providers import OpenAIWorkflowProvider, ProviderError
from flowpilot.security import SecretBox
from flowpilot.workflow_service import change_state, execute_approved, locked_workflow

logger = logging.getLogger("flowpilot.worker")


@contextmanager
def keep_lease(database, lease):
    stopped = threading.Event()

    def renew():
        while not stopped.wait(30):
            try:
                with database.transaction() as db:
                    heartbeat(db, lease)
            except Exception:
                # Final ownership check remains the authority; never commit a stale result.
                logger.warning(json.dumps({"event": "heartbeat_failed", "job_id": lease.id}))
                return

    thread = threading.Thread(target=renew, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=2)


def escalate(db, workflow, request_id, code):
    if workflow.status == State.RECEIVED:
        change_state(db, workflow, State.CLASSIFYING, actor_id="system", request_id=request_id)
    if workflow.status in {State.CLASSIFYING, State.EXTRACTING, State.VALIDATING, State.EXECUTING}:
        append_event(
            db,
            workflow.id,
            event_type="ERROR",
            actor_id="system",
            payload={"code": code},
            request_id=request_id,
        )
        change_state(
            db, workflow, State.NEEDS_MANUAL_REVIEW, actor_id="system", request_id=request_id
        )


def reconcile_failures(database):
    with database.transaction() as db:
        rows = db.execute(
            select(Workflow, Job)
            .join(Job, Job.resource_id == Workflow.id)
            .where(
                Job.status == "failed",
                Job.payload["revision"].as_integer() == Workflow.revision,
                Workflow.status.in_(
                    [
                        State.RECEIVED,
                        State.CLASSIFYING,
                        State.EXTRACTING,
                        State.VALIDATING,
                        State.EXECUTING,
                    ]
                ),
            )
            .with_for_update(of=Workflow, skip_locked=True)
            .limit(100)
        ).all()
        for workflow, job in rows:
            escalate(db, workflow, job.id, job.last_error_code or "worker_failed")


def run_once(database: Database, settings: Settings, *, provider_factory=None) -> bool:
    with database.transaction() as db:
        lease = claim(db)
    reconcile_failures(database)
    if lease is None:
        return False
    try:
        if not settings.encryption_key or not settings.encryption_key.get_secret_value():
            raise ProviderError("encryption_not_configured")
        box = SecretBox(settings.encryption_key.get_secret_value())
        if provider_factory is None:

            def provider_factory():
                return OpenAIWorkflowProvider(
                    settings.openai_api_key.get_secret_value() if settings.openai_api_key else "",
                    model=settings.generation_model,
                    base_url=settings.openai_base_url,
                    timeout=settings.provider_timeout_seconds,
                )

        if lease.kind == "process_request":
            with keep_lease(database, lease):
                process_request(database, lease, box, provider_factory)
        elif lease.kind == "execute_vendor":
            with database.transaction() as db:
                assert_owned(db, lease)
                workflow = locked_workflow(db, lease.resource_id)
                if workflow.revision == lease.payload.get("revision"):
                    execute_approved(
                        db,
                        workflow.id,
                        box=box,
                        request_id=lease.id,
                        today=datetime.now(UTC).date(),
                    )
                complete(db, lease)
        else:
            raise ValueError("Unsupported job kind")
        logger.info(json.dumps({"event": "job_completed", "job_id": lease.id, "kind": lease.kind}))
    except LeaseLost:
        logger.warning(json.dumps({"event": "lease_lost", "job_id": lease.id}))
    except Exception as exc:
        code = exc.code if isinstance(exc, ProviderError) else "workflow_processing_failed"
        retryable = isinstance(exc, ProviderError) and exc.retryable
        try:
            with database.transaction() as db:
                status = fail(db, lease, code=code, retryable=retryable)
                workflow = locked_workflow(db, lease.resource_id)
                if workflow.revision == lease.payload.get("revision"):
                    append_event(
                        db,
                        workflow.id,
                        event_type="RETRY" if status == "queued" else "ERROR",
                        actor_id="system",
                        tool="extract_document" if workflow.status == State.EXTRACTING else None,
                        payload={
                            "code": code,
                            "attempt": lease.attempt,
                            "retryable": retryable,
                            "status": status,
                        },
                        request_id=lease.id,
                    )
                    if status == "failed":
                        escalate(db, workflow, lease.id, code)
        except LeaseLost:
            logger.warning(json.dumps({"event": "lease_lost", "job_id": lease.id}))
        logger.warning(
            json.dumps(
                {"event": "job_failed", "job_id": lease.id, "code": code, "retryable": retryable}
            )
        )
    return True


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = Settings()
    database = Database(settings.database_url)
    stop = threading.Event()
    for signum in [signal.SIGTERM, signal.SIGINT]:
        signal.signal(signum, lambda *_: stop.set())
    try:
        while not stop.is_set():
            worked = run_once(database, settings)
            if args.once:
                break
            if not worked:
                stop.wait(settings.worker_poll_seconds)
    finally:
        database.close()


if __name__ == "__main__":
    main()
