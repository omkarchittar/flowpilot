# Failure analysis and measurement limits

The [saved workflow report](../benchmarks/results/workflow-contracts.json) measures controlled
software contracts on PostgreSQL. It is not a model-accuracy report or a production failure rate.
All 102 named scenarios produced their expected outcomes; many expected outcomes are blocked,
rejected or manually escalated workflows rather than completed vendor creation.

| Failure or ambiguity | Product response | Direct evidence |
| --- | --- | --- |
| A field has no source, an invented quote or low confidence | Remove unsupported extraction before deterministic validation; request information or escalate | `test_extraction.py`, field/document scenario families |
| A request is not vendor onboarding | Classify it, then route to manual review without executing vendor tools | `test_orchestration.py`, classification scenarios |
| A requester attempts self-approval, including as administrator | Reject approval; create no vendor | Domain decision matrix, 24 human-decision scenarios, browser journey |
| Fields change after review | Increment revision and invalidate old approval; stale decisions cannot authorize new input | `test_workflow_service.py`, revision-conflict browser journey |
| Transient provider errors persist | Retry with bounded backoff; exhaustion escalates visibly | Six injected transient scenarios: four recover and two intentionally exhaust |
| An approved execution is replayed | Reuse the payload-bound receipt and unique vendor fingerprint; create no duplicate vendor | One/five/twenty replay scenarios and PostgreSQL persistence tests |
| Approval authority is revoked before execution | Recheck authority immediately before side effects and block invalid execution | Disabled/downgraded approver scenarios |
| An advisory summary fails or arrives after a revision | Expose unavailability or discard stale output; preserve authoritative policy/approval state | `test_review_briefs.py` and unavailable-brief browser journey |
| An audit event is omitted | Completeness checks fail even if remaining hashes are internally consistent | Deliberate sabotage tests in `test_scenarios.py` |

The zero-duplicate result covers the tested transactions and replays, not every future external
integration. The current registry and notification outbox commit in PostgreSQL; an external ERP
or email transport would need its own delivery/reconciliation contract. Audit hashes and
append-only triggers do not protect against a privileged database administrator. Uploaded source
documents remain sensitive even when the field view masks tax identifiers.

Verbatim evidence is a provenance check, not proof that a document is authentic or its contents
are true. Model confidence is not calibrated probability. Human review and deterministic policy
remain necessary even if measured extraction accuracy is high.

## Required live report

Run the [classification/extraction CLI](../benchmarks/README.md) against the configured real
provider. Preserve the completed report with dataset/endpoint/prompt hashes, actual returned
model metadata, case IDs, usage coverage and timings. Publish classification accuracy by type,
raw field exact match, verified precision, required-field recall, unsupported extracted-field
rate, document precision/recall and error coverage. Review misclassification, ambiguous dates,
conflicting identifiers, missing evidence and adversarial cases by ID against the authored labels.

A high verified precision with low recall may mean filtering removed incorrect extractions.
Errors and skipped routing must remain in applicable denominators. No live accuracy number or
claim of representative production reliability is justified until actual measurements exist.
