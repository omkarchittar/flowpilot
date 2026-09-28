# AI review brief

Complete the PRD approval experience with actual model-generated prose explaining why a
request is ready for independent review or blocked. The brief is advisory and never grants
approval, changes validation results or executes a tool.

Use the existing durable queue after classification/validation and when human changes or
execution revalidation introduce a block. Store a bounded redacted context and its SHA-256
fingerprint with the current revision. The provider receives only policy results, issue
codes/messages and workflow classification, never raw requests, documents or field values.
Strict output schema requires a matching assessment and complete, exact issue references.
Free-form prose remains model output; the UI labels it advisory beside the authoritative
validation and decision history.

Provider IO occurs outside transactions. Final publication verifies lease ownership,
revision and context fingerprint. Superseded jobs complete without publishing. Retryable
errors use existing bounded backoff; exhaustion is explicit in the brief and audit but does
not change workflow authority. Reconcile expired final leases so the UI cannot remain pending
forever. Reset the brief on revision; every model result records usage/prompt provenance and
an output digest in immutable audit, not free-form text in logs.

Verify schema/context fidelity, no sensitive inputs, actual provider metadata, both readiness
outcomes, stale revision/context/lease rejection, retries and exhaustion, unchanged approval
and side-effect invariants, API ownership and browser presentation. Run PostgreSQL suite,
migration upgrade/downgrade/schema check, browser suite and independent review before commit.
