"""Advisory model summaries of redacted policy facts, fenced by revision and context."""

import hashlib
import json
from copy import deepcopy

from sqlalchemy import select

from flowpilot.audit import append_event
from flowpilot.db import utcnow
from flowpilot.jobs import assert_owned, complete
from flowpilot.models import Job, Workflow
from flowpilot.providers import ReviewBrief, validate_review_brief


def fingerprint(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def queue_review_brief(db, workflow, *, request_id, extra_issue=None):
    report = workflow.validation or {}
    issues = [
        {"id": f"{i['code']}:{i['field']}", "message": i["message"]}
        for i in report.get("issues", [])
    ]
    if extra_issue:
        issues.append(extra_issue)
    if not report and not extra_issue:
        if workflow.workflow_type != "vendor_onboarding":
            issues.append(
                {
                    "id": "unsupported_workflow:workflow_type",
                    "message": "Only vendor onboarding is supported for automatic processing.",
                }
            )
        if workflow.model_metadata.get("classification_confidence", 0) < 0.85:
            issues.append(
                {
                    "id": "uncertain_classification:workflow_type",
                    "message": "Classification confidence requires manual review.",
                }
            )
    context = {
        "revision": workflow.revision,
        "source_state": workflow.status,
        "workflow_type": workflow.workflow_type,
        "assessment": "ready_for_review" if report.get("ready") and not issues else "blocked",
        "policy_version": report.get("policy_version"),
        "issues": issues,
        "passed_checks": [
            "required_fields",
            "source_evidence",
            "tax_and_email_formats",
            "required_documents",
            "insurance_minimum_30_days",
            "duplicate_vendor_check",
        ]
        if report.get("ready")
        else [],
        "human_approval_required": True,
    }
    digest = fingerprint(context)
    if workflow.review_brief and workflow.review_brief.get("fingerprint") == digest:
        return
    workflow.review_brief = {"status": "pending", "fingerprint": digest, "context": context}
    db.add(
        Job(
            kind="review_brief",
            resource_id=workflow.id,
            idempotency_key=f"brief:{workflow.id}:{workflow.revision}:{digest}",
            payload={"revision": workflow.revision, "fingerprint": digest},
        )
    )
    append_event(
        db,
        workflow.id,
        event_type="REVIEW_BRIEF_QUEUED",
        actor_id="system",
        payload={"revision": workflow.revision, "fingerprint": digest},
        request_id=request_id,
    )


def current_brief(workflow, payload):
    brief = workflow.review_brief
    return bool(
        workflow.revision == payload.get("revision")
        and brief
        and brief.get("status") == "pending"
        and brief.get("fingerprint") == payload.get("fingerprint")
    )


def generate_review_brief(database, lease, provider_factory):
    from flowpilot.workflow_service import locked_workflow

    with database.transaction() as db:
        assert_owned(db, lease)
        workflow = locked_workflow(db, lease.resource_id)
        if not current_brief(workflow, lease.payload):
            complete(db, lease)
            return
        context = deepcopy(workflow.review_brief["context"])
    # No database locks or sensitive source text cross this provider boundary.
    result = provider_factory().review_brief(context)
    value = ReviewBrief.model_validate(result.value.model_dump())
    validate_review_brief(value, context)
    with database.transaction() as db:
        assert_owned(db, lease)
        workflow = locked_workflow(db, lease.resource_id)
        if current_brief(workflow, lease.payload):
            workflow.review_brief = {
                **workflow.review_brief,
                "status": "complete",
                "result": value.model_dump(),
                "metadata": result.metadata(),
                "generated_at": utcnow().isoformat(),
            }
            append_event(
                db,
                workflow.id,
                event_type="MODEL_DECISION",
                actor_id="agent",
                payload={
                    "purpose": "review_brief",
                    "revision": workflow.revision,
                    "fingerprint": lease.payload["fingerprint"],
                    "assessment": value.assessment,
                    "issue_refs": value.issue_refs,
                    "output_sha256": fingerprint(value.model_dump()),
                    **result.metadata(),
                },
                request_id=lease.id,
            )
        else:
            append_event(
                db,
                workflow.id,
                event_type="MODEL_RESULT_DISCARDED",
                actor_id="agent",
                payload={
                    "purpose": "review_brief",
                    "revision": lease.payload["revision"],
                    "fingerprint": lease.payload["fingerprint"],
                    "reason": "context_changed",
                    "output_sha256": fingerprint(value.model_dump()),
                    **result.metadata(),
                },
                request_id=lease.id,
            )
        complete(db, lease)


def mark_brief_failed(workflow, payload, code):
    if current_brief(workflow, payload):
        workflow.review_brief = {**workflow.review_brief, "status": "failed", "error_code": code}
        return True
    return False


def reconcile_brief_failures(db):
    rows = db.execute(
        select(Workflow, Job)
        .join(Job, Job.resource_id == Workflow.id)
        .where(
            Job.kind == "review_brief",
            Job.status == "failed",
            Job.payload["revision"].as_integer() == Workflow.revision,
            Workflow.review_brief["status"].as_string() == "pending",
            Job.payload["fingerprint"].as_string()
            == Workflow.review_brief["fingerprint"].as_string(),
        )
        .with_for_update(of=Workflow, skip_locked=True)
        .limit(100)
    ).all()
    for workflow, job in rows:
        code = job.last_error_code or "review_brief_failed"
        if mark_brief_failed(workflow, job.payload, code):
            append_event(
                db,
                workflow.id,
                event_type="ERROR",
                actor_id="system",
                payload={
                    "purpose": "review_brief",
                    "code": code,
                    "status": "failed",
                    "attempt": job.attempts,
                },
                request_id=job.id,
            )
