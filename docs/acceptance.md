# PRD acceptance audit

Audited 2026-09-28 against [the source PRD](PRD.md), implementation at `b7e472c`,
and [the execution ledger](implementation-plan.md). This maps implemented software
and unresolved release gates; it does not certify the final release.

## Functional requirements

| PRD requirement | Implementation and direct verification | Status |
| --- | --- | --- |
| FR-1: manual request, attachment upload and simulated incoming API | [intake API](../backend/src/flowpilot/api.py), [intake service](../backend/src/flowpilot/intake.py), [HTTP tests](../backend/tests/test_workflow_api.py), multipart browser journey | Implemented |
| FR-2: four request types; only vendor onboarding executed | [provider classification](../backend/src/flowpilot/providers.py), [orchestration tests](../backend/tests/test_orchestration.py), classification scenario family | Implemented; live accuracy open |
| FR-3: company, tax, contact, documents and insurance extraction | Strict provider schemas, quote/source verification and [extraction tests](../backend/tests/test_extraction.py) | Implemented; live extraction accuracy open |
| FR-4: deterministic completeness, format, expiry and policy rules | [domain policy](../backend/src/flowpilot/domain.py), [domain tests](../backend/tests/test_domain.py), boundary scenario families | Implemented |
| FR-5: extract_document, validate_vendor, check_duplicate_vendor, create_vendor, send_notification | [orchestrator](../backend/src/flowpilot/orchestration.py), [workflow service](../backend/src/flowpilot/workflow_service.py), [execution tests](../backend/tests/test_workflow_service.py) | Implemented with persisted vendor registry and in-app notifications; no external ERP/email claim |
| FR-6: approve, reject, request changes; explicit authority | Domain decision matrix, revision-bound approval service, 24 human-decision scenarios and independent-approval browser journey | Implemented |
| FR-7: immutable transition, model, tool, approval, retry/failure audit | [audit module](../backend/src/flowpilot/audit.py), append-only database triggers, [persistence tests](../backend/tests/test_persistence.py), [scenario completeness/sabotage checks](../backend/tests/test_scenarios.py) | Implemented; database administrators remain trusted |
| FR-8: bounded safe retry/backoff and manual escalation | [jobs](../backend/src/flowpilot/jobs.py), [worker](../backend/src/flowpilot/worker.py), [queue tests](../backend/tests/test_jobs.py), provider recovery scenarios | Implemented; advisory brief failure has separate nonblocking behavior |
| FR-9: side-effect idempotency | Unique payload-bound receipts and vendor fingerprint; replay/rollback tests and scenario families | Implemented; zero duplicate vendor creations in controlled tests |
| FR-10: requester/reviewer/approver/admin | [auth tests](../backend/tests/test_auth.py), role/ownership HTTP tests and browser journeys | Implemented |

## State, approval UX, reliability and security

- Every state from PRD section 7 and every allowed transition is explicit in the
  [domain model](../backend/src/flowpilot/domain.py) and embedded README state diagram.
  [Workflow models](../backend/src/flowpilot/models.py) persist revisions, documents,
  approvals, audit events, jobs, vendors, receipts and notifications.
- All section 10 approval information appears in the [workflow detail](../frontend/src/components/workflow-detail.tsx):
  fields, confidence, validation, warnings, sources and decision controls. The
  [advisory AI brief](../frontend/src/components/review-brief.tsx) has independent durable
  jobs, provenance and stale-output fencing. [Brief tests](../backend/tests/test_review_briefs.py)
  prove failures cannot change approval/execution authority.
- All five required UI surfaces exist: dashboard, request form, workflow detail/timeline,
  approvals and chronological audit. [Nine browser journeys](../frontend/tests/workflows.spec.ts)
  verify request → approval → execution → notification, revisions, ownership, conflicts,
  multipart uploads, accessible desktop/mobile views and advisory failure states.
- Schema validation, upload limits, tool allowlists, provider timeouts, deterministic
  execution guards and low-confidence escalation are exercised by domain/provider/API tests.
  [Security tests](../backend/tests/test_security.py) verify encryption/redaction. Logs use
  correlation IDs and sanitized error codes. Authorized source downloads may contain
  sensitive source values; field masking is not document sanitization.
- The last full native suite passed 292 tests against actual PostgreSQL, including all
  102 workflow scenarios. Both nonroot Dockerfiles built on Linux/arm64; all nine browser
  journeys also passed against containerized API, worker, PostgreSQL and frontend.
  These checks do not establish production load, live-model quality or public deployment.
- [CI](../.github/workflows/ci.yml) runs tests on every pull request/main push, checks
  migrations, exports scenario evidence and builds images. The tag-triggered
  [release workflow](../.github/workflows/release.yml) waits for all quality gates.
  Remote execution and publication are still open.

## Evaluation and portfolio criteria

| PRD sections 18–19 / milestone | Evidence | Acceptance |
| --- | --- | --- |
| At least 100 automated scenarios | [102-case manifest](../benchmarks/scenarios.json), executable PostgreSQL suite and [saved report](../benchmarks/results/workflow-contracts.json) | Implemented and measured as controlled software contracts |
| Classification accuracy across request types | [32-request authored dataset](../benchmarks/extraction.json), production-adapter benchmark CLI and metric tests | Live measurements open |
| Field exact match/precision/recall, mandatory recall and unsupported-field rate | [Benchmark definitions](../benchmarks/README.md), [metrics tests](../backend/tests/test_benchmark_metrics.py) | Computation implemented; live accuracy report open |
| Completion/retry/duplicate effects | Saved report includes denominators: 102 expected outcomes, 4/6 injected transient recoveries, 0 duplicate vendors | Measured controlled contracts; not production rates |
| Every sensitive effect independently approved; auditable state changes | 10/10 approved sensitive effects, 102/102 complete audit checks, deliberate omitted-event sabotage tests | Verified within test scope |
| README architecture, state machine, screenshots, GIF, reliability/security | Embedded diagrams, recorded app assets, design decisions and [operations runbook](deployment.md) | Present |
| Deployment and portfolio launch | Local Docker journeys and deployment/release definitions | Remote CI, registry publication, public deployment and final release open |

Required next evidence: real-provider classification/extraction report with inspected errors;
successful remote CI and image publication; selected hosting environment and a verified deployed
workflow. Controlled extraction receipts are not a replacement for measured model accuracy.
