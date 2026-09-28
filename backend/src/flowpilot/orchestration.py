"""Resumable AI stages. All model IO runs outside state-changing transactions."""

import json
from datetime import UTC, datetime
from time import perf_counter

from sqlalchemy import select

from flowpilot.audit import append_event
from flowpilot.domain import State, validate_vendor
from flowpilot.jobs import assert_owned, complete
from flowpilot.models import Document
from flowpilot.providers import verified_candidate
from flowpilot.review_briefs import queue_review_brief
from flowpilot.workflow_service import (
    change_state,
    duplicate_exists,
    locked_workflow,
    read_candidate,
)

TERMINAL_PROCESS_STATES = {
    State.PENDING_APPROVAL,
    State.NEEDS_INFORMATION,
    State.NEEDS_MANUAL_REVIEW,
    State.REJECTED,
    State.COMPLETED,
    State.EXECUTING,
}


def process_request(database, lease, box, provider_factory):
    provider = None
    while True:
        with database.transaction() as db:
            assert_owned(db, lease)
            workflow = locked_workflow(db, lease.resource_id)
            if (
                workflow.revision != lease.payload.get("revision")
                or workflow.status in TERMINAL_PROCESS_STATES
            ):
                complete(db, lease)
                return
            if workflow.status == State.RECEIVED:
                change_state(
                    db, workflow, State.CLASSIFYING, actor_id="system", request_id=lease.id
                )
            stage = State(workflow.status)
            request_text = box.decrypt(workflow.request_ciphertext)
            sources = {"request": request_text}
            if stage == State.EXTRACTING:
                documents = db.scalars(
                    select(Document).where(
                        Document.workflow_id == workflow.id, Document.revision == workflow.revision
                    )
                )
                for document in documents:
                    if document.text_ciphertext:
                        pages = json.loads(box.decrypt(document.text_ciphertext))
                        sources[document.id] = "\n\n".join(text for _, text in pages)
            if stage == State.VALIDATING:
                candidate = read_candidate(workflow, box)
                started = perf_counter()
                duplicate = duplicate_exists(db, candidate, box)
                append_event(
                    db,
                    workflow.id,
                    event_type="TOOL_CALLED",
                    actor_id="system",
                    tool="check_duplicate_vendor",
                    payload={
                        "duplicate": duplicate,
                        "duration_ms": int((perf_counter() - started) * 1000),
                        "status": "success",
                    },
                    request_id=lease.id,
                )
                started = perf_counter()
                report = validate_vendor(
                    candidate, today=datetime.now(UTC).date(), duplicate=duplicate
                )
                workflow.validation = report.model_dump(mode="json")
                append_event(
                    db,
                    workflow.id,
                    event_type="TOOL_CALLED",
                    actor_id="system",
                    tool="validate_vendor",
                    payload={
                        "ready": report.ready,
                        "manual_review": report.manual_review,
                        "issue_codes": [i.code for i in report.issues],
                        "duration_ms": int((perf_counter() - started) * 1000),
                        "status": "success",
                    },
                    request_id=lease.id,
                )
                target = (
                    State.PENDING_APPROVAL
                    if report.ready
                    else State.NEEDS_MANUAL_REVIEW
                    if report.manual_review
                    else State.NEEDS_INFORMATION
                )
                change_state(db, workflow, target, actor_id="system", request_id=lease.id)
                queue_review_brief(db, workflow, request_id=lease.id)
                complete(db, lease)
                return
        # Snapshot and stage have been committed. No locks remain during provider IO.
        if provider is None:
            provider = provider_factory()
        if stage == State.CLASSIFYING:
            result = provider.classify(request_text)
            classification = result.value
            with database.transaction() as db:
                assert_owned(db, lease)
                workflow = locked_workflow(db, lease.resource_id)
                if workflow.revision != lease.payload["revision"] or workflow.status != stage:
                    complete(db, lease)
                    return
                workflow.workflow_type = classification.request_type
                workflow.model_metadata = {
                    **workflow.model_metadata,
                    "classification": result.metadata(),
                    "classification_confidence": classification.confidence,
                }
                append_event(
                    db,
                    workflow.id,
                    event_type="MODEL_DECISION",
                    actor_id="agent",
                    payload={
                        "request_type": classification.request_type,
                        "confidence": classification.confidence,
                        **result.metadata(),
                    },
                    request_id=lease.id,
                )
                target = (
                    State.EXTRACTING
                    if classification.request_type == "vendor_onboarding"
                    and classification.confidence >= 0.85
                    else State.NEEDS_MANUAL_REVIEW
                )
                change_state(db, workflow, target, actor_id="system", request_id=lease.id)
                if target == State.NEEDS_MANUAL_REVIEW:
                    queue_review_brief(db, workflow, request_id=lease.id)
        elif stage == State.EXTRACTING:
            result = provider.extract(sources)
            candidate = verified_candidate(result.value, sources)
            with database.transaction() as db:
                assert_owned(db, lease)
                workflow = locked_workflow(db, lease.resource_id)
                if workflow.revision != lease.payload["revision"] or workflow.status != stage:
                    complete(db, lease)
                    return
                workflow.candidate_ciphertext = box.encrypt(candidate.model_dump_json())
                workflow.model_metadata = {
                    **workflow.model_metadata,
                    "extraction": result.metadata(),
                }
                for evidence in candidate.documents:
                    document = db.get(Document, evidence.document_id)
                    if (
                        document
                        and document.workflow_id == workflow.id
                        and document.revision == workflow.revision
                    ):
                        document.document_type = evidence.kind
                        document.extraction = {
                            "confidence": evidence.confidence,
                            "source_verified": True,
                        }
                append_event(
                    db,
                    workflow.id,
                    event_type="TOOL_CALLED",
                    actor_id="agent",
                    tool="extract_document",
                    payload={
                        "verified_fields": sorted(candidate.evidence),
                        "document_count": len(candidate.documents),
                        "confidence": candidate.confidence,
                        "status": "success",
                        **result.metadata(),
                    },
                    request_id=lease.id,
                )
                change_state(db, workflow, State.VALIDATING, actor_id="system", request_id=lease.id)
        else:
            raise ValueError("Unexpected processing state")
