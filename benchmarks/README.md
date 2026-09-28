# FlowPilot benchmarks

Two separate evidence sources cover different questions:

- **Workflow contracts:** 102 named scenarios run the actual intake, worker, approval, execution and
  audit services against PostgreSQL. The model responses are controlled fixtures. These test software
  invariants, not model accuracy or production failure rates.
- **Classification and extraction:** 32 authored requests, including 20 vendor cases with field and
  document labels. The CLI calls the configured model adapter and measures its actual observations.
  All companies, people, identifiers and documents in the bundle are fictional.

## Workflow scenarios

`scenarios.json` gives every case a stable ID, expected state and explicit parameters. Its date is
fixed for reproducible insurance-policy boundaries; this clock override exists only in the tests.

| Family | Cases | Behavior exercised |
| --- | ---: | --- |
| Classification | 12 | Four request types at confidence below, at and above the threshold |
| Field evidence | 20 | Five fields with missing values, unknown sources, invented quotes or low confidence |
| Document evidence | 12 | Three required document kinds with absent/unverified/request-only/low-confidence classifications |
| Field formats | 11 | Invalid tax identifiers and contact emails |
| Insurance expiry | 7 | Expired, immediate and 29/30/31-day boundary cases |
| Human decisions | 24 | Four roles × three decisions × own/other request |
| Provider recovery | 8 | Classification/extraction transient recovery, exhaustion and permanent failure |
| Replayed execution | 3 | One, five and twenty repeated executions after approval |
| Replayed intake | 3 | Identical input, reordered attachments and conflicting payload |
| Revoked authority | 2 | Disabled or downgraded approver before execution |
| **Total** | **102** | |

Every scenario checks expected state, vendor/notification counts, approval linkage, tool receipts
and audit integrity **and completeness**. Audit assertions match approvals and sensitive receipts to
recorded events and verify state continuity through the final persisted status. Separate sabotage
tests deliberately suppress decision, vendor, notification and state events and must detect each
omission. Other tests cover stale revisions, PostgreSQL uniqueness, independent concurrent claims,
lease expiry, HTTP ownership/RBAC and encrypted/redacted storage.

From the repository root, with an isolated, migrated PostgreSQL test database:

```sh
export TEST_DATABASE_URL='postgresql+psycopg://USER:PASSWORD@localhost:5432/flowpilot_test'
backend/.venv/bin/pytest backend/tests/test_scenarios.py -q \
  --junitxml=.data/scenarios.xml -o junit_family=xunit1
backend/.venv/bin/python -m flowpilot.benchmark scenarios-report .data/scenarios.xml \
  --output .data/scenario-report.json
```

The report checks all manifest IDs appear exactly once, with complete observations and no skipped
or failing cases. Exit status is 0 only when the complete scenario gate passes, 1 for failed or
incomplete evidence, and 2 for a malformed/unreadable input. Failed cases do not disappear from
measurements: incomplete totals become null with coverage, known duplicates remain visible, and the
retry denominator includes all six injected transient cases, including the two deliberately exhausted
ones. The eight provider scenarios also include two permanent failures which are not retry candidates.

A full-suite JUnit file is accepted; unrelated tests are excluded from the 102-case report. CI runs
this gate and publishes its JSON with test results. `scripts/check.sh` produces equivalent local
artifacts under `.data/`. Workflow fixtures use savepoint-isolated PostgreSQL transactions; they do not
model production load, external network reliability or durability across a database restart.

## Classification and extraction

`extraction.json` contains request text, explicit source IDs, five reference fields (null when missing
or ambiguous), expected document classifications and tags. The manifest records the bundle checksum.
The vendor cases include varied layouts, missing fields/documents, request-only evidence, non-ISO
dates, conflicting identifiers and instructions embedded in otherwise useful source text. The other
12 requests cover invoice review, contract requests and unknown intents.

Set the same `FLOWPILOT_OPENAI_API_KEY`, model and optional provider URL used by your application,
then run from the repository root:

```sh
backend/.venv/bin/python -m flowpilot.benchmark extract \
  --cases benchmarks/extraction.json --output .data/extraction-run.json
```

Settings load `.env` relative to the working directory. Alternatively run from `backend/` with
`--cases ../benchmarks/extraction.json` to use `backend/.env`. This command incurs actual configured
provider usage: 32 classification calls and up to 32 extraction calls depending on predicted routing.
It creates no workflow, vendor or notification, and makes no approval decisions.

The CLI checkpoints each completed observation atomically. An interrupted file remains marked
`running`; only the final report has `completed` status. Rerunning starts a new measurement, so use a
new output path to preserve earlier evidence. Errors remain in applicable denominators and produce
exit status 1 after reporting; invalid setup/input returns 2. Provider authenticity is not attested by
the CLI. Report hashes identify the dataset and endpoint; model metadata records actual response model,
prompt/schema fingerprint, stage latency and token usage. Reports omit request text, raw fields,
quotes and credentials; use case IDs to inspect the local authored source bundle.

### Metric definitions

- **Classification accuracy:** correct request types / all attempted cases, including provider errors.
  Per-type counts prevent the larger vendor group from hiding other classification failures.
- **Extraction coverage:** vendor-labeled cases with an extraction observation / all vendor cases.
  Production routing is preserved: non-vendor predictions and confidence below 0.85 skip extraction.
- **Raw field exact match:** exact matches / five fields across every vendor case. Null references can
  match null predictions only when extraction actually occurred. Values normalize Unicode, case and
  whitespace; tax identifiers additionally ignore spaces/hyphens. Dates follow the production adapter's
  ISO-evidence requirement. Correct paraphrases are not treated as exact matches.
- **Verified precision:** correct nonempty verified fields / all nonempty verified fields. A value
  present in a source but contrary to the human-authored label is still incorrect.
- **Required-field recall:** correct nonempty verified fields / nonempty reference fields. Missing,
  filtered and misclassified cases stay in this denominator. Per-field precision/recall is also exported.
- **Unsupported extracted-field rate:** raw nonempty predictions rejected by deterministic source,
  quote, value or date verification / all raw nonempty predictions. This is a provenance failure rate;
  it is not a semantic entailment score and cannot detect every misleading but verbatim source claim.
- **Document precision/recall:** matching `(source ID, document kind)` pairs against authored labels.
  An assertion that a request itself is an uploaded document is rejected by the production verifier.
- **Error/usage coverage:** failed cases remain visible. Tokens sum reported successful responses;
  usage on rejected/failed transport responses is unknown rather than assumed zero total consumption.

A high verified precision with low recall can mean filtering removed bad extractions. Read those
metrics together with raw exact match, unsupported rate and coverage. These compact authored cases
are not a representative production distribution. Review difficult cases manually and use unseen
examples before generalizing. Automated controlled-provider smoke tests validate the measurement
code; they are never substituted for a live-model accuracy report.
