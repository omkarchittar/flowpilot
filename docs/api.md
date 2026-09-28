# Current backend API

The OpenAPI schema at `/docs` is the authoritative request/response reference.
The implemented workflow is vendor onboarding; invoice and contract requests are
classified and routed to manual review rather than executed as vendor requests.

## Authentication and roles

Bootstrap an administrator with `python -m flowpilot.cli create-user`. The CLI reads
a hidden password prompt; `--password-env` names a variable for automated bootstrap.
Administrators provision users through `/api/admin/users`. Roles are requester,
reviewer, approver and admin. Requesters can read their own workflows. Reviewer,
approver and admin accounts can read the shared review queue. Approval requires an
approver or admin who is not the requester. A reviewer can request changes.

`POST /api/auth/token` accepts email/password and returns an opaque bearer token.
Use `Authorization: Bearer TOKEN` for API clients. Browser clients use
`/api/auth/login` and its HttpOnly, SameSite=Strict cookie. Cookie mutations require
an allowed `Origin` and the returned `X-CSRF-Token`; `/api/auth/me` refreshes client
session information. `/api/auth/logout` revokes the current session. Only token
hashes are stored. Default session life is 12 hours. Disabling a user or changing
their role revokes their sessions, and execution checks approver authority again.

Configure `FLOWPILOT_ALLOWED_ORIGINS` as a JSON array and use
`FLOWPILOT_ENVIRONMENT=production` behind HTTPS for Secure cookies. Login throttling
is database-backed by account and client IP. Only trust forwarded IP headers from
your own proxy; use gateway rate limiting for deployment-wide abuse control.

## Submit and process

`POST /api/workflows` accepts multipart `title`, `request_text` and optional repeated
`files` fields. `POST /api/intake` accepts JSON title/request_text for incoming-request
simulation without attachments. Both require `Idempotency-Key` (8–200 permitted
ASCII characters). Replaying identical content under the same key returns the same
workflow; changing content under that key returns 409.

Files may be PDF, UTF-8 TXT or Markdown. Intake stores encrypted originals and
extracted text, a request audit event and a processing job in one transaction.
Each revision allows at most 20 distinct documents within the configured aggregate
upload limit (10 MB by default). PDF parsing has independent CPU/memory/decoded-data
limits. Scanned PDFs require OCR before submission.

The worker classifies the request, extracts strict-schema fields with document
quotes, verifies each quote against the supplied source, then runs deterministic
validation and duplicate checks. Unsupported types and uncertain classification
route to manual review. Missing information routes back for revision. Required
fields, evidence, document types, confidence, email/tax-ID format and insurance
validity must pass before the request reaches `PENDING_APPROVAL`.

Quotes establish source membership, not semantic correctness. Human review remains
mandatory, and structured model output is never authority to execute side effects.
Provider model/usage/latency and prompt versions are recorded. Provider calls run
outside DB transactions; current revision and lease ownership are checked on return.

## Review and execution

- `GET /api/workflows` lists visible workflows with status filtering and pagination.
- `GET /api/workflows/{id}` returns candidate fields, validation, documents and
  decisions. Tax IDs are masked; raw request text is not included in the read model.
- `GET /api/documents/{id}/download` returns an authorized original attachment.
- `POST /api/workflows/{id}/decisions` accepts `revision`, `decision`
  (`approve`, `reject`, `request_changes`) and `comment`.
- `POST /api/workflows/{id}/revisions` accepts multipart `revision`, `request_text`
  and optional files. The requester or admin can revise requests needing information
  or manual review. Existing files are retained unless replaced by filename; all
  extraction and validation is recomputed and previous approval cannot carry over.

Approved execution revalidates policy, tax uniqueness and approver authority. Vendor
creation, tool receipts, in-app notification, audit and completion commit atomically.
The notification tool writes the local inbox; it does not send email. Failed jobs
retry only when classified transient, within the persisted attempt budget. Permanent
errors and exhausted retries route to manual review, where a new revision can resume
processing with corrected inputs/configuration.

`GET /api/workflows/{id}/audit?after=0&limit=100` returns ordered hash-chained events.
Continue with `next_cursor` while `has_more` is true. `verified` explicitly covers
only the returned page against `anchor_hash`; a client verifying the full stream
must carry the final hash from one page into the next, beginning at genesis.
Database triggers prevent event mutation. This is tamper evidence within the database,
not an externally signed transparency log.

`GET /api/overview` reports persisted state counts. `/api/notifications` lists the
current user's inbox; POST `/api/notifications/{id}/read` marks an item read.

## Operations and sensitive data

Use the same stable Fernet key for API and workers. Back up it separately from the
DB with restricted access; changing it requires migrating encrypted data and tax
fingerprints. Requests, extracted candidate payloads and attachments are encrypted
at rest at the application layer. Titles, decision comments, contact details in the
vendor registry and notification messages are not encrypted application fields;
avoid putting tax IDs or banking details in titles/comments.

`/health/live`, `/health/ready` and `/metrics` cover API operations. Keep metrics
internal at your gateway. Logs omit raw documents, prompts, credentials and tax IDs.
The automated suite uses controlled provider responses; it does not claim measured
live model accuracy or final release benchmark coverage.


## AI review brief

Workflow detail includes nullable `review_brief`. New processed workflows have a persisted
`status` (`pending`, `complete`, `failed`), `fingerprint` and redacted `context` with revision,
source workflow state, assessment and issue IDs. Complete briefs add `result` (plain-text
`summary`, matching `assessment`, exact `issue_refs`), `metadata` (model, tokens, latency,
prompt version/fingerprint) and `generated_at`. Failed briefs expose a stable `error_code`.
Existing workflows migrated from an earlier version may have no brief until their next
processing/revision. No caller-provided brief can authorize a decision or vendor creation.

A brief describes the recorded context, not a fresh policy check. Approval and execution
revalidate independently. Changing the request clears the current brief; human changes requests
and execution blocks queue a replacement. Raw source text and decision comments are not supplied
to summary generation. All workflow-detail ownership and role checks apply to this data.
