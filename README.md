# FlowPilot

A vendor onboarding system with deterministic validation, revision-bound human approvals and auditable execution.

**Status: backend, workflow benchmark and operations console implemented; release verification in progress.**
The console supports request intake, revisions, human decisions, audit inspection, inbox and team access.
Live-model measurements and the final release package remain in progress.

## Implemented and verified

- Cookie sessions with CSRF protection, hashed API tokens, database-backed login throttling and administrative account management.
- Encrypted, idempotent multipart intake, strict-schema AI classification/extraction and source-quote verification.
- Durable processing and execution workers, bounded revisions, approval APIs and paginated audit verification.
- AI review briefs generated from redacted policy facts, with revision fencing, model provenance and independent retries. Summary failures do not change approval authority.
- Explicit workflow state graph and deterministic vendor policy validation.
- Requester/reviewer/approver/admin decision rules, including prevention of self-approval.
- Revision-bound approvals and revalidation immediately before side effects.
- Transactional vendor registry and in-app notifications with replay-safe execution.
- Sequenced, hash-chained audit events; PostgreSQL prevents event/approval/tool-receipt mutation.
- Encrypted sensitive payloads, keyed tax-ID fingerprints, salted password hashing and redaction.
- PostgreSQL job queue with SKIP LOCKED claims, expiring leases, backoff and stale-worker fencing.
- FastAPI liveness/readiness, structured request logs, correlation IDs and Prometheus metrics.
- Alembic migrations, reproducible dependency locks, non-root Dockerfile and backend CI definition.
- Responsive Next.js console with same-origin API proxy, in-memory CSRF tokens and server-enforced permissions.
- Browser journeys against actual FastAPI/PostgreSQL and the production standalone frontend.
- [102 named workflow scenarios and a 32-request extraction benchmark](benchmarks/README.md), with reproducible CLI reports and CI artifact generation.

Current local verification: **292 backend tests pass with PostgreSQL 17 and 9 browser journeys pass**,
including the complete 102-scenario benchmark. Type checking, lint, formatting and the standalone
production build pass. The same nine browser journeys also pass against the Linux/arm64 Docker Compose stack. Live model accuracy and remote publication remain unverified.

## Console preview

![FlowPilot operations overview](docs/screenshots/overview-desktop.png)

[Approval screen](docs/screenshots/review-desktop.png) · [Audit trail](docs/screenshots/audit-desktop.png) ·
[Mobile requests](docs/screenshots/requests-mobile.png)

Screenshots show fictional browser fixtures on the real application stack; displayed model receipts
are controlled responses. See [capture provenance](docs/screenshots/README.md).

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

## Product walkthrough

![Recorded FlowPilot walkthrough](docs/demo.gif)

Fictional vendor documents and a controlled local model fixture. The recording shows independent human approval, durable execution and the audit trail. [Recording provenance and regeneration](docs/demo.md).

## Architecture

```mermaid
flowchart LR
  UI[Next.js operations console] --> API[FastAPI / RBAC]
  API --> DB[(PostgreSQL)]
  DB --> Worker[Leased job worker]
  Worker --> AI[Classification / structured extraction]
  Worker --> Rules[Deterministic policy validation]
  Rules --> Approval[Persisted human approval]
  Rules --> Brief[Queued advisory AI review brief]
  Brief --> UI
  Approval --> Tools[Allowlisted idempotent tools]
  Tools --> Registry[Vendor registry / notification outbox]
  Worker --> Audit[Append-only redacted audit events]
```

See [architecture and tradeoffs](docs/architecture.md) for the component diagram,
relational invariants and security/reliability design. The [source PRD](docs/PRD.md)
is preserved from the supplied Word document. The [implementation plan](docs/implementation-plan.md)
tracks the complete scope and evidence. The [acceptance audit](docs/acceptance.md) maps each required capability to implementation and verification, with open release gates kept explicit. The [deployment and security runbook](docs/deployment.md)
covers HTTPS, secret handling, worker recovery, backups and trust boundaries.

## Workflow state machine

```mermaid
stateDiagram-v2
  [*] --> RECEIVED
  RECEIVED --> CLASSIFYING
  CLASSIFYING --> EXTRACTING
  CLASSIFYING --> NEEDS_MANUAL_REVIEW
  EXTRACTING --> VALIDATING
  EXTRACTING --> NEEDS_MANUAL_REVIEW
  VALIDATING --> NEEDS_INFORMATION
  VALIDATING --> PENDING_APPROVAL
  VALIDATING --> NEEDS_MANUAL_REVIEW
  NEEDS_INFORMATION --> CLASSIFYING
  NEEDS_INFORMATION --> REJECTED
  PENDING_APPROVAL --> EXECUTING
  PENDING_APPROVAL --> REJECTED
  PENDING_APPROVAL --> NEEDS_INFORMATION
  PENDING_APPROVAL --> NEEDS_MANUAL_REVIEW
  EXECUTING --> COMPLETED
  EXECUTING --> NEEDS_MANUAL_REVIEW
  NEEDS_MANUAL_REVIEW --> CLASSIFYING
  NEEDS_MANUAL_REVIEW --> REJECTED
  COMPLETED --> [*]
  REJECTED --> [*]
```

This shows every allowed transition from the [domain state model](backend/src/flowpilot/domain.py).
Each command also checks role, ownership, revision and policy. Moving from approval to
execution requires an independent authorized decision for the current revision. Revisions
restart classification and invalidate old approval. Terminal workflows cannot be reopened.

## Engineering decisions and limits

A custom state machine keeps transitions and authority visible in ordinary Python.
The model proposes structured facts; deterministic policy and human approval authorize
side effects. Vendor creation, its idempotency receipt and audit event commit together.
Advisory AI briefs have their own retries and cannot approve or block valid execution.

The v1 integration is a persisted vendor registry and in-app notification outbox.
There is no claimed ERP or email delivery. Source quotes establish provenance, not the
truth of a business document; reviewers still assess the evidence. The deployment
runbook covers encryption-key backup and the database administrator trust boundary.
[Failure analysis](docs/failure-analysis.md) explains tested failures and live-model limits.

## Run with Docker

Requires Docker Compose. From the repository root:

```sh
cp .env.example .env
# Set a local PostgreSQL password and provider key in .env.
# Generate FLOWPILOT_ENCRYPTION_KEY as described below before starting.
docker compose up --build
```

Open `http://localhost:3001` for the console and `http://localhost:8001/docs` for the API schema.
`/health/live` checks the process; `/health/ready` checks the database and migration
version table; `/metrics` exports request counts and latency histograms. Ports bind
only to localhost. Keep `/metrics` internal behind the deployment gateway.

Compose starts PostgreSQL, runs the migrations as a separate one-shot service and
then starts the API, a separate durable worker and the frontend. The frontend image bakes in the
internal API address at build time. Local Linux/arm64 Docker verification passes the complete nine-journey browser suite.

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

For the console, run `npm ci && npm run dev` from `frontend/`, then open
`http://localhost:3001`. See [frontend setup and browser tests](frontend/README.md) for
standalone production builds, proxy configuration and accessibility checks.

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

## Remaining release verification

Live-provider extraction measurements, an executed GitHub release and public
deployment remain pending. Local Linux/arm64 container verification passes all nine
browser journeys. The interactive frontend, architecture/state
diagrams, screenshots, demo GIF, benchmark harness, deployment instructions and
quality-gated image publishing workflow are implemented. See the
[implementation ledger](docs/implementation-plan.md) for verified evidence and limits.
