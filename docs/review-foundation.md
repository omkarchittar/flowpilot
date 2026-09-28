# Backend foundation review — 2026-09-28

An independent reviewer inspected the implemented code, excluding explicitly pending
product APIs, worker runners and frontend. The initial review requested changes.

## Findings and disposition

- **Lease expiry sampled before blocking row lock (both projects): fixed.**
  Tests hold the job row lock past expiration and verify completion, heartbeat and
  failure all reject the stale lease. Each reproduced the issue before the fix.
- **Cached approver authority (FlowPilot): fixed.** Tests revoke the persisted user
  while the identity-map object remains active, then verify decision/execution are
  rejected. Approval, revision and execution now refresh and lock the actor row.
- **PDF expansion before size check (EvalRAG): fixed.** A compressed PDF with repeated
  content-stream references reproduced uncontrolled parent-process expansion.
  Parsing now runs out of process; incremental stream traversal precedes concatenation.
  Linux enforces a 512 MiB address-space limit. All supported hosts use a 512 MiB
  child-RSS monitor, five CPU seconds and a ten-second wall timeout. RSS monitoring is
  sampled and complements, rather than replaces, Linux's hard allocation limit.
- **Excessive overlap amplifies embedding cost (EvalRAG): fixed.** Chunk construction
  rejects documents exceeding 2,000 chunks or 250,000 cumulative embedding tokens.
  The full chunk plan is validated before any provider request is made.
- **Embedding model identity ignored (EvalRAG): fixed.** Wrong and missing provider
  model identities now fail response validation, even when dimensions match.

All applicable regressions and the complete current suites passed after fixes.
No minor findings were deferred. This review covers the implemented foundation;
it does not certify pending milestones or a production deployment.
