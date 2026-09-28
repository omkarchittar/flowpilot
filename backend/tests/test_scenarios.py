"""Named workflow scenarios with real persistence and controlled model outputs.

This measures orchestration invariants, never model classification/extraction accuracy.
"""

import json
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import func, select
from test_orchestration import Transactions

from flowpilot.audit import verify_chain
from flowpilot.config import Settings
from flowpilot.domain import TRANSITIONS, Decision, State
from flowpilot.intake import accept_request, prepare_attachment
from flowpilot.models import Approval, AuditEvent, Job, Notification, ToolExecution, User, Vendor
from flowpilot.providers import Classification, Extraction, ModelResult, ProviderError
from flowpilot.security import SecretBox
from flowpilot.worker import run_once
from flowpilot.workflow_service import WorkflowConflict, decide, execute_approved

BUNDLE = json.loads((Path(__file__).resolve().parents[2] / "benchmarks/scenarios.json").read_text())
TODAY = date.fromisoformat(BUNDLE["as_of"])
FIELDS = ["company_name", "tax_id", "contact_name", "contact_email", "insurance_expiration"]
KINDS = ["tax_form", "insurance_certificate", "bank_confirmation"]
pytestmark = pytest.mark.postgres


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(TODAY.year, TODAY.month, TODAY.day, 12, tzinfo=UTC).astimezone(tz)


class ScenarioProvider:
    def __init__(self, scenario, values):
        self.scenario = scenario
        self.values = values
        self.remaining = scenario.get("failures", 0)

    def fail_if_requested(self, stage):
        if self.scenario["family"] == "retry" and self.scenario["stage"] == stage:
            if not self.scenario["retryable"]:
                raise ProviderError("invalid_model_response")
            if self.remaining:
                self.remaining -= 1
                raise ProviderError("provider_http_503", retryable=True)

    def classify(self, request_text):
        self.fail_if_requested("classify")
        classification = Classification(
            request_type=self.scenario.get("kind", "vendor_onboarding")
            if self.scenario["family"] == "classification"
            else "vendor_onboarding",
            confidence=self.scenario.get("confidence", 0.99),
        )
        return ModelResult(classification, "controlled-scenario-provider", 20, 10, 1, "classify-v1")

    def extract(self, sources):
        self.fail_if_requested("extract")
        ids = {
            kind: next(key for key, value in sources.items() if value.startswith(kind + "\n"))
            for kind in KINDS
        }
        payload = {
            field: {
                "value": value,
                "source_id": ids["tax_form"],
                "quote": value,
                "confidence": 0.99,
            }
            for field, value in self.values.items()
        }
        payload.update(
            confidence=0.99,
            documents=[
                {"source_id": ids[kind], "kind": kind, "quote": kind, "confidence": 0.99}
                for kind in KINDS
            ],
        )
        mutation = self.scenario.get("mutation")
        if self.scenario["family"] == "field":
            item = payload[self.scenario["field"]]
            if mutation == "missing":
                item.update(value=None, source_id=None, quote=None)
            if mutation == "unknown_source":
                item["source_id"] = "not-uploaded"
            if mutation == "invented_quote":
                item["quote"] = "Invented evidence absent from the source"
            if mutation == "low_confidence":
                item["confidence"] = 0.84
        if self.scenario["family"] == "document":
            item = next(d for d in payload["documents"] if d["kind"] == self.scenario["kind"])
            if mutation == "missing":
                payload["documents"].remove(item)
            if mutation == "unknown_source":
                item["source_id"] = "not-uploaded"
            if mutation == "request_source":
                item["source_id"] = "request"
            if mutation == "low_confidence":
                item["confidence"] = 0.84
        return ModelResult(
            Extraction.model_validate(payload),
            "controlled-scenario-provider",
            80,
            50,
            2,
            "extract-v1",
        )


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


@pytest.mark.parametrize("scenario", BUNDLE["scenarios"], ids=lambda row: row["id"])
def test_workflow_scenario(db, monkeypatch, scenario, record_property):
    import flowpilot.orchestration
    import flowpilot.worker

    monkeypatch.setattr(flowpilot.orchestration, "datetime", FixedDatetime)
    monkeypatch.setattr(flowpilot.worker, "datetime", FixedDatetime)
    key = Fernet.generate_key().decode()
    box = SecretBox(key)
    database = Transactions(db)
    settings = Settings(encryption_key=SecretStr(key))
    users = [
        User(email=f"{role}@example.com", name=role, role=role, password_hash="unused")
        for role in ["requester", "approver"]
    ]
    db.add_all(users)
    db.flush()
    requester, approver = users
    values = dict(
        company_name="Fictional Meridian Vendor",
        tax_id="12-3456789",
        contact_name="Jamie Example",
        contact_email="jamie@example.com",
        insurance_expiration="2030-12-31",
    )
    if scenario["family"] == "format":
        values[scenario["field"]] = scenario["value"]
    if scenario["family"] == "expiry":
        values["insurance_expiration"] = (TODAY + timedelta(days=scenario["days"])).isoformat()
    attachments = [
        prepare_attachment(
            f"{kind}.txt", (kind + "\n" + "\n".join(values.values())).encode(), max_bytes=10000
        )
        for kind in KINDS
    ]
    request = dict(
        requester_id=requester.id,
        title="Authored workflow scenario",
        request_text="Please onboard the fictional vendor. tax_form insurance_certificate bank_confirmation",
        idempotency_key=scenario["id"],
        attachments=attachments,
        box=box,
        request_id="scenario",
    )
    workflow = accept_request(db, **request)
    if scenario["family"] == "intake_replay":
        replay = (
            {**request, "attachments": list(reversed(attachments))}
            if scenario["mutation"] == "reverse_attachments"
            else dict(request)
        )
        if scenario["mutation"] == "changed_payload":
            replay["title"] = "Different payload"
            with pytest.raises(WorkflowConflict):
                accept_request(db, **replay)
        else:
            assert accept_request(db, **replay).id == workflow.id
        assert count(db, Job) == 1
    provider = ScenarioProvider(scenario, deepcopy(values))
    process_job = db.scalar(select(Job).where(Job.resource_id == workflow.id))
    process_job.max_attempts = 3
    db.flush()
    for _ in range(3):
        assert run_once(database, settings, provider_factory=lambda: provider)
        db.refresh(process_job)
        if process_job.status != "queued":
            break
        assert process_job.last_error_code == "provider_http_503"
        process_job.available_at = datetime.now(UTC) - timedelta(seconds=1)
        db.flush()
    assert count(db, Vendor) == count(db, Notification) == count(db, Approval) == 0
    if scenario["family"] in {"decision", "execution_replay", "revocation"}:
        actor = requester if scenario.get("own") else approver
        actor.role = scenario.get("role", "approver")
        db.flush()
        kwargs = dict(
            actor=actor,
            revision=1,
            decision=Decision(scenario.get("decision", "approve")),
            comment="Reviewed fictional scenario",
            box=box,
            request_id="human",
            today=TODAY,
        )
        if scenario.get("allowed", True):
            decide(db, workflow.id, **kwargs)
            assert count(db, Vendor) == count(db, Notification) == 0
            if kwargs["decision"] == Decision.APPROVE:
                if scenario["family"] == "revocation":
                    if scenario["mutation"] == "disabled":
                        actor.active = False
                    else:
                        actor.role = "requester"
                    db.flush()
                assert run_once(database, settings, provider_factory=lambda: provider)
            if scenario["family"] == "execution_replay":
                for _ in range(scenario["repeats"]):
                    assert execute_approved(
                        db, workflow.id, box=box, request_id="retry", today=TODAY
                    )
        else:
            with pytest.raises(PermissionError):
                decide(db, workflow.id, **kwargs)
    db.refresh(workflow)
    assert workflow.status == scenario["expected_state"]
    completed = workflow.status == "COMPLETED"
    assert count(db, Vendor) == count(db, Notification) == int(completed)
    assert count(db, ToolExecution) == 2 * int(completed)
    if completed:
        approval = db.scalar(select(Approval).where(Approval.workflow_id == workflow.id))
        assert (
            approval.decision == "approve"
            and approval.actor_id != requester.id
            and approval.revision == workflow.revision
        )
    events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.workflow_id == workflow.id)
        .order_by(AuditEvent.sequence)
    ).all()
    assert_audit_contract(db, workflow, events)
    assert values["tax_id"] not in json.dumps([event.payload for event in events])
    if scenario["family"] == "retry":
        assert any(
            event.event_type == ("RETRY" if scenario["retryable"] else "ERROR") for event in events
        )
    record_property("scenario_id", scenario["id"])
    record_property("family", scenario["family"])
    record_property("final_state", workflow.status)
    record_property("vendors", count(db, Vendor))
    record_property("sensitive_effects", count(db, ToolExecution))
    record_property("independently_approved_effects", count(db, ToolExecution) if completed else 0)
    record_property("duplicate_side_effects", max(0, count(db, Vendor) - 1))
    record_property("audit_verified", True)


def assert_audit_contract(db, workflow, events):
    message = "audit contract: missing, disconnected or inconsistent event"
    assert events and verify_chain(events), message
    assert sum(event.event_type == "REQUEST_RECEIVED" for event in events) == 1, message
    previous = "RECEIVED"
    for event in (event for event in events if event.event_type == "STATE_CHANGED"):
        assert event.payload["from"] == previous, message
        assert State(event.payload["to"]) in TRANSITIONS[State(previous)], message
        previous = event.payload["to"]
    assert previous == workflow.status, message
    approvals = db.scalars(select(Approval).where(Approval.workflow_id == workflow.id)).all()
    decisions = [event for event in events if event.event_type == "APPROVAL_DECISION"]
    assert len(decisions) == len(approvals), message
    for approval in approvals:
        assert any(
            event.actor_id == approval.actor_id
            and event.payload["decision"] == approval.decision
            and event.payload["revision"] == approval.revision
            for event in decisions
        ), message
    tools = [event for event in events if event.event_type == "TOOL_CALLED"]
    receipts = db.scalars(
        select(ToolExecution).where(ToolExecution.workflow_id == workflow.id)
    ).all()
    for receipt in receipts:
        matches = [
            event
            for event in tools
            if event.tool == receipt.tool
            and event.payload.get("status") == "success"
            and all(event.payload.get(key) == value for key, value in receipt.result.items())
        ]
        assert len(matches) == 1, message
    if "classification" in workflow.model_metadata:
        assert len([event for event in events if event.event_type == "MODEL_DECISION"]) == 1, (
            message
        )
    if "extraction" in workflow.model_metadata:
        assert {"extract_document", "check_duplicate_vendor", "validate_vendor"} <= {
            event.tool for event in tools
        }, message


@pytest.mark.parametrize(
    "omission", ["APPROVAL_DECISION", "create_vendor", "send_notification", "STATE_CHANGED"]
)
def test_scenario_audit_contract_detects_suppressed_emissions(
    db, monkeypatch, record_property, omission
):
    import flowpilot.workflow_service

    original = flowpilot.workflow_service.append_event

    def omit_event(*args, **kwargs):
        if kwargs.get("event_type") == omission or kwargs.get("tool") == omission:
            return None
        return original(*args, **kwargs)

    monkeypatch.setattr(flowpilot.workflow_service, "append_event", omit_event)
    scenario = next(row for row in BUNDLE["scenarios"] if row["id"] == "execution-replay-1")
    with pytest.raises(AssertionError, match="audit contract"):
        test_workflow_scenario(db, monkeypatch, scenario, record_property)
