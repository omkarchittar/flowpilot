"""Actual adapter/queue behavior: summaries cannot invent authority or survive stale inputs."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import func, select
from test_orchestration import FixtureProvider
from test_orchestration import work as work

from flowpilot.domain import Decision
from flowpilot.jobs import LeaseLost, claim
from flowpilot.models import AuditEvent, Document, Job, User, Vendor
from flowpilot.providers import ModelResult, OpenAIWorkflowProvider, ProviderError, ReviewBrief
from flowpilot.worker import run_once
from flowpilot.workflow_service import decide, revise_request


def context():
    return {
        "revision": 1,
        "source_state": "NEEDS_INFORMATION",
        "assessment": "blocked",
        "workflow_type": "vendor_onboarding",
        "policy_version": "vendor-v1",
        "issues": [
            {
                "id": "missing_document:bank_confirmation",
                "message": "A supporting document is required.",
            }
        ],
        "human_approval_required": True,
    }


def response(payload):
    return httpx.Response(
        200,
        json={
            "model": "gpt-4.1-mini-2025-04-14",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(payload)}}],
            "usage": {"prompt_tokens": 120, "completion_tokens": 45},
        },
    )


def test_provider_explains_redacted_facts_and_records_actual_provenance():
    def handler(request):
        body = json.loads(request.content)
        facts = json.loads(body["messages"][1]["content"])
        assert facts["issues"] == [
            {
                "id": "missing_document:bank_confirmation",
                "message": "A supporting document is required.",
            }
        ]
        assert "sources" not in facts and "request_text" not in facts
        assert body["response_format"]["json_schema"]["strict"] is True
        return response(
            {
                "assessment": "blocked",
                "summary": "Bank confirmation is missing. Supply that evidence before independent review.",
                "issue_refs": ["missing_document:bank_confirmation"],
            }
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = OpenAIWorkflowProvider("test", client=client).review_brief(context())
    assert result.value.assessment == "blocked"
    assert "Bank confirmation" in result.value.summary
    assert result.input_tokens == 120 and result.output_tokens == 45
    assert result.model == "gpt-4.1-mini-2025-04-14"
    assert len(result.prompt_fingerprint) == 64


@pytest.mark.parametrize(
    "mutation",
    [
        "authority",
        "omitted_issue",
        "invented_issue",
        "duplicate_issue",
        "extra_field",
        "blank",
        "too_long",
    ],
)
def test_invalid_summary_cannot_reclassify_the_policy_result(mutation):
    payload = {
        "assessment": "blocked",
        "summary": "Missing bank confirmation prevents review.",
        "issue_refs": ["missing_document:bank_confirmation"],
    }
    if mutation == "authority":
        payload["assessment"] = "ready_for_review"
    if mutation == "omitted_issue":
        payload["issue_refs"] = []
    if mutation == "invented_issue":
        payload["issue_refs"] = ["invalid_tax_id:tax_id"]
    if mutation == "duplicate_issue":
        payload["issue_refs"] *= 2
    if mutation == "extra_field":
        payload["approved"] = True
    if mutation == "blank":
        payload["summary"] = "   "
    if mutation == "too_long":
        payload["summary"] = "a" * 801
    with httpx.Client(transport=httpx.MockTransport(lambda _: response(payload))) as client:
        with pytest.raises(ProviderError, match="invalid_model_response"):
            OpenAIWorkflowProvider("test", client=client).review_brief(context())


class BriefProvider(FixtureProvider):
    def __init__(self, *, failure=None, before_result=None, **kwargs):
        super().__init__(**kwargs)
        self.failure = failure
        self.before_result = before_result
        self.contexts = []

    def review_brief(self, facts):
        self.contexts.append(facts)
        if self.before_result:
            self.before_result()
        if self.failure:
            raise self.failure
        return ModelResult(
            ReviewBrief(
                assessment=facts["assessment"],
                summary="Review the supplied evidence and policy findings before making a human decision.",
                issue_refs=[i["id"] for i in facts["issues"]],
            ),
            "controlled-brief-provider",
            110,
            35,
            4,
            "review-brief-v1",
            "a" * 64,
        )


def brief_job(db, workflow):
    return db.scalar(
        select(Job)
        .where(Job.resource_id == workflow.id, Job.kind == "review_brief")
        .order_by(Job.created_at.desc())
    )


@pytest.mark.postgres
def test_validation_queues_advisory_brief_without_waiting_or_creating_a_vendor(work, db):
    database, settings, workflow, _, _ = work
    provider = BriefProvider()
    run_once(database, settings, provider_factory=lambda: provider)
    assert workflow.status == "PENDING_APPROVAL"
    assert getattr(workflow, "review_brief", None) is not None
    assert workflow.review_brief["status"] == "pending"
    assert not provider.contexts
    run_once(database, settings, provider_factory=lambda: provider)
    assert workflow.review_brief["status"] == "complete"
    assert workflow.review_brief["result"]["assessment"] == "ready_for_review"
    assert workflow.review_brief["metadata"]["input_tokens"] == 110
    assert db.scalar(select(func.count()).select_from(Vendor)) == 0
    facts = json.dumps(provider.contexts)
    for private in [
        "Acme",
        "12-3456789",
        "Jane",
        "jane@example.com",
        "Please onboard",
        "2027-12-31",
    ]:
        assert private not in facts
    events = list(db.scalars(select(AuditEvent).where(AuditEvent.workflow_id == workflow.id)))
    generated = next(
        e
        for e in events
        if e.event_type == "MODEL_DECISION" and e.payload.get("purpose") == "review_brief"
    )
    assert generated.payload["model"] == "controlled-brief-provider"
    assert "summary" not in generated.payload
    assert len(generated.payload["output_sha256"]) == 64


@pytest.mark.postgres
@pytest.mark.parametrize("kind,confidence", [("invoice_review", 0.99), ("vendor_onboarding", 0.4)])
def test_unsupported_or_uncertain_classification_gets_a_blocked_brief(work, kind, confidence):
    database, settings, workflow, _, _ = work
    provider = BriefProvider(kind=kind, confidence=confidence)
    run_once(database, settings, provider_factory=lambda: provider)
    run_once(database, settings, provider_factory=lambda: provider)
    assert workflow.status == "NEEDS_MANUAL_REVIEW"
    assert workflow.review_brief["result"]["assessment"] == "blocked"
    assert workflow.review_brief["result"]["issue_refs"]


@pytest.mark.postgres
def test_transient_summary_failure_retries_without_changing_approval_authority(work, db):
    database, settings, workflow, _, _ = work
    provider = BriefProvider(failure=ProviderError("provider_unavailable", retryable=True))
    run_once(database, settings, provider_factory=lambda: provider)
    run_once(database, settings, provider_factory=lambda: provider)
    job = brief_job(db, workflow)
    assert job.status == "queued" and job.available_at > datetime.now(UTC)
    assert workflow.status == "PENDING_APPROVAL" and workflow.review_brief["status"] == "pending"
    provider.failure = None
    job.available_at = datetime.now(UTC)
    db.flush()
    run_once(database, settings, provider_factory=lambda: provider)
    assert workflow.review_brief["status"] == "complete"
    assert workflow.status == "PENDING_APPROVAL"


@pytest.mark.postgres
def test_exhausted_summary_failure_does_not_escalate_or_prevent_valid_approval(work, db):
    database, settings, workflow, approver, box = work
    provider = BriefProvider(failure=ProviderError("provider_unavailable", retryable=True))
    run_once(database, settings, provider_factory=lambda: provider)
    job = brief_job(db, workflow)
    job.max_attempts = 1
    db.flush()
    run_once(database, settings, provider_factory=lambda: provider)
    assert workflow.status == "PENDING_APPROVAL" and workflow.review_brief["status"] == "failed"
    decide(
        db,
        workflow.id,
        actor=approver,
        revision=1,
        decision=Decision.APPROVE,
        comment="",
        box=box,
        request_id="human",
        today=datetime.now(UTC).date(),
    )
    run_once(database, settings, provider_factory=lambda: provider)
    assert workflow.status == "COMPLETED"
    assert db.scalar(select(func.count()).select_from(Vendor)) == 1


@pytest.mark.postgres
def test_last_expired_summary_lease_becomes_visible_failure_once(work, db):
    database, settings, workflow, _, _ = work
    provider = BriefProvider()
    run_once(database, settings, provider_factory=lambda: provider)
    lease = claim(db)
    job = brief_job(db, workflow)
    job.max_attempts = job.attempts
    job.lease_until = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    assert not run_once(database, settings, provider_factory=lambda: provider)
    assert workflow.review_brief["status"] == "failed"
    assert workflow.review_brief["error_code"] == "lease_exhausted"
    assert workflow.status == "PENDING_APPROVAL"
    assert not run_once(database, settings, provider_factory=lambda: provider)
    failures = list(
        db.scalars(
            select(AuditEvent).where(
                AuditEvent.workflow_id == workflow.id,
                AuditEvent.event_type == "ERROR",
                AuditEvent.request_id == lease.id,
            )
        )
    )
    assert len(failures) == 1


@pytest.mark.postgres
def test_older_revision_summary_cannot_publish_after_an_authorized_revision(work, db):
    from flowpilot.review_briefs import generate_review_brief

    database, settings, workflow, _, box = work
    bank = db.scalar(
        select(Document).where(Document.workflow_id == workflow.id, Document.filename == "2.txt")
    )
    db.delete(bank)
    db.flush()
    run_once(database, settings, provider_factory=BriefProvider)
    assert workflow.status == "NEEDS_INFORMATION"
    lease = claim(db)

    def update_request():
        revise_request(
            db,
            workflow.id,
            actor=db.get(User, workflow.requester_id),
            revision=1,
            request_text="Updated onboarding request for a new revision.",
            box=box,
            request_id="revision",
        )

    provider = BriefProvider(before_result=update_request)
    generate_review_brief(database, lease, lambda: provider)
    assert workflow.revision == 2 and workflow.review_brief is None
    assert db.get(Job, lease.id).status == "completed"
    event = db.scalar(
        select(AuditEvent).where(
            AuditEvent.request_id == lease.id, AuditEvent.event_type == "MODEL_RESULT_DISCARDED"
        )
    )
    assert len(event.payload["output_sha256"]) == 64


@pytest.mark.postgres
def test_changed_context_same_revision_cannot_be_overwritten_by_older_brief(work, db):
    from flowpilot.review_briefs import generate_review_brief

    database, settings, workflow, approver, box = work
    run_once(database, settings, provider_factory=BriefProvider)
    lease = claim(db)

    def request_changes():
        decide(
            db,
            workflow.id,
            actor=approver,
            revision=1,
            decision=Decision.REQUEST_CHANGES,
            comment="Check the contact.",
            box=box,
            request_id="changes",
            today=datetime.now(UTC).date(),
        )

    generate_review_brief(database, lease, lambda: BriefProvider(before_result=request_changes))
    assert workflow.status == "NEEDS_INFORMATION"
    assert workflow.review_brief["status"] == "pending"
    assert workflow.review_brief["context"]["assessment"] == "blocked"
    event = db.scalar(
        select(AuditEvent).where(
            AuditEvent.request_id == lease.id, AuditEvent.event_type == "MODEL_RESULT_DISCARDED"
        )
    )
    assert len(event.payload["output_sha256"]) == 64
    assert "human_changes_requested:request" in [
        i["id"] for i in workflow.review_brief["context"]["issues"]
    ]


@pytest.mark.postgres
def test_lost_lease_cannot_publish_a_summary(work, db):
    from flowpilot.review_briefs import generate_review_brief

    database, settings, workflow, _, _ = work
    run_once(database, settings, provider_factory=BriefProvider)
    lease = claim(db)

    def lose_lease():
        job = db.get(Job, lease.id)
        job.lease_until = datetime.now(UTC) - timedelta(seconds=1)
        db.flush()

    with pytest.raises(LeaseLost):
        generate_review_brief(database, lease, lambda: BriefProvider(before_result=lose_lease))
    assert workflow.review_brief["status"] == "pending"


@pytest.mark.postgres
def test_superseded_failures_cannot_fill_reconciliation_batch_and_starve_current_failure(work, db):
    from flowpilot.worker import reconcile_failures

    database, settings, workflow, _, _ = work
    # Historical jobs are legal queue records, but cannot represent the current brief.
    for i in range(100):
        db.add(
            Job(
                kind="review_brief",
                resource_id=workflow.id,
                idempotency_key=f"old-brief-{i}",
                payload={"revision": 1, "fingerprint": f"superseded-{i}"},
                status="failed",
                last_error_code="provider_unavailable",
            )
        )
    db.flush()
    run_once(database, settings, provider_factory=BriefProvider)
    current = brief_job(db, workflow)
    current.status = "failed"
    current.last_error_code = "lease_exhausted"
    db.flush()
    reconcile_failures(database)
    assert workflow.review_brief["status"] == "failed"
    assert workflow.review_brief["error_code"] == "lease_exhausted"


@pytest.mark.postgres
def test_failed_brief_cannot_interrupt_an_already_approved_execution(work, db):
    database, settings, workflow, approver, box = work
    provider = BriefProvider(failure=ProviderError("invalid_model_response"))
    run_once(database, settings, provider_factory=lambda: provider)
    decide(
        db,
        workflow.id,
        actor=approver,
        revision=1,
        decision=Decision.APPROVE,
        comment="Checked documents",
        box=box,
        request_id="human",
        today=datetime.now(UTC).date(),
    )
    run_once(database, settings, provider_factory=lambda: provider)
    assert workflow.status == "EXECUTING" and workflow.review_brief["status"] == "failed"
    run_once(database, settings, provider_factory=lambda: provider)
    assert workflow.status == "COMPLETED"
    assert db.scalar(select(func.count()).select_from(Vendor)) == 1


@pytest.mark.postgres
def test_same_review_context_does_not_enqueue_duplicate_calls(work, db):
    from flowpilot.review_briefs import queue_review_brief

    database, settings, workflow, _, _ = work
    provider = BriefProvider()
    run_once(database, settings, provider_factory=lambda: provider)
    queue_review_brief(db, workflow, request_id="replay")
    run_once(database, settings, provider_factory=lambda: provider)
    queue_review_brief(db, workflow, request_id="replay-after-result")
    db.flush()
    assert not run_once(database, settings, provider_factory=lambda: provider)
    assert len(provider.contexts) == 1
    assert (
        db.scalar(
            select(func.count())
            .select_from(Job)
            .where(Job.resource_id == workflow.id, Job.kind == "review_brief")
        )
        == 1
    )
