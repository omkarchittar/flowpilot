# API and worker review — 2026-09-28

Scope: uncommitted API/authentication/durable-worker increment following the reviewed
foundation. Independent reviewer examined both projects with fresh context, then
reviewed fixes. Parent verified the following regressions against real PostgreSQL.

| Finding | Resolution | Evidence |
|---|---|---|
| FlowPilot accepted blank normalized document quotes | Require nonempty normalized source quote before accepting evidence | Whitespace, tabs/newlines and Unicode whitespace regressions |
| Bootstrap CLI validation printed raw invalid passwords | Catch validation errors and emit sanitized argument error | Subprocess tests assert password and traceback absent from output |
| PDF file-size configuration was lost at subprocess/worker boundaries | Pass byte budget to PDF subprocess and preserve admitted size for indexing under 50 MB ceiling | Actual >10 MB valid PDF admitted and indexed by separate worker |

Additional checks: combined revision attachment limits; page-level audit verification;
workspace isolation and role boundaries; token expiry/revocation, CSRF and login
throttling; approval revision/current authority; provider IO outside DB transactions;
lease fencing and retry exhaustion.

Final review assessment: **approved; no blocking findings remain**.
Current flowpilot suite: **155 passing tests**, no skipped PostgreSQL tests.
Provider responses in tests are controlled fixtures, not measured model quality.
Docker runtime and full release validation remain separate unfinished work.
