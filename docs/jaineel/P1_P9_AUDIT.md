# P1–P9 audit and fixes — 28 October 2026

This audit covers Jaineel's available M1/M0 implementation through P9. It does
not certify the absent catalogue, transaction, event/outbox or analytical services.
Real G0/G1/G3/G4/G5 and performance results remain INCOMPLETE/NOT_RUN. P10/P11
were not implemented. No model provider, commit, push, merge, reset or unrelated
service/volume mutation was performed.

Branch: `jaineel/j03-telemetry`. The initial 22 dirty paths (including the
uncommitted [P1–P7 audit](P1_P7_AUDIT.md)) were captured and preserved. This audit
adds changes only in Jaineel-owned paths. The authority is
[ownership](../OWNERSHIP.md), [common interfaces](../specs/02_COMMON_SPEC.md),
[evaluation](../specs/03_EVALUATION_SPEC.md),
[dataset rules](../specs/08_DATASET_PROFILE_AND_RULES.md),
[runbook](../specs/09_EVALUATION_RUNBOOK.md), and the
[P1–P9 playbook](../specs/10_JAINEEL_CODEX_PLAYBOOK.md).

Evidence root: `artifacts/p1-p9-audit/20261028-audit/` (ignored, retained locally).
Every `*.command.json` records the exact argument array, UTC start/end, elapsed
time, exit code and raw stdout/stderr filenames. Initial reproductions and failed
audit development attempts remain alongside successful reruns.

## Requirements mapped to code and verification

| Milestone | Implementation inspected | Executable verification and limits |
|---|---|---|
| P1 | `pyproject.toml`, `uv.lock`, `projectctl/{cli,config,models,artifacts,providers,schemas}.py`, CI | Locked sync, help/invalid options, adapter/config/failure artifact tests in `tests/projectctl`; `verify_p1`. Missing-provider exit 4 remains visible. |
| P2 | M1 provider contracts, gateway and HTTP/SSE clients; canonical versus provisional contract inventory | `tests/contracts`, negative JSON/money/response validation, deadlines/retry identity, SSE version conflict/reconnect; `verify_p2`. Teammate canonical bindings remain absent. |
| P3 | Independent dataset checks, quality/assistant fixtures, reconciliation, metric math | `tests/oracles`, fixture/metric corruption tests, source checksum/accounting; `verify_p3`. Existing automated adjudication preserved; human review NOT_RUN. |
| P4 | Workloads, drivers, scheduler, experiment lifecycle, planning | Bounded slow-publisher, cancellation, duplicates, exact cutoff/late acknowledgement, finite/query timing and receipt conservation tests; `verify_p4`. Synthetic demos are smoke/test evidence. |
| P5 | Shared telemetry, collectors, observer, offline reconstruction and dashboard | `tests/telemetry`, stall/gap demonstration and independent rebuild; `verify_p5`. New cohort/identity/clock and cgroup checks below. Grafana deployment NOT_RUN. |
| P6 | `services/conversation/{state,database,events,app}.py`, both SQL migrations | Real PostgreSQL 18 state, concurrent edit/key contention, rollback, isolation, lost response and process restart tests; `verify_p6`. Shared outbox/event capture is an explicit transactional double. |
| P7 | Intent extraction, templates, quote/checkout command journal, gateway | `tests/conversation`, 60 fixed scenarios, explicit confirmation/stale versions/quote binding, actual loopback API flow; `verify_p7`. Actual provider services and live assist NOT_RUN. |
| P8 | Case register, scoped preparation, frozen inputs, independent audits, fault gates and rechecks | `tests/integration`, T/D alias deduplication, acknowledged barriers/retained-state/outage doubles, namespace/read-only checks; `verify_p8`. Required real cases remain blocked. |
| P9 | Performance eligibility, metrics, comparisons, selection, capacity, matrix/config and resume | All existing P9 tests plus the regressions below; `verify_p9`; read-only validation of documented previous evidence. No short/stub trial is a performance measurement. |

## Findings

### A01 — High, P5/P9: a received-timer count was treated as the whole cohort

- Requirement: evaluation §5.1 and runbook §7 require unfinished work and missing
  timings beside completed-only quantiles. Location:
  `benchmarks/observation_summary.py::rebuild`.
- Reproduction: three acknowledged planned requests with one retained 10-ms timer
  produced `cohort_count=1`, no missing timing, and a complete-cohort p99. See
  `red-evidence.xml` and `red-evidence.stdout.txt`.
- Root cause: `expected_count=len(received_timings)` learned the denominator from
  the observations. Duplicate IDs, cross-namespace timers and mixed clocks were
  also not checked by this aggregation path.
- Fix: hash and join the independent plan, emissions and stage IDs. Count known
  acknowledgements without timers as missing timings, and uncompleted stage
  operations as unresolved. Keep unknown stage mappings INCOMPLETE. Reject
  duplicate/context/clock conflicts; bind duplicate event deliveries to their
  original logical offer. Mandatory primary stage cohorts must be complete before
  P9 promotion.
- Regression: `tests/benchmarks/test_audit_evidence.py` covers omitted/null timers,
  late physical duplicates, duplicate timer identity, namespace and clock mismatch.
  Limit: integrated domain-event stages need a reviewed cohort mapping; request
  workflow/finality timers must carry their planned `record_id`.
- Previous results: no measured P9 run affected; historical smoke/stub summaries
  remain historical and should be rebuilt under these rules before further use.

### A02 — High, P9: stage latency rows reported admission-level unresolved counts

- Requirement: Gold/finality completion is separate from admission (evaluation
  §§5.1/5.3). Location: `benchmarks/performance_metrics.py::derive_metrics`.
- Reproduction: an entirely admitted cohort with 99 unfinished Gold operations
  exported `unresolved_count=0` beside a 10-ms Gold p95. `red-evidence.xml` retains
  the failing assertion (actual 0, expected 99).
- Root cause: every metric inherited `admission.unresolved`, ignoring the stage's
  independent unresolved count.
- Fix: use stage-specific counts for both namespaced quantiles and primary p95
  aliases. Unknown counts stay null. Preserve collector/CPU incompleteness when
  exporting their derived metrics.
- Regression: the explicit stage projection double with 99 unresolved operations
  now retains 99. No real performance claim is made by this fixture.
- Previous results: none of the documented previous P9 runs contain measured
  metrics. Future full trials must retain and validate these boundaries.

### A03 — High, P9: hash-valid summaries could disagree with their raw evidence

- Requirement: evaluation §§9/10 and runbook §§5/7 require reproducible raw-backed
  metrics and integrity checks before reuse/comparison/selection. Location:
  `benchmarks/performance.py::load_performance_run`.
- Reproduction: with explicit bundle/audit boundary doubles, the loader accepted
  a 999-ms query p95 over 10-ms raw timers. `red-metric-loader-repro.xml` retains
  the missing expected rejection. This is a loader test, not a real SUT run.
- Root cause: bundle hashes and a pass flag were checked, but saved metric values
  were never independently recomputed.
- Fix: share admission-rate arithmetic with execution, independently rebuild all
  saved metric rows, and require exact agreement at load. P9 output validation
  also recomputes admission from the frozen plan/emission journals and checks
  their saved result/hash. Raw JSONL timings are mandatory indexed evidence.
- Regression: both a consistent summary and the same summary with only its p95
  changed are tested; the former loads, the latter is rejected. Existing artifact,
  comparison, selection and resume tests remain required.
- Previous results: no measured P9 results to invalidate. Resume will reject any
  future incompatible metric derivation and retain the original run.

### A04 — Medium, P8: cancellation left selected cases without finalized evidence

- Requirement: failure evidence survives cancellation; every selected case has a
  disposition (AGENTS evidence rules and runbook §4). Location:
  `benchmarks/integration.py::run_cases`.
- Reproduction: an exercise callback raising `asyncio.CancelledError` escaped
  before its case record and final manifest were written. See
  `red-cancellation.xml` (uncaught cancellation).
- Root cause: cancellation inherits from `BaseException`; `except Exception`
  did not cover it and there was no cancellation finalization path.
- Fix: retain the interrupted case as INCOMPLETE, mark remaining cases NOT_RUN,
  stop executing their callbacks, and finalize journals/manifest with exit 4.
  Existing fault-gate restart cleanup remains in force.
- Regression: explicit callback cancellations during prepare, exercise and audit
  in `tests/integration/test_audit_cancellation.py`. All selected cases remain
  accountable; cancellation text contains no provider exception/secret content.
- Previous results: no historical incomplete trial was promoted. Already lost
  journals cannot be reconstructed; rerun a cancelled real case when available.

### A05 — Medium, P5/P9: cgroup samples omitted the OOM evidence their consumer required

- Requirement: evaluation §8 requires actual OOM/resource evidence, with missing
  readings visible. Locations: `benchmarks/collectors.py::CgroupV2Reader` and
  `benchmarks/capacity.py::assess_run`.
- Reproduction: a cgroup fixture with `memory.events: oom_kill 0` produced memory
  readings without `details.oom_kill_count`, so the capacity consumer could never
  accept this built-in reader's samples. `red-evidence.xml` retains the KeyError.
- Root cause: producer/consumer metadata mismatch.
- Fix: read the actual cgroup counter from `memory.events`. Missing/invalid
  readings remain null, so they cannot become a zero-OOM claim.
- Regression: a real file-reader test over explicitly synthetic cgroup files;
  capacity tests cover full samples, sparse samples and a nonzero OOM counter.
- Previous results: no measured stress run exists; no sustainable rate is claimed.

### A06 — High, P9: a single resource sample could qualify a 600-second tier

- Requirement: evaluation §§4/8 and runbook §7 require complete per-second
  resources within the fixed budget. Location: `benchmarks/capacity.py::assess_run`.
- Reproduction: complete 600-second backlog samples plus only one memory reading
  per service returned `capacity_valid=true`. See `red-capacity.xml`.
- Root cause: resource validation checked only whether each component appeared
  somewhere, without checking temporal coverage.
- Fix: require a valid memory/OOM reading for every declared SUT service at every
  measurement second. Every observed resource reading must satisfy its bound.
- Regression: explicit validated-run boundary double; sparse sampling and OOM
  fail, complete in-budget samples pass. This is capacity-logic verification;
  actual container stress remains NOT_RUN.
- Previous results: no measured stress result to mark stale; affected future tiers
  must be rerun if their raw resource coverage is incomplete.

### A07 — Medium, P8/P9 CI: the integration harness tests were never scheduled

- Requirement: P8's implemented test register and the P1–P9 regression checkpoint
  must stay executable in CI. Location: `.github/workflows/offline.yml`.
- Reproduction by inspection: both existing jobs invoke older verifiers whose
  pytest argument lists omit `tests/integration`; neither job schedules it.
- Fix: add integration lint, formatting and pytest steps to both OS legs of the
  offline job; name the workflow for P1–P9. PostgreSQL remains a separate job.
- Validation: the exact local integration lint/format/test surface is included
  in this audit's checks. Hosted GitHub execution remains NOT_RUN; no commit/push
  was authorized.
- Previous results: historical CI passes prove only their former scope. They do
  not establish P8 correctness or real provider integration.

### A08 — Medium, P6 verification: isolated schemas shared test advisory-lock scopes

- Requirement: reproducible independent checks without relaxed production bounds.
  Location: `tests/conversation/conftest.py::context`.
- Reproduction: the first P6 verifier retained 797 passes and one A-025 failure
  while a second verifier ran against the same PostgreSQL database. Both suites
  used fixed namespace/user/key values. A focused two-connection PostgreSQL probe
  then reproduced the advisory-lock timeout deterministically
  (`red-test-isolation.xml`), without relying on concurrent suite timing.
- Root cause: PostgreSQL advisory locks are scoped to a database, so separate
  test schemas did not isolate identical advisory-lock keys.
- Fix: give each test context a fresh benchmark namespace. The lock operation,
  API timeouts, production implementation and frozen scenario labels are unchanged.
- Regression: hold one test context's operation lock and acquire the same key
  for an independently created context using another real connection. The new
  test in `tests/conversation/test_state.py` passes after namespace isolation.
- Previous results: the first failed P6 verifier remains retained; successful
  baseline/P7 records are not relabelled. Repeat the affected verifier and final
  complete suite after this test-infrastructure correction.

## Verification and observed execution

Baseline: **823 passed, 0 failed/errors/skipped**, 152.59 s, real M1 PostgreSQL and
explicit provider/event/audit doubles (`baseline.xml`). The dedicated new audit
regressions pass; their counts overlap the final full suite and are not added to it.

Final full regression: **840 distinct tests passed; 0 failed, 0 errors, 0 skipped**,
164.39 s (`final.xml`). By directory: conversation 217, projectctl 117, contracts
94, oracles 50, benchmarks 275, telemetry 47, integration 40. This is the unique
final count; baseline, targeted, manual-verifier and CI-subset counts overlap it
and are never summed. Seventeen tests were added. Eight findings were fixed:
0 critical, 4 high, 4 medium. One upstream Starlette deprecation warning remains;
no dependency was changed to suppress it.

In this table, `python` is `.venv/Scripts/python.exe`, `AUDIT` is the evidence root,
and `DBFILE` is the existing ignored
`artifacts/p1-p7-audit/20261027-audit/verifier-p6/local-database.json` connection
file. No credentials are printed in the command ledger.

| Exact command/check (paths expanded in `*.command.json`) | Actual outcome |
|---|---|
| `uv sync --locked --cache-dir AUDIT/uv-cache` | Exit 0, 38 packages resolved and 37 installed packages audited; existing Python 3.11.15 environment; lock unchanged. |
| `python -m benchmarks.manual.verify_p1` | Exit 0, all 16 expected outcomes. |
| `python -m benchmarks.manual.verify_p2` | Exit 0, 9/9 expected outcomes; explicit HTTP/SSE doubles. |
| `python -m benchmarks.manual.verify_p3` | Exit 0, 10/10 expected outcomes; independent fixture corruption probes/source checks. |
| `python -m benchmarks.manual.verify_p4` | Exit 1, 10/11 checks. Its final P4-only guard rejects the preserved, authorized conversation edits. Workload/tests/demo/schema checks passed. The guard was not weakened; the audit ownership check applies the requested P1–P9 scope. |
| `python -m benchmarks.manual.verify_p5 --review-p1-p5` | Exit 0, 11/11; stall/gap demo and offline reconstruction passed. |
| `python -m benchmarks.manual.verify_p6 --external-database --out AUDIT/verifier-p6-final` | Exit 0, all 10 expected outcomes; **800 passed**, actual loopback API/service restart smoke passed. First run's 797-pass/1-failure result remains in `verifier-p6/`. |
| `python -m benchmarks.manual.verify_p7 --out AUDIT/verifier-p7 --database-file DBFILE` | Exit 0, 10/10; **798 passed** at that source checkpoint, 60 distinct fixed scenarios, 0 model attempts, 16/16 smoke assertions. |
| `python -m benchmarks.manual.verify_p8 --out AUDIT/verifier-p8 --database-file DBFILE` | Exit **4**, harness checks passed; **839 passed** before the last isolation test was added. Setup `env up` returned 4; ten dependent setup commands stayed NOT_RUN. Contract/smoke/correctness/assistant/outage/recheck commands returned 4. |
| `python -m benchmarks.manual.verify_p9` | Exit 0 for its missing-dependency checkpoint; all five child command exits **4**, with 37 NOT_RUN evaluation cases, one refused short smoke, one refused B0 and 73 refused matrix records. No workload started. |
| `python -m pytest tests/conversation tests/projectctl tests/contracts tests/oracles tests/benchmarks tests/telemetry tests/integration -q --tb=short -o junit_family=xunit1 -o cache_dir=AUDIT/final-cache --basetemp=AUDIT/final-tmp --junitxml=AUDIT/final.xml` | Exit 0; **840 passed**, no failures/errors/skips. This is the final source checkpoint after all fixes. |
| `python -m pytest tests/integration -q --tb=short --junitxml=AUDIT/ci-integration.xml` | Exit 0, **40 passed**; standalone execution of the added CI test surface. Hosted CI NOT_RUN. |
| `python -m ruff check projectctl benchmarks services/conversation shared/contracts shared/telemetry dashboards tests/projectctl tests/contracts tests/oracles tests/benchmarks tests/telemetry tests/conversation tests/integration` | Exit 0. |
| Same paths with `python -m ruff format --check` | Exit 0, 136 files formatted. |
| `python -m projectctl.schemas --check`; `python -m projectctl.conversation_contract --check` | Both exit 0, all generated schemas/OpenAPI current. |
| `git diff --check`; protected-path `git diff --exit-code -- ...` | Both exit 0. Exact protected paths are in `protected-paths.command.json`; no shared spec/DTO/fixture/lock/provider implementation changed. |

All nine manual verifiers exist and were executed. Their raw ledgers remain at
the emitted evidence directories, linked by the command outputs. P1 and P9
verifiers each invoke a blocked matrix preflight; neither runs a long matrix or
records performance. The final ownership/evidence scripts record the exact
changed paths, preserved initial paths, unchanged HEAD/branch/index and hashes.

Actual requests exercised include M1 session creation, cart read/update,
identical-key replay, changed-input/stale-version 409, cross-user 403 and
cross-namespace 404, fixed search, quote, cart edit invalidating confirmation,
unconfirmed checkout 422, lost checkout response 503/unknown, blocked pending
cart edit, and same/new-key recovery to one 202/PENDING order. The final actual
network transcript has 19 requests and returned session
`f5f8c898-aaab-4155-acb8-5ddb041f34c2`, cart
`2c53474a-7809-4814-a7dc-c395c1635f8b`, initial quote
`2c753b24-d096-449e-b029-945d09d773e8`, and accepted order
`ca047702-dfa7-450a-bd3c-15c28e0b55d1`. See
`final-tmp/test_network_workflow_isolatio0/http.json` for returned versions and the
replacement quote. The unavailable-catalogue network case retains
`dependency_error` with empty products. P6 additionally exercises service process
restart and durable key/cart recovery.

PostgreSQL is the existing loopback Docker **18.6**, port **32773**, with `fsync`,
`full_page_writes` and `synchronous_commit` on. Container identity/durability
facts are retained in `verifier-p8/database.json`. Tests use new schemas and
remove only their own schemas; the original two containers and volumes remain.
No database-container restart was performed in this audit; the application
service-process restart was real. Catalogue/quote/Orders, shared event/outbox,
audit/fault and cgroup-capacity providers are explicitly labelled doubles in
their respective tests. No real Kafka offset/crash/recovery, inventory/payment
saga, stock projection, active-Gold publication or simulated success/decline
end-to-end integration result is claimed.

The required real evaluation cases are **37 distinct NOT_RUN cases**, deduplicated
across overlapping suites. Contract inventory is 3 local passes and 51 missing
provider handoffs. These dependency outcomes are separate from the 840 local
test passes. Initial red probes, a fixture-setup error, the intermediate refactor
failure, and the failed P6 run are retained; they are not passing evidence.

Changed source/config/test paths for this audit (earlier dirty work is preserved):

- `.github/workflows/offline.yml`.
- `benchmarks/{capacity,collectors,experiment,integration,observation_summary,performance,performance_metrics}.py`.
- `tests/benchmarks/test_audit_evidence.py`.
- `tests/conversation/{conftest,test_state}.py`.
- `tests/integration/test_audit_cancellation.py`.
- `docs/jaineel/{P1_P9_AUDIT,p9_performance,progress}.md`.

Manual continuation: use the same locked environment and a new evidence
directory; set `P6_TEST_DATABASE_URL` from the ignored connection file without
printing it. Repeat the full pytest command above and inspect its real network
transcript. After each provider handoff, run `contracts check --all`, follow the
canonical setup order and rerun P8; inspect every case/barrier/audit rather than
only its exit. Follow [the P9 handoff](p9_performance.md) for reviewed real
collectors, short smoke, B0, paired comparisons, C-BEST and stress/recovery.

## Existing P9 evidence and measurement validity

`previous-p9-validation.json` checks the documented P9 checkpoint
`artifacts/p9/5f5d40f9-dd4a-40cb-a8ef-7bd63d76cc32/checks.json`: **77 distinct run
bundles, 230 indexed artifacts**, all hashes and schemas valid. All summary exits
are 4; all performance values are null/NOT_RUN. Its evaluation journal has 37
NOT_RUN cases and its matrix has 73 retained dependency records. There was no
qualified B0, candidate comparison, C-BEST selection, stress or recovery result.

The original artifacts were preserved. No measured run/metric from that checkpoint
needs a stale flag; `stale_measurements=[]` is explicit in the audit record. A full
controlled rerun is still required after providers, reviewed bindings, locks,
resources, fixtures and a clean reviewed code revision exist. Audit smoke commands
exercise refusal/preflight; they do not execute the long performance matrix.

The independent source check again passed the exact checksum and
20,000 = 19,920 active + 78 inactive + 2 superseded + 0 mandatory rejects, with
19,998 canonical identities. This is source accounting, not Harsh's production
normalization/import pass. Twelve tracked fixture/review-history files are hashed
in `fixture-history-hashes.json`; labels/adjudication were not regenerated and no
human-review claim is made.

## Remaining handoffs and contract conflicts

| Owner | Required handoff / affected gate |
|---|---|
| Harsh | Canonical catalogue/search/facet/quote contracts and implementations, immutable source/normalized/SKU/query manifests, full D-01/02/03 results, import/search/compaction bindings and projection readiness. G0/G2/G3/G4 and I0/I1/O2/layout rows remain incomplete. |
| Aditya | Orders/Inventory/Payments APIs, caller-local shared outbox and DDL, deterministic seed/payment controls, scoped stock/reservation/ledger audits and acknowledged transaction faults. Real M1 events, G3, T-07/08/11 remain incomplete. |
| Vichitr | Locked environment/registry/Kafka/event transport, scoped analytics receipts and active membership, replay/storage/fault/observer/deployment controls. G1, publication/replay/T-11, O1/P10/P30/P33 and resources remain incomplete. |
| Jaineel + consumers | Compose real adapters from those reviewed handoffs; attach actual resources/correctness receipts and freeze all input hashes; run the canonical setup and suites, then short smoke, full B0 diagnosis, paired trials and evidence-selected stress/recovery. |

No teammate defect is asserted against absent implementation. Exact unavailable
handoffs and attempted command failures remain in the contract inventory and
checkpoint logs. The earlier common §5 TurnRequest versus §6.2 structured-control
conflict remains for Jaineel/Harsh review; no public M1 field/endpoint was added.
Consumed Orders status URL/isolation/version conventions also await Aditya's
canonical review. Neither conflict was silently resolved in shared behavior.

Readiness: the owner-code audit checkpoint can be reviewed with its evidence.
Real integrated/performance gates must pass before P10. P10 and P11 remain stopped.
