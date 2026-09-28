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

- [ ] Deliverable: `config.py, db.py, models.py, security.py, migrations`.
- [ ] Behavior evidence: State, policy, role, redaction and relational constraints have behavior tests; migrations run on PostgreSQL.
- [ ] Run the backend suite (`.venv/bin/pytest`) and relevant integration/browser checks.
- [ ] Commit the verified increment and record evidence below.

### 2. Ingestion and AI extraction

- [ ] Deliverable: `documents.py, providers.py, api.py`.
- [ ] Behavior evidence: Bounded uploads and strict schema validation; supported/unsupported request classification; extracted fields require source evidence.
- [ ] Run the backend suite (`.venv/bin/pytest`) and relevant integration/browser checks.
- [ ] Commit the verified increment and record evidence below.

### 3. Durable workflow and approvals

- [ ] Deliverable: `orchestration.py, worker.py, tools.py, audit.py`.
- [ ] Behavior evidence: Revision-bound approvals, append-only events, concurrent claims, retry exhaustion, idempotent vendor creation and notification outbox.
- [ ] Run the backend suite (`.venv/bin/pytest`) and relevant integration/browser checks.
- [ ] Commit the verified increment and record evidence below.

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
