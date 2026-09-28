# FlowPilot

A vendor onboarding system with deterministic validation, revision-bound human approvals and auditable execution.

**Status: workflow backend and reliability benchmark implemented; frontend/release work in progress.**
The product APIs are usable through OpenAPI or an API client. The frontend and measured live-model
benchmark/release package are still in progress.

## Implemented and verified

- Cookie sessions with CSRF protection, hashed API tokens, database-backed login throttling and administrative account management.
- Encrypted, idempotent multipart intake, strict-schema AI classification/extraction and source-quote verification.
- Durable processing and execution workers, bounded revisions, approval APIs and paginated audit verification.
- Explicit workflow state graph and deterministic vendor policy validation.
- Requester/reviewer/approver/admin decision rules, including prevention of self-approval.
- Revision-bound approvals and revalidation immediately before side effects.
- Transactional vendor registry and in-app notifications with replay-safe execution.
- Sequenced, hash-chained audit events; PostgreSQL prevents event/approval/tool-receipt mutation.
- Encrypted sensitive payloads, keyed tax-ID fingerprints, salted password hashing and redaction.
- PostgreSQL job queue with SKIP LOCKED claims, expiring leases, backoff and stale-worker fencing.
- FastAPI liveness/readiness, structured request logs, correlation IDs and Prometheus metrics.
- Alembic migrations, reproducible dependency locks, non-root Dockerfile and backend CI definition.
- [102 named workflow scenarios and a 32-request extraction benchmark](benchmarks/README.md), with reproducible CLI reports and CI artifact generation.

Current local verification: **271 tests pass with PostgreSQL 17**, including the complete 102-scenario benchmark. Live model
accuracy, Docker image builds and the final release presentation remain unverified.

### Measured workflow contract results

These are controlled scenario results on PostgreSQL, not model accuracy or production reliability.

| Observation | Result |
| --- | ---: |
| Expected workflow outcomes | 102 / 102 |
| Independent approvals before sensitive effects | 10 / 10 effects |
| Duplicate vendor creations under replay tests | 0 |
| Audit integrity and completeness | 102 / 102 scenarios |
| Injected transient cases recovered | 4 / 6; the other 2 intentionally exhaust retries |

See the [saved scenario report](benchmarks/results/workflow-contracts.json) and
[benchmark method and commands](benchmarks/README.md) for denominators and limitations.
Live extraction measurements will be published separately; authored labels and contract fixtures
are not presented as model-generated benchmark scores.

## Architecture

See [architecture and tradeoffs](docs/architecture.md) for the component diagram,
relational invariants and security/reliability design. The [source PRD](docs/PRD.md)
is preserved from the supplied Word document. The [implementation plan](docs/implementation-plan.md)
tracks the complete scope and evidence.

## Run the current backend with Docker

Requires Docker Compose. From the repository root:

```sh
cp .env.example .env
# Set a local PostgreSQL password and provider key in .env.
# Generate FLOWPILOT_ENCRYPTION_KEY as described below before starting.
docker compose up --build
```

Open `http://localhost:8001/docs` for the current API schema.
`/health/live` checks the process; `/health/ready` checks the database and migration
version table; `/metrics` exports request counts and latency histograms. Ports bind
only to localhost. Keep `/metrics` internal behind the deployment gateway.

Compose starts PostgreSQL, runs the migrations as a separate one-shot service and
then starts the API and a separate durable worker. The frontend is not yet included.

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

## Accounts and worker configuration

Generate a Fernet key with the installed backend environment and save it as
`FLOWPILOT_ENCRYPTION_KEY` in `.env` (Compose) or `backend/.env` (native):

```sh
backend/.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

Keep this key stable and backed up with restricted access: existing encrypted requests
and tax fingerprints depend on it. Key rotation requires a data migration, not a new
random key on each startup. Compose requires it before launching services.

Create the first administrator using the interactive password prompt:

```sh
docker compose exec api python -m flowpilot.cli create-user --email admin@example.com --name Admin --role admin
# Native equivalent, from backend:
.venv/bin/python -m flowpilot.cli create-user --email admin@example.com --name Admin --role admin
```

Use `POST /api/auth/token` for API-client authentication or `/api/auth/login` for an
HttpOnly browser session. Cookie mutations require an allowed `Origin` and the
returned `X-CSRF-Token`. Administrators can provision accounts at `/api/admin/users`.
There are no built-in passwords or open public signup. See [API usage](docs/api.md).

Run the worker in a second terminal with the same database and provider configuration:

```sh
cd backend
.venv/bin/python -m flowpilot.worker
# Process at most one eligible job and exit:
.venv/bin/python -m flowpilot.worker --once
```

Set `FLOWPILOT_OPENAI_API_KEY` for model calls. Missing credentials produce explicit
failed jobs; they do not return synthetic responses. Retryable provider errors use
bounded exponential backoff; lease loss prevents stale results from being committed.

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

Next.js frontend; browser tests; live-provider extraction measurements; release pipeline; screenshots and demo GIF.

The final release will include measured benchmarks, an interactive frontend,
architecture/state diagrams, screenshots, a demo GIF, deployment instructions and
an explanation of failure cases and design decisions.
