# P1–P7 implementation audit — 27 October 2026

Status: audit complete; eight findings fixed. Final regression: **737 passed,
0 failed, 0 errors, 0 skipped**. Scope: Jaineel-owned P1–P7 only. No commit, push,
shared-contract changes, fixture relabelling, or performance matrix execution.
Starting branch: `jaineel/j03-telemetry`; working tree clean.
Evidence root: `artifacts/p1-p7-audit/20261027-audit/` (ignored, local).
Base commit: `9f1013bb7f2cdec6e9b4caa407540c4b58b2ee88`.
Authority: [ownership](../OWNERSHIP.md), [common specification](../specs/02_COMMON_SPEC.md),
[evaluation](../specs/03_EVALUATION_SPEC.md), [Jaineel's brief](../specs/04_JAINEEL_VORA.md),
[source rules](../specs/08_DATASET_PROFILE_AND_RULES.md),
[runbook](../specs/09_EVALUATION_RUNBOOK.md), and [playbook](../specs/10_JAINEEL_CODEX_PLAYBOOK.md).

## Requirement-to-code/test checklist

| Milestone | Implementation inspected | Verification |
|---|---|---|
| P1 | `projectctl/{cli,config,models,providers,artifacts}.py`, application lock/CI | Clean locked Python 3.11 install; `tests/projectctl`; verifier P1; failure manifests and schema checks |
| P2 | `services/conversation/{clients,provider_contracts}.py`, common/conversation DTOs and OpenAPI | `tests/contracts`; verifier P2; deadlines, malformed responses, retries, identity and SSE |
| P3 | `benchmarks/{dataset_checks,fixtures,quality,reconciliation,metrics}.py` | `tests/oracles`, fixture/metric tests; verifier P3; corruption and denominator checks; preserve LLM adjudication provenance |
| P4 | `benchmarks/{workloads,scheduler,drivers,experiment,planning}.py` | `tests/benchmarks`; verifier P4; cutoff, cancellation, bounded queues and disposition accounting |
| P5 | `shared/telemetry`, `benchmarks/{collectors,observation,observation_summary}.py`, dashboards | `tests/telemetry`; verifier P5; gaps, stalls, clocks, manifest membership and offline evidence |
| P6 | Conversation state/database/app/events, conversation migrations | Real PostgreSQL `tests/conversation`; verifier P6; HTTP mutations, races, rollback, restart and isolation |
| P7 | Conversation intent/workflow/gateway | Workflow/intent tests, 60 frozen scenarios; verifier P7 and HTTP smoke; explicit confirmation, response loss and zero model calls |

## Findings and fixes

### F01 — High, P7: hard constraints silently dropped

- Requirement: common §6.2 and playbook P7 require explicit filters to survive
  parsing and ambiguity/unsupported constraints to trigger clarification.
- Location: `services/conversation/intent.py::extract_intent`.
- Reproduction: `clothing under 100 USD`, `clothing under 100 euros`,
  `clothing under 100 rupees and above 50 rupees`, repeated explicit size/colour/
  fabric cues with an unsupported value, and a valid bound followed by
  `below -5 rupees` returned `valid`. Seven initial failing cases are retained
  in `red-intent-oracle.xml`/`.log`. Repeated different single-letter sizes
  were also being reduced to the first cue.
- Root cause: the first explicit cue/recognized monetary clause was treated as
  sufficient even when later clauses were not understood. Single-letter size
  extraction collected only the first explicit size.
- Fix: inspect every explicit cue, collect all explicit sizes, account for
  monetary clauses, and clarify foreign currency/minimum-price constraints.
- Regression: expanded `tests/conversation/test_intent.py`; all original 60
  scenarios also rerun unchanged. No labels, hashes, or adjudication history
  were regenerated. Parsing remains deterministic and makes zero model calls.

### F02 — Medium, P2: conflicting SSE version ignored

- Requirement: common §5's versioned Orders snapshots and safe reconnects.
- Location: `services/conversation/clients.py::ProviderHTTP.events`.
- Reproduction: two valid snapshots for the same order/version with different
  statuses yielded the first and silently discarded the conflict
  (`red-sse.xml`/`.log`, one failed regression).
- Root cause: the cursor suppressed every repeated version without checking
  its immutable state.
- Fix: keep a defensive copy of the current snapshot and reject a conflicting
  repeated current version. Identical repeats and older-version suppression
  preserve existing reconnect behavior. Memory remains bounded to one snapshot.
- Regression: `test_sse_conflicting_current_version_is_not_silently_discarded`
  and the existing reconnect/corruption/deadline tests pass.
- Limit: a new stream cannot compare an unseen snapshot against an earlier
  process's payload from a cursor alone. Durable provider version integrity
  remains Aditya's responsibility.

### F03 — High, P3: warmup duplicate inflates measurement Gold goodput

- Requirement: evaluation §5.1 counts unique measurement-cohort logical events;
  warmup, physical duplicate traffic, and drain completions are distinct.
- Location: `benchmarks/metrics.py::cohort_rates`.
- Reproduction: warmup event at t=5, its duplicate at t=11, new event at t=12,
  both visible at t=15, window [10,20): reported two Gold events instead of one
  (`red-cohort.xml`/`.log`).
- Root cause: any physical offer during measurement assigned its logical event
  to that cohort, including an earlier warmup event.
- Fix: assign logical events by their first planned offer; continue counting
  every physical measurement offer/admission in load rates.
- Regression: `test_measurement_duplicate_of_warmup_event_does_not_become_measurement_goodput`
  checks offered=2, admitted=2, goodput=1/10 seconds and complete cohort=1.
  Existing quantile, lag, F1, percentage and drain-boundary tests pass.

### F04 — High, P4: cancellation loses future offer dispositions

- Requirement: evaluation §4/playbook P4 require every planned emission to be
  accountable and exceptions/cancellation to retain evidence.
- Location: `benchmarks/scheduler.py::run_schedule`.
- Reproduction: cancel immediately after the first send of a ten-offer
  schedule. Only one emission receipt survived and `generator.json` was absent
  (`red-cancellation-stale.xml`/`.log`).
- Root cause: cleanup covered active/queued work only; later planned records
  were never journalled, and generator persistence followed the exception path.
- Fix: retain the interrupted offer and stream the unoffered suffix into
  explicit missed dispositions; persist an INCOMPLETE generator snapshot from
  cleanup. Unsent work remains missed; an attempted operation remains unknown.
  The original cancellation still propagates. An early abort has no fabricated
  cutoff and no completed-window denominator.
- Regression: cancellation test reconciles all ten receipts, one unresolved
  attempted send and nine misses, zero accounting-invariant failures, no early
  `cutoff.json`, and null duration denominator. Existing count/byte limits,
  slow-publisher admission, finite/query timing and late-ack tests pass.
- Limit: unreadable/corrupt plans or unavailable evidence storage cannot yield
  complete journals; the enclosing experiment reports incomplete evidence.

### F05 — Medium, P5: stale explicit Prometheus timestamps accepted

- Requirement: common §14/evaluation §5 require visible missing/stale samples;
  they cannot become current measurements or fabricated zeroes.
- Location: `benchmarks/collectors.py::PrometheusReader`.
- Reproduction: an actual loopback HTTP metrics response with sample timestamp
  1000 ms after Unix epoch returned a current reading of 7
  (`red-cancellation-stale.xml`/`.log`).
- Root cause: the reader discarded the parsed sample timestamp.
- Fix: enforce a declared positive finite freshness bound (default one second)
  for explicit timestamps, reject stale/future samples as missing, and retain
  timestamp/age for accepted timestamped samples. Duplicate-series detection
  also includes rejected stale occurrences. Untimestamped live scrapes retain
  their existing scrape-time behavior.
- Regression: actual HTTP stale-sample test plus absent-metric, collector gap,
  stall, resource-clock and offline-summary tests pass.
- Limit: an exporter supplying no timestamp cannot expose the age of its
  internally cached value. Its own health/freshness metric remains necessary.

### F06 — Medium, P7 evidence: failed scenario could be labelled PASS

- Requirement: runbook §7 requires each `tests.jsonl` case to retain its actual
  verdict; evidence cannot claim a pass when an assertion or teardown failed.
- Location: `benchmarks/manual/verify_p7.py`.
- Reproduction by inspection: a JUnit testcase with an `assistant_turn`
  property followed by a failure/error/skipped element was always serialized
  with `status="PASS"`, `passed=true`, and no failure reason. The aggregate
  verifier could fail while its per-case artifact claimed success.
- Root cause: the exporter scanned all properties without their testcase verdict.
- Fix: derive each record from its testcase, preserve FAIL/NOT_RUN, and require
  60 distinct scenario IDs for the checkpoint.
- Regression: four synthetic JUnit cases cover pass, post-property failure,
  error and skip in `tests/benchmarks/test_verifier_evidence.py`.
  Final real-PostgreSQL verifier evidence is retained separately below.

### F07 — Medium, P1: blocked matrix scans repeatedly hash the raw source

- Requirement: P1 CLI/configuration must fail honestly for missing prerequisites;
  it must not perform useless history scans before that failure. Existing resume
  rules prohibit reuse when preflight fails.
- Location: `projectctl/benchmark_adapter.py::execute_benchmarks`.
- Reproduction: the existing P1 verifier's draft matrix command spent over six
  minutes scanning earlier result directories. Every `reusable_run` called
  preflight and hashed the same 38 MB CSV again for each directory/trial.
  A focused regression with an earlier result directory reproduced the forbidden
  scan (`red-matrix.xml`/`.log`).
- Root cause: the matrix adapter tested every candidate for reuse before checking
  whether the trial's configuration permitted any reuse.
- Fix: check preflight once before scanning candidate directories. A blocked
  trial still emits its normal dependency-failure artifacts. Ready trials retain
  all existing integrity/reuse checks.
- Regression: `test_draft_matrix_does_not_scan_prior_results_for_each_blocked_trial`
  forbids the scan for a draft config and verifies every result remains exit 4
  and NOT_RUN. CLI/metric targeted suite: 71 passed (`cli-metrics.xml`).
- The stuck audit-owned draft command was terminated, preserving earlier blocked
  artifacts and the interrupted verifier log. P1 is rerun after this correction;
  the interrupted result is not reported as a successful verifier run.

### F08 — Medium, P4/P5 tests: host timing changes the tested scenario

- Requirement: reproducible verification, explicit doubles, and no weakened
  assertions or fabricated measurements (AGENTS evidence rules).
- Locations: `tests/benchmarks/test_scheduler.py` and
  `tests/telemetry/test_observation.py`.
- Reproduction: the first final P7 run retained **730 passes and 7 failures**
  (`verifier-p7/checks.json`, `pytest.xml`). The same complete suite had just
  passed in the real P6 Docker run. These tests assumed that 20 ms collector
  ticks and a 150 ms publisher schedule would always run promptly on the host.
  Delays correctly produced missing ticks or additional attempted sends, which
  changed the unit-test scenario before its expected assertions could hold.
- Root cause: explicit publisher/collector doubles still used real idle timer
  waits. The new cancellation test also used the default 32 workers while
  expecting exactly one attempted operation.
- Fix: use an explicit virtual elapsed clock/selector-loop double in these two
  unit-test modules. Every task, scheduled tick and timeout still executes;
  only idle waits advance deterministically. The cancellation case explicitly
  limits concurrency to one. All original outcome/count/CPU assertions remain.
- Regression: **35 tests pass** in `clock-regression.xml`. Real PostgreSQL,
  actual HTTP/process/restart tests, real resource collection, and the manual
  publisher/observer demonstrations retain real clocks. No real-provider path
  was replaced by a double, and virtual timings are not performance evidence.
- The failed P7 artifacts remain intact. A complete new final P7 run writes
  `verifier-p7-final/`; the failed run is not overwritten or counted as passed.

## Baseline and targeted verification

- Clean `uv sync --locked` into a fresh ignored environment installed 37
  packages with CPython 3.11.15; the application lock was preserved.
- Baseline: **717 passed, 0 failed, 0 skipped** in 109.15 seconds, with real
  PostgreSQL 18.6 and explicit provider/event doubles (`baseline.xml`/`.log`).
- Initial targeted fixes: **165 passed** (`targeted.xml`); workflow/API/evidence
  coverage: **95 passed** (`workflow.xml`); metric/lifecycle/telemetry coverage:
  **98 passed** (`metrics-lifecycle.xml`). These overlap and are not added to
  the final unique regression count.
- Actual uploaded CSV checksum matched
  `56f8f699c9e847356666c2eab3c3ab1244340f6a98ad08e39ea2199ebe993ad1`.
  Independent checks found 20,000×15, 19,998 canonical identities,
  19,920 active +78 inactive +2 superseded +0 mandatory rejected; exact
  duplicate-PID winners and 323 unknown categories matched (`dataset_checks.json`).
  Provider normalization and full facet-coverage comparison remain NOT_RUN.
- The initial currency-corruption probe was already rejected by the existing
  oracle. Its added regression retains that behavior; no oracle fix is claimed.
  The initial red file includes an assertion expecting a different diagnostic
  name; it is not counted as an implementation defect.

## HTTP flows and dependency provenance

`tests/conversation/test_process_workflow.py` launches an actual loopback
uvicorn M1 subprocess and makes HTTP requests against real PostgreSQL with
explicit in-process catalogue/Orders/event doubles. Raw request bodies, safe
identity headers, returned IDs/versions and responses are saved in test evidence.
The flows exercise session creation, cart read, cross-user 403, cross-namespace
404, search, identical mutation replay, changed-input and stale-version 409,
quote, cart edit, old-confirmation rejection, unconfirmed checkout 422, accepted
order response loss, blocked edits while unresolved, and same/new-key checkout
recovery to the same pending order. Another loopback test confirms unavailable
catalogue results stay visibly `dependency_error` with empty products.

Existing suites additionally exercise real service-process restart, PostgreSQL
concurrent edits/key contention, atomic rollback of state/key/event capture,
malformed provider responses, bounded transport deadlines/retries, stopped real
HTTP dependencies, Orders failure/status/SSE, and quote binding corruption.
The event capture is explicitly a transactional double, not the shared outbox.
There is no real catalogue/Orders/saga/Kafka/Gold integration claim.

## Outstanding handoffs and contract decisions

| Owner | Available reproduction / missing gate | Required next handoff |
|---|---|---|
| Harsh | Catalogue service/contracts/DTO/dictionary directories contain scaffolding, so real search/quote bindings are unavailable | Canonical OpenAPI/DTOs, immutable SKU/facet manifests, real APIs and reviewed brand/path bindings; full D-01/D-02 normalized/facet reconciliation |
| Aditya | Orders/Inventory/Payments and shared outbox contain scaffolding; real cart event path fails closed with 503 | Orders acceptance/status/SSE, quote-consumption/stable-key guarantees, shared `append_outbox` and caller-local DDL; real stock/ledger recovery checks |
| Vichitr | Event builder/schema/transport, broker, active Gold/receipts and environment adapters unavailable | Shared builder/transport and diagnostics, caller-local schema binding, locked Compose/registry, analytics membership/receipt adapters and fault barriers |
| Jaineel + Harsh | Common §5 TurnRequest allows only request_id/text/mode while §6.2 requires structured controls | Existing local structured adapter bypasses extraction; HTTP controls use M2 `/v1/search`. Any new M1 field/endpoint requires their explicit contract review |
| Aditya + Jaineel | Consumed Orders relative `status_url` convention and provider isolation/version semantics await canonical contract | Review existing consumer examples before binding a real provider; no public contract changed here |

`contracts check --all` returning **4** represents these unavailable handoffs.
It is not a passing G0/G3 check and is not hidden by a substitute service.
No teammate-owned implementation defect can be reproduced against absent code.

Human scenario review remains **NOT_RUN**. Existing automated LLM-adjudication
history is preserved, and no model provider was called during this audit.
Hosted CI, real shared event delivery, real G1/G3, full performance/SLO matrix
and P8–P11 remain unverified/unimplemented by this audit.

## Final command/evidence index and readiness

The final complete suite contains **737 distinct testcase IDs**: conversation
216, projectctl 113, contracts 94, oracles 50, benchmarks 217, telemetry 47.
All passed; none failed, errored, or skipped. This count comes only from
`verifier-p7-final/pytest.xml`. Baseline, targeted and overlapping verifier suites
are not added to it. One deprecation warning comes from the locked FastAPI
TestClient/HTTPX combination; no dependency was changed to suppress it.

In the commands below, `python` is
`artifacts/p1-p7-audit/20261027-audit/venv/Scripts/python.exe` and `AUDIT` denotes
the audit evidence directory. Exact executable paths, argument arrays, stdout,
stderr, timestamps and actual exit codes are in `checks.json`,
`final-checks.json`, `final-verifier-command.json`, and the nested verifier
`checks.json` files. The initial P1 and P7 failures remain preserved separately.

| Command / check actually run | Actual outcome |
|---|---|
| `uv sync --locked` with `UV_PROJECT_ENVIRONMENT=artifacts/p1-p7-audit/20261027-audit/venv` | Fresh Python 3.11.15 install: 37 packages; final locked recheck exit 0, 37 audited |
| Runtime imports for all frozen dependency families, projectctl and conversation app | Exit 0, Python 3.11 asserted |
| `python benchmarks/manual/verify_p1.py` | Corrected rerun exit 0, **16/16** expected outcomes; initial interrupted matrix inspection preserved |
| `python benchmarks/manual/verify_p2.py` | Exit 0, **9/9** expected outcomes |
| `python benchmarks/manual/verify_p3.py` | Exit 0, **10/10** expected outcomes |
| `python benchmarks/manual/verify_p4.py` | Exit **1**, **10/11**: tests/schema/slow-publisher checks passed; only original single-P4 Git guard rejected authorized conversation edits |
| `python benchmarks/manual/verify_p5.py --review-p1-p5` | Exit 0, **11/11**, including stall/gap demonstration and offline reconstruction |
| `python benchmarks/manual/verify_p6.py --out AUDIT/verifier-p6` | Exit 0: fresh Docker PostgreSQL 18.6, full regression, API smoke and retained-volume database restart passed |
| `python benchmarks/manual/verify_p7.py --out AUDIT/verifier-p7-final --database-file AUDIT/verifier-p6/local-database.json` | Exit 0, **10/10** expected outcomes; **737/737** tests, **60** distinct fixed scenarios, **0** model attempts, **16/16** smoke assertions |
| `python -m pytest tests/conversation tests/projectctl tests/contracts tests/oracles tests/benchmarks tests/telemetry -q --tb=short -o junit_family=xunit1` plus explicit cache/basetemp/JUnit paths | Final P7 verifier's complete relevant suite: **737 passed**, no failures/errors/skips |
| `python -m ruff check projectctl benchmarks services/conversation shared/contracts shared/telemetry dashboards tests/projectctl tests/contracts tests/oracles tests/benchmarks tests/telemetry tests/conversation` | Exit 0 |
| Same paths with `python -m ruff format --check` | Exit 0, **112 files** formatted |
| `python -m projectctl.schemas --check`; `python -m projectctl.conversation_contract --check` | Both exit 0; generated schemas/OpenAPI current |
| `git diff --check` | Exit 0; no whitespace errors |
| Protected-path `git diff --exit-code` and independent `finish_evidence.py` ownership check | Exit 0 / PASS; **22 changed paths**, all Jaineel-owned; no staged paths; HEAD unchanged |
| `python -m projectctl contracts check --all` | Expected exit **4**, canonical provider handoffs absent; no real integration pass |

P1's existing verifier invokes the draft matrix command, which creates blocked
trial artifacts. No performance workload was executed: draft configuration and
missing adapters prevented every trial from starting. The initial command was
terminated only after identifying F07; its artifacts and interrupted log remain.
The corrected rerun completed with the documented exit 4 for those draft trials.

P4's final guard explicitly forbids all `services/` edits because it was written
for a P4-only checkpoint. This audit was explicitly authorized for P1–P7. Its
failure was preserved, and the independent audit ownership check verifies the
actual requested scope. No assertion or ownership rule was loosened to make that
verifier green.

The new PostgreSQL container retained its ID, image and named volume across a
restart. Its loopback port changed **32772 → 32773**; the existing harness
refreshed the connection file and the resumed smoke passed. `fsync`,
`full_page_writes` and `synchronous_commit` were all on. The original container
and volumes were preserved. The audit container/volume and its smoke schema
remain available for manual replay; test credentials stay only in ignored files.

Evidence entry points:

- `summary.json`, `ownership.json`, `evidence-index.json`: final count, scope,
  immutable evidence hashes and nested evidence locations.
- `source.diff`, `source-snapshot.json`, `source-snapshot/`: retained exact
  changed source/tests/documentation, including new untracked files.
- `verifier-p1-fixed.log`, `verifier-p1-evidence/` through
  `verifier-p5-evidence/`: copied raw verifier checks/JUnit and original paths.
- `verifier-p6/docker-summary.json`, `docker-checks.json`, and
  `checkpoint/smoke/database-restart.json`: fresh real database and restart proof.
- `verifier-p7-final/{checks.json,pytest.xml,summary.json,assistant_turns.jsonl,tests.jsonl}`:
  final suite and scenario evidence. `smoke/{smoke.json,http.json}` contains the
  16-assertion API smoke.
- `verifier-p7-final/test-temp/test_network_workflow_isolatio0/http.json` and
  `test_network_catalogue_failure0/failure.json`: actual network requests and
  safe identity headers, returned IDs/versions and dependency-failure response.
- `red-*.xml`, `red-*.log`, `verifier-p1-interrupted.log`, and `verifier-p7/`:
  preserved reproductions and unsuccessful attempts, including the seven timing
  failures. These are not represented as successful runs.

**Readiness:** Jaineel's independent P1–P7 implementation checkpoint is ready
for the next owner-reviewed integration stage. There are no remaining reproduced
owned-code failures. Real event delivery and real catalogue/Orders integration
remain **INCOMPLETE/NOT_RUN** until the handoffs above are supplied. This is not
a full real P1–P7/G3 certification, benchmark/SLO result, or advancement of P8–P11.

Changed source/test paths:

- `projectctl/benchmark_adapter.py` and `tests/projectctl/test_cli.py`: F07.
- `services/conversation/intent.py`, `tests/conversation/test_intent.py`: F01.
- `services/conversation/clients.py`, `tests/contracts/test_clients.py`: F02.
- `benchmarks/metrics.py`, `tests/benchmarks/test_metrics.py`: F03.
- `benchmarks/scheduler.py`, `tests/benchmarks/test_scheduler.py`: F04.
- `benchmarks/collectors.py`, `tests/telemetry/test_collectors.py`: F05.
- `tests/benchmarks/time_double.py`, `tests/telemetry/test_observation.py`,
  and the scheduler test clock/concurrency setup: F08.
- `benchmarks/manual/verify_p7.py`, `tests/benchmarks/test_verifier_evidence.py`: F06.
- `tests/conversation/{server,process,test_process_workflow}.py`: actual network
  workflow/fault verification with explicit provider flags.
- `tests/oracles/test_reconciliation.py`: preserves the existing currency
  corruption rejection with an additional regression.
- `docs/jaineel/{P1_P7_AUDIT,progress}.md`: this audit and accurate progress.

No application lock, dependencies, CI, shared specification, public DTO/schema,
fixture label/audit history, teammate implementation, or existing migration was
changed. Initial state was clean, and no staging/commit/push/merge was performed.

Manual recheck from the repository root:

1. Use the audit environment's `venv/Scripts/python.exe`. Set
   `P6_TEST_DATABASE_URL` by reading the ignored local database connection file
   emitted by the Docker harness; do not paste credentials into a report.
   Rerun `python -m pytest tests/conversation/test_process_workflow.py -q` with a
   fresh `--basetemp` directory. Inspect its `http.json`: actual returned cart
   versions/quote/order IDs, 403/404 isolation, 409 conflicts, 503 unknown checkout
   followed by 202 PENDING and the same order on replay.
2. Run `python -m benchmarks.manual.p7_smoke --test-double-providers
   --confirm-checkout --out artifacts/p1-p7-audit/manual-NEW-ID`. Confirm 16
   assertions and review the actual quoted total and response-loss transcript.
   The flags explicitly opt into synthetic providers and simulated checkout.
3. Run `python -m pytest tests/conversation/test_intent.py
   tests/benchmarks/test_scheduler.py tests/benchmarks/test_metrics.py -q`.
   The new foreign-currency/repeated-constraint cases clarify, cancellation
   accounts for all planned records, and warmup duplicates add no goodput.
4. Run `python -m projectctl contracts check --all`. Expected exit is 4 until
   the listed provider handoffs exist. Review the audit's provider inventory
   and independent `dataset_checks.json` before attempting real integration.
