# FlowPilot implementation plan

**Goal:** Implement the complete supplied PRD as a reliable portfolio project.
**Architecture:** Modular FastAPI application, independent durable worker, PostgreSQL,
and Next.js frontend. Domain rules do not depend on HTTP or model providers.
**Tech stack:** Python 3.12+, SQLAlchemy 2, Alembic, FastAPI, PostgreSQL, Next.js, TypeScript.
**Spec:** [architecture.md](architecture.md); source acceptance criteria: [PRD.md](PRD.md).

## Global constraints

No placeholder product behavior. No fabricated metrics. Real Postgres integration tests.
Sensitive values never appear in logs. APIs validate and authorize every mutation.
Keep the full PRD scope intact across iterations. Implement core backend before UI polish.

## Review focus

Malformed/oversized files; model outputs without evidence; concurrency and retries;
expired/forged credentials; changed inputs after a saved approval or evaluation snapshot.
Each is covered by tests in the owning task below and checked again through HTTP.

## Execution

Implement inline in this session, with behavior tests preceding domain implementation.
User explicitly authorized scaffolding and backend implementation; proceed without
adding intermediate approval gates. Record actual test results here, not intentions.

### 1. Foundation and schema

- [x] Deliverable: `config.py, db.py, models.py, security.py, migrations`.
- [x] Behavior evidence: State, policy, role, redaction and relational constraints have behavior tests; migrations run on PostgreSQL.
- [x] Run the backend suite (`.venv/bin/pytest`) and relevant integration/browser checks.
- [x] Commit the verified increment and record evidence below.

### 2. Ingestion and AI extraction

- [x] Deliverable: `documents.py, providers.py, api.py`.
- [x] Behavior evidence: Bounded uploads and strict schema validation; supported/unsupported request classification; extracted fields require source evidence.
- [x] Run the backend suite (`.venv/bin/pytest`) and relevant integration/browser checks.
- [x] Commit the verified increment and record evidence below.

### 3. Durable workflow and approvals

- [x] Deliverable: `orchestration.py, worker.py, workflow_service.py, audit.py`.
- [x] Behavior evidence: Revision-bound approvals, append-only events, concurrent claims, retry exhaustion, idempotent vendor creation and in-app notifications.
- [x] Run the backend suite (`.venv/bin/pytest`) and relevant integration/browser checks.
- [x] Commit the verified increment and record evidence below.

### 4. API and reliability benchmark

- [x] Deliverable: `api.py, tests/, benchmarks/`.
- [ ] Behavior evidence: RBAC and ownership enforced through HTTP; at least 100 scenarios; extraction accuracy and zero duplicate side effects reported honestly.
- [x] Run the backend suite (`.venv/bin/pytest`) and relevant integration/browser checks.
- [x] Commit the verified increment and record evidence below.

### 5. Frontend and operational delivery

- [ ] Deliverable: `frontend/, Dockerfile, compose.yaml, .github/workflows/`.
- [ ] Behavior evidence: Request → validation → approval → execution timeline browser journey; responsive UI; CI/builds; screenshots, GIF and security runbook.
- [ ] Run the backend suite (`.venv/bin/pytest`) and relevant integration/browser checks.
- [ ] Commit the verified increment and record evidence below.

## Evidence ledger

- 2026-09-28: Read both source PRDs, verified remote repository empty, cloned independent repository, preserved source requirements and architecture. Implementation in progress.

### Backend increment — 2026-09-28

- Foundation schema and domain services committed locally.
- PostgreSQL 17 + pgvector 0.8.6 installed for actual integration tests on local port 55432.
- Verified: 110 tests, 95% statement coverage; Ruff passes; Alembic schema check passes; full downgrade to base then upgrade succeeds.
- Queue concurrency test uses separate PostgreSQL transactions and proves SKIP LOCKED gives different jobs to different workers.
- API currently exposes only operational endpoints. Authentication and product endpoints remain pending.
- Docker Compose and CI definitions are present but not executed locally (Docker is unavailable).
- Neither frontend, complete benchmark corpus, live model quality, screenshots, GIF nor release deployment is complete.
- Next: authenticated APIs and worker orchestration; continue through all remaining PRD requirements.

### Reviewed foundation checkpoint

- Independent review found concrete lease-timing, authority-cache, PDF memory, chunk-amplification and model-identity issues. All applicable findings were reproduced and fixed; no review findings deferred.
- Final suite for this checkpoint: **115 passing tests** with PostgreSQL, with no skipped tests.
- Real Uvicorn readiness and Prometheus endpoints returned successful responses; smoke-test servers were stopped afterward.
- Current status: foundation complete, broader product implementation remains active. No remote push or release deployment has been performed.

### Authenticated API and durable-worker checkpoint — 2026-09-28

- Cookie/Bearer authentication, CSRF, persisted login throttles, bootstrap CLI and account administration implemented. Password validation errors omit input values.
- Atomic, encrypted, idempotent intake; strict-schema classification/extraction; verified field and document quotes; policy validation; human decisions; revisions; execution; inbox and audit pagination implemented.
- End-to-end PostgreSQL tests reach approval without side effects, then require human approval before vendor and notification creation. Retry/exhaustion paths preserve audit and route permanent failure to manual review.
- Revision limits cover retained plus new documents. Blank normalized quotes cannot satisfy document evidence. Audit responses explicitly verify one page against its preceding hash.
- Full suite: **155 passing tests**, no skips, with PostgreSQL 17. Ruff lint/format and Alembic schema check pass. Full downgrade to base and upgrade to head pass on the isolated test database.
- Native Uvicorn smoke test in a temporary database verifies CLI bootstrap, real HTTP authentication, persisted product mutation, separate-worker missing-key failure handling, and session revocation. Temporary processes and database removed afterward.
- Independent review found three concrete issues across the increment (blank evidence quotes, bootstrap validation secret exposure, PDF upload-size mismatch). Regression tests reproduced all three; fixes approved on re-review with no outstanding findings.
- Compose now starts the worker and shares backend configuration. FlowPilot dependency locks include psutil. YAML and environment references validated, but actual Docker builds/startup remain unverified because Docker is unavailable.
- These test totals are not live provider quality metrics or the final PRD benchmark corpus. Frontend, complete benchmark artifacts and release presentation remain outstanding. No remote push or deployment performed.

### Provider disconnect correction — 2026-09-28

- Applied the provider-boundary finding from EvalRAG review: HTTP protocol disconnects are transient provider failures, not unclassified worker errors.
- Reproduced with httpx.RemoteProtocolError, fixed by catching the TransportError family, and verified safe retry classification without exposing transport details.
- Updated suite: **156 passing tests** against PostgreSQL; lint/format pass.


### Workflow and extraction benchmark checkpoint — 2026-09-28

- Added a manifest of **102 named workflow scenarios** spanning classification thresholds, missing/unverified fields/documents, malformed values, insurance dates, role/self-approval combinations, transient/permanent failures, idempotency/replayed execution and revoked authority. All execute actual services with PostgreSQL and controlled model responses.
- Every scenario checks side-effect cardinality and independent current-revision approval. Audit checks validate the hash chain and state continuity, match persisted approvals to decision events and match sensitive tool receipts to their audit events. Four sabotage tests suppress required emissions and prove missing events are detected.
- Added **32 authored classification requests / 20 vendor extraction cases**, with fictional evidence, required-field/document labels, missing/ambiguous values and adversarial instructions. CLI measures actual configured provider output, keeps failures/misclassification in denominators, reports field-level precision/recall and raw unsupported-value rates separately, and records dataset/endpoint/model/prompt/token provenance without raw fields in reports.
- Tightened response model identity to exact configured model or dated snapshot suffix; added prompt/schema fingerprints to provider metadata. Regression test rejects an unrelated model suffix.
- Independent review identified failed observations disappearing from reliability totals and audit-chain validity being mistaken for completeness. Both fixed with explicit regressions; re-review approved with no outstanding findings. Missing metrics are unknown with coverage; failed known observations remain in metrics; retry denominators remain fixed.
- Final local check script: **271 passing tests**, no skips, with PostgreSQL 17. Ruff format/lint and Alembic schema drift check pass. No schema change in this increment; migrations were already roundtrip-verified in the prior backend increment.
- Complete scenario report: 102/102 expected outcomes, 10/10 independently approved sensitive effects, zero duplicate vendors, 102 audit contracts verified. Four of six injected transient cases recover; the other two intentionally exhaust their retry budget. Saved report: `benchmarks/results/workflow-contracts.json`. These are software contract observations, not production/model accuracy claims.
- Native extraction CLI smoke used a temporary local HTTP provider explicitly named `controlled-contract`: 32 classifications and 20 extractions, with one deliberately unsupported field correctly lowering recall/increasing unsupported rate. Actual model/prompt/token metadata persisted; no raw tax identifier appeared in the report. This validates measurement wiring, not live-model quality.
- CI and local check script now produce/gate on the scenario report. Docker execution and remote CI remain unverified locally. Live extraction accuracy remains required before the full benchmark/release requirement is complete, so task 4's broader behavioral requirement stays open.
- Next: full Next.js frontend and browser journeys, live-model measurements, Docker/release/deployment validation, screenshots/GIF and final requirement audit. Goal remains active; no remote push or deployment performed.


### Operations console checkpoint — 2026-09-28

- Implemented the Next.js/TypeScript console: cookie login/logout, persisted overview counts,
  paginated/filterable requests and approvals, bounded multipart intake, revisions, extracted
  field/source/confidence views, deterministic validation, human decisions, audit timeline,
  notifications and admin account/access controls. Polling cancels obsolete requests and shows
  errors explicitly. Backend authority remains decisive.
- Added authenticated request options so the form uses configured upload policy. Revision drafts
  retain their original base version. Intake retries retain their idempotency key; independent
  approval and self-approval restrictions are visible in the interface.
- Independent review identified stale drafts adopting a polled revision and Next's default proxy
  body ceiling truncating supported larger uploads. Both fixed and covered by browser regressions.
  Temporarily removing the fixes caused both tests to fail (missing conflict, truncated upload returning HTTP 500);
  restoring them passes. Corrected a fixture assertion to respect checksum deduplication.
  Final re-review approved with no outstanding findings.
- Verified the actual standalone production server (including copied static/public assets) against
  a disposable PostgreSQL database, FastAPI and a separate worker with a controlled HTTP provider.
  **All 8 browser journeys pass**, covering approvals/execution/audit/inbox/logout, revisions,
  rejection/self-approval, cross-owner denial, team administration, concurrent edits, >10MiB
  uploads, mobile navigation and axe checks on login, request form, dashboard, review and mobile list.
- Visual inspection caught a mobile table minimum width hiding statuses; fixed it and added an
  explicit status-in-viewport assertion. Text contrast and form labels corrected; closed mobile
  navigation is hidden from focus. Saved actual desktop/mobile screenshots with fixture provenance.
- Frontend lint, TypeScript, Prettier, production build and Python fixture lint/format pass.
  Backend check script still passes **271 tests / 102 named scenarios**, with no PostgreSQL skips;
  schema drift check and Ruff pass. No database schema changes in this increment.
- Added nonroot frontend Dockerfile, standalone build packaging, Compose console service and
  frontend CI/browser/image jobs. YAML syntax checked and configuration reviewed. Docker and
  remote CI have not run locally; no deployment or remote push performed.
- Added setup, build-time proxy configuration and deployment/security runbook. ESLint9 is pinned
  because current Next React rules fail with ESLint10; this tooling constraint is documented.
- Remaining FlowPilot work: PRD AI-generated ready/blocked summary (current summary is explicitly
  deterministic), measured live-model extraction results, deployment/release pipeline verification,
  demo GIF and final acceptance audit. Full task 5 remains open because release requirements remain.
  EvalRAG frontend and broader two-project release work also remain active.


### Advisory AI review brief checkpoint — 2026-09-28

- Completed the PRD's AI-generated explanation of readiness/blockers. Separate durable jobs receive
  only redacted policy/classification facts, use strict model output schemas, and require matching
  assessment plus exact issue references. No raw request, document, field values or human comments
  enter the summary prompt. Free-form wording remains explicitly advisory in the UI.
- Persisted the current brief with revision, source state, context fingerprint, model/prompt/token
  provenance and generation time. Lease/revision/context fencing prevents stale publication; both
  published and discarded results record output digests in immutable audit. Revisions clear the
  brief; human changes and execution blocks replace it.
- Summary retries use the existing bounded durable queue. Exhaustion and final expired leases mark
  the brief unavailable without blocking valid approvals or interrupting approved execution.
- Review found stale failed jobs could fill a reconciliation batch and starve current failures,
  plus missing digests for discarded outputs. Reproduced both with failing tests, fixed them and
  obtained approval on re-review with no outstanding findings.
- Verified **292 backend tests** on PostgreSQL, including all **102 workflow scenarios**, schema
  drift check and Ruff. The scenarios now also generate controlled briefs and check their audit
  records. Full downgrade to base and upgrade to `0004_review_brief`, schema check and two
  post-migration provider/API persistence smoke tests pass. **9 browser journeys** pass against the production standalone frontend and real API/DB/
  worker with a controlled HTTP model provider. Ready, blocked and unavailable briefs are covered,
  including accessibility. TypeScript, ESLint, Prettier and production build pass.
- Reviewed the rendered approval screen and refreshed actual desktop/mobile screenshot evidence.
  These controlled-model results demonstrate software behavior; live-model quality remains unmeasured.
- Remaining: EvalRAG frontend, live-provider benchmark runs, Docker/deployment/release verification,
  demo GIF and final two-project acceptance audit. No remote push or deployment performed.
