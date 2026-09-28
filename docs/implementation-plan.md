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

- [ ] Deliverable: `api.py, tests/, benchmarks/`.
- [ ] Behavior evidence: RBAC and ownership enforced through HTTP; at least 100 scenarios; extraction accuracy and zero duplicate side effects reported honestly.
- [ ] Run the backend suite (`.venv/bin/pytest`) and relevant integration/browser checks.
- [ ] Commit the verified increment and record evidence below.

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
