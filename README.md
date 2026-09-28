# FlowPilot

A vendor onboarding system with deterministic validation, revision-bound human approvals and auditable execution.

**Status: backend foundations implemented; product development in progress.**
This repository is not yet the complete portfolio release. The only HTTP endpoints
currently exposed are operational endpoints. Domain services are exercised through tests.

## Implemented and verified

- Explicit workflow state graph and deterministic vendor policy validation.
- Requester/reviewer/approver/admin decision rules, including prevention of self-approval.
- Revision-bound approvals and revalidation immediately before side effects.
- Transactional vendor registry and in-app notifications with replay-safe execution.
- Sequenced, hash-chained audit events; PostgreSQL prevents event/approval/tool-receipt mutation.
- Encrypted sensitive payloads, keyed tax-ID fingerprints, salted password hashing and redaction.
- PostgreSQL job queue with SKIP LOCKED claims, expiring leases, backoff and stale-worker fencing.
- FastAPI liveness/readiness, structured request logs, correlation IDs and Prometheus metrics.
- Alembic migrations, reproducible dependency locks, non-root Dockerfile and backend CI definition.

Current local verification: **115 tests pass against PostgreSQL 17**. This count includes unit, HTTP and database tests; it is not a claim that
the final PRD benchmark/scenario requirements have been completed. Live provider calls
and Docker image builds have not yet been verified in this environment.

## Architecture

See [architecture and tradeoffs](docs/architecture.md) for the component diagram,
relational invariants and security/reliability design. The [source PRD](docs/PRD.md)
is preserved from the supplied Word document. The [implementation plan](docs/implementation-plan.md)
tracks the complete scope and evidence.

## Run the current backend with Docker

Requires Docker Compose. From the repository root:

```sh
cp .env.example .env
# Set a local PostgreSQL password in .env.
docker compose up --build
```

Open `http://localhost:8001/docs` for the current API schema.
`/health/live` checks the process; `/health/ready` checks the database and migration
version table; `/metrics` exports request counts and latency histograms. Ports bind
only to localhost. Keep `/metrics` internal behind the deployment gateway.

Compose starts PostgreSQL, runs the migrations as a separate one-shot service and
then starts the API. It does not yet launch the planned workers or frontend.

## Native development

Use Python 3.12+ and PostgreSQL 17.
Create a dedicated database and user, then:

```sh
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.lock
.venv/bin/pip install --no-deps -e .
export FLOWPILOT_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@localhost:5432/flowpilot'
.venv/bin/alembic upgrade head
.venv/bin/uvicorn flowpilot.app:create_app --factory --reload --port 8001 --no-access-log
```

Secrets belong in environment variables or a git-ignored `backend/.env` for native
runs. Never commit API keys, encryption keys or real business documents.

## Verify changes

Point `TEST_DATABASE_URL` at a separate test database, never a live database:

```sh
export TEST_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@localhost:5432/flowpilot_test'
./scripts/check.sh
```

The script checks formatting/lint, upgrades migrations, checks schema drift, and runs
the suite. Database tests skip explicitly if `TEST_DATABASE_URL` is absent; a run
without it does not verify PostgreSQL behavior. CI supplies PostgreSQL and also
checks migration downgrade/upgrade and Docker image compilation.

Test fixture provider responses are controlled HTTP responses used to exercise
adapter contracts. They are not fabricated live model quality results.

## Next milestones

Authenticated ingestion and approval APIs; evidence-verified AI extraction; document ingestion; worker runner and recovery orchestration; extraction/reliability benchmark suite; Next.js frontend; browser tests; release pipeline; screenshots and demo GIF.

The final release will include measured benchmarks, an interactive frontend,
architecture/state diagrams, screenshots, a demo GIF, deployment instructions and
an explanation of failure cases and design decisions.
