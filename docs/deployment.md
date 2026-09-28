# Deployment and operations

The repository provides nonroot API/worker and frontend images and a local Compose stack.
Both images build and all nine browser journeys pass against the local Linux/arm64
Compose stack, including migrations, the separate worker and containerized PostgreSQL.
The model endpoint uses controlled fictional fixtures, which verifies packaging and
service integration. Live-provider measurements, amd64 execution, remote image publication
and public HTTPS deployment remain unverified.

## Configuration and startup

1. Provision PostgreSQL 17, a durable volume and separate restricted runtime credentials.
2. Store a stable Fernet key, database URL and model API key in your deployment's secret
   store. Back up the encryption key with access control; losing it makes existing
   requests unreadable. Do not place provider credentials in frontend build arguments.
3. Build the frontend with `FLOWPILOT_API_URL` pointing at the API's internal service URL.
   This is a build-time setting, not runtime browser configuration. Only `/api` is proxied.
4. Set the API/worker `FLOWPILOT_ENVIRONMENT=production` and
   `FLOWPILOT_ALLOWED_ORIGINS=["https://YOUR-CONSOLE-HOST"]`. Serve the console over HTTPS.
   Secure cookies will not work over plain HTTP in production mode. Keep API/worker
   configuration and encryption keys identical.
5. Run `alembic upgrade head` once before starting API and workers. Start the worker as
   a separate long-running service; allow 60 seconds for graceful shutdown. Start the
   frontend after API readiness succeeds. Bootstrap the first administrator interactively.
6. Verify login, a representative upload, independent approval, execution and inbox in
   a nonproduction environment before accepting real documents.

The sample Compose ports bind to localhost and use development cookie settings. Put
an HTTPS ingress in front of the console for remote access. Keep PostgreSQL, internal
API operations and `/metrics` off the public network. Permit request bodies up to the
configured attachment limit plus 1 MB multipart overhead at the ingress; the application
supports at most 50 MB of attachments and enforces smaller configured limits.

## Checks and diagnosis

- API `/health/live`: process response. `/health/ready`: database and migration table.
- Frontend `/login`: standalone server and static assets. This alone does not prove model
  credentials or worker execution; run a controlled workflow as a deployment smoke check.
- `/metrics`: HTTP counts and latency, with request IDs in structured API logs.
- Workflow detail: persisted model receipts, validation and status. Audit view: immutable
  events with page-scoped hash verification, including retry/failure and tool outcomes.
- Pending work: check the worker process, provider configuration, lease/retry state and
  database reachability. Processing/execution failures back off when transient;
  exhausted/permanent failures become manual review. Advisory brief failures instead mark the
  brief unavailable and leave workflow authority unchanged. Do not create vendor rows directly or bypass approval to clear a queue.

Login throttling currently uses the ASGI peer address. When a Next proxy is the only API
client, its address is shared by browser users. The account limit still applies separately;
size deployment expectations around the shared IP limit, and only add trusted forwarded-IP
handling with explicit ingress configuration and spoofing tests.

## Access and data handling

Requester scope is their own workflows. Reviewers inspect and request changes. Approvers
and administrators may approve, but never their own request. Role/access changes revoke
sessions; decisions and execution check current authority. The UI is not an authorization
boundary. Passwords are provisioned through an administrator, not public signup.

Never log prompts, request bodies, file contents, raw tax IDs or credentials. Audit payloads
are allowlisted and redacted. Uploaded source documents can contain sensitive values and
are available only through authorized downloads; masked UI fields do not sanitize those
source files. Notifications stay in the product; no email delivery is claimed.

Approval and audit rows are append-only. Hash chains detect application-level corruption
and missing events when checked against the workflow contract. A database administrator
can bypass database protections; these chains are not an external notarization system.

## Backup and rollback

Back up PostgreSQL and the encryption key separately, then rehearse restoring both into
an isolated environment. Restore tests should verify a document decrypts, the audit chain
is valid and existing vendor fingerprints still prevent duplicates. Apply a retention
policy appropriate to the uploaded business documents.

Before an upgrade, back up the database and pin image versions. Prefer rolling back code
with compatible migrations; do not run destructive migration downgrades against live data.
Database migration roundtrips in CI use disposable databases. Stop workers during an
incompatible migration and let current leases expire before recovery. Replaying an approved
execution retains its idempotency key; never invent a new key to retry a completed effect.

## Versioned image publishing

The `Publish verified images` workflow starts on a pushed `v*` tag. It calls the complete quality workflow for that exact tagged commit before publishing API and console images to GHCR. API and worker use the same image. Publishing has package-write permission only in the publishing job; pull-request CI remains read-only. Actions in the publishing job are commit-pinned. Images include source/revision metadata, BuildKit provenance and SBOMs, and are built for Linux amd64/arm64. No mutable `latest` tag is created.

The workflow uses GitHub's documented [reusable workflow](https://docs.github.com/en/actions/how-tos/reuse-automations/reuse-workflows) and [container publishing](https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images) mechanisms. The definitions have been locally checked; successful remote publishing still needs execution evidence.

After a successful tag run, copy each image digest from its job summary into the deployment secret/environment configuration:

```sh
export FLOWPILOT_API_IMAGE='ghcr.io/OWNER/flowpilot-api@sha256:API_DIGEST'
export FLOWPILOT_CONSOLE_IMAGE='ghcr.io/OWNER/flowpilot-console@sha256:CONSOLE_DIGEST'
docker compose -f compose.yaml -f compose.release.yaml pull
docker compose -f compose.yaml -f compose.release.yaml up --no-build -d
```

The release override intentionally keeps the same migrations, health checks, environment, volumes and worker wiring as local Compose. Set actual digest values; the placeholders above are documentation, not runnable image references. Tag names can be moved by repository writers, so deploy by digest and protect release tags in repository settings. For rollback, retain the previous digest pair and confirm schema compatibility before replacing services. If a matrix publication fails after one image is pushed, do not deploy that partial release; require the whole workflow to succeed.

Public HTTPS infrastructure and deployment credentials are environment-specific and are not provisioned by image publication. A registry upload is not evidence of a running deployment.
