# Benchmark increment review

Reviewed against local base `9eb16c6`, 2026-09-28. Independent re-review approved the final corrections.

| Finding | Resolution and regression evidence |
| --- | --- |
| Failed observations disappeared from reliability aggregates | Aggregate all unique expected observations. Retain known duplicates, mark incomplete totals unknown with coverage, and use manifest-defined retry denominators. A regression with a duplicate, unauthorized extra effect and failed recovery verifies 1 duplicate, 10/11 approval coverage and 3/6 recovery. |
| A valid audit hash chain did not establish event completeness | Verify state continuity and correlate approvals and sensitive tool receipts to events. Four sabotage tests suppress decision/vendor/notification/state emissions and require detection. |

The final check script passed 271 tests with actual PostgreSQL. The named 102-scenario report passed
with complete coverage. A separate controlled HTTP smoke exercised the extraction CLI's full bundle,
provider metadata and unsupported-value measurement. No live-model accuracy is claimed from these
fixtures. No material review finding was deferred.
