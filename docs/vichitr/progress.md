# Vichitr progress

Git delivery policy (31 October 2026): the user authorizes committing and pushing
each completed module to `vichitr` after its checks pass. The first delivery covers
the completed M01a/M01b infrastructure and planning notes. Credentials, the raw CSV,
generated data and local evidence stay outside Git. Earlier "not requested/pushed"
notes below describe those checkpoints before this standing authorization.

## Independent readiness closure — 2 November 2026

User requested completing remaining work that needs no teammate input. This
checkpoint adds owner-thread consumer-buffer observations and bounded worker JSON
logs, refreshes standalone infrastructure/registry/transport/recovery evidence,
and consolidates the remaining provider handoff. B0/O1 tuning and full independent
quality/integrated gates still require their actual owners' inputs.

Initial focused checks: **37 passed**, `artifacts/independent/offline-focused.xml`.
Owned paths: transport consumer/README; ingestion worker; buffer tests and worker
log check; low-memory PostgreSQL recreation test; test-only evidence redirection
for old registry/transport checks; checker mount and owner documentation. No new
dependency, shared metric name, public DTO/schema, CLI command or resource limit.
Live checks, final source pins and remaining-provider audit are recorded below
after execution; no unexecuted result is claimed in this implementation commit.

## M11 worker metrics exposure preparation — 2 November 2026

The next preparation checkpoint exposes the real worker's existing telemetry
registry at internal `http://analytics-worker:8006/metrics`. The API remains a
separate process/registry. See the [M11 handoff](m11_baseline_handoff.md#worker-metrics-preparation-checkpoint).
No dependency, migration, public schema, canonical specification, harness,
evaluation configuration, resource limit or batching behavior changes.

Changed owned paths: ingestion worker entrypoint/export lifecycle, Compose
worker port metadata/checker evidence mount, explicit lifecycle/bind-error tests,
real-process HTTP/Kafka/SQL/file check and owner documentation/skip notes.
Initial implementation: **ea1247b3d53c5ea3c54480a28a3116e72a5fc978**. Final
tested source: **d1a64ac6e9e507699e1843477d43a81b7f4967fe**. The only change
between them is a publication crash-test cleanup fence; production code is identical.

| Check | Actual outcome | Raw evidence |
|---|---|---|
| Focused entrypoint/B0/cadence unit checks | 13 passed, 12.26 s | `artifacts/m11-worker/offline-focused.xml` |
| First real worker/main/HTTP/Kafka/SQL/files check, ea1247b | 1 passed, 9.50 s | `artifacts/m11-worker/live-focused.xml`, `focused-facts/` |
| Host pipeline/contracts/integration, ea1247b | **347 passed, 133 skipped, 48.30 s** | `artifacts/m11-worker/host-final.xml` |
| First Linux run, ea1247b | 321 passed, 1 failed, 8 skipped, 2 deselected, 180.30 s | `artifacts/m11-worker/linux-first.xml`, `first-regression-facts/` |
| Final Linux run, d1a64ac | **322 passed, 8 skipped, 2 deselected, 248.27 s** | `artifacts/m11-worker/linux-final.xml`, `regression-facts/`, `worker-proof.json`, `worker-metrics.txt` |
| Ruff lint/format; generated CLI/conversation contract checks; diff whitespace | Passed | Exact commands below |
| Analytics Compose config with explicit nonsecret check-only token/identity | Passed, worker exposes 8006 internally | `docker compose ... --profile analytics-worker config --quiet` |
| Startup then read-only verification | First startup verification returned `ConnectionTimeout`; later verification passed after all containers reported healthy, with no resource/timeout changes | `artifacts/projectctl/c0e3b088-e955-47db-8870-32366d05fd2d/`, `artifacts/infra/streaming-local/checks/3a9a536f-3abf-4db9-bee1-b7b4bcd71d2e/streaming.json` |

The first Linux failure was `snapshot-before_rename`: the process had exited 73
with its named fault ACK, but PostgreSQL still held its publication session lock
when the parent immediately attempted recovery. The publisher correctly rejected
a competing owner. The test now waits for that exact namespace lock using a
transaction-scoped advisory lock and a five-second local SQL lock timeout. COMMIT
acknowledges fence release before recovery. No crash, generation, membership,
pending-event or visibility assertion was removed/relaxed; no sleep/retry loop or
production publisher change was added. All seven crash cases pass in final Linux.
The original failure and initial worker facts remain retained.

The actual worker exports one `new_valid` and one `duplicate_delivery`, two sink
transactions, one unique Silver/Gold effect, active generation 1 and committed
next offset 2. HTTP scrape evidence comes from its separate process, while the
parent registry has no worker histogram. Only the test schema/root connection
binding differs from normal runtime. No real-outbox pass or timing SLO is claimed.

Exact verification from repository root (use fresh result names on reproduction):

```powershell
$env:PROJECTCTL_ADAPTER_MODULE='infra.analytics'
.venv/Scripts/python.exe -m projectctl env up --profile streaming-local
.venv/Scripts/python.exe -m projectctl env verify --profile streaming-local
$env:POSTGRES_SECRETS_DIR=(Resolve-Path artifacts/infra/postgres-local/secrets).Path
$taskCommit=git rev-parse HEAD
docker compose -p group3-postgres-local -f infra/compose.yaml -f infra/compose.streaming.yaml -f infra/compose.storage.yaml -f artifacts/m11-worker/evidence.compose.yaml --profile storage-check run --rm --no-deps -e RUN_VERTICAL_LIVE_TESTS=1 -e RUN_STORAGE_LIVE_TESTS=1 -e M05_CODE_COMMIT=$taskCommit storage-check python -m pytest tests/pipelines -q --tb=short -k 'not quality_ratio_smoke and not more_than_ten_thousand' --junitxml=artifacts/m11-worker/linux-final.xml
.venv/Scripts/python.exe -m pytest tests/pipelines tests/contracts tests/integration -q --tb=short --junitxml=artifacts/m11-worker/host-final.xml
.venv/Scripts/python.exe -m ruff check pipelines/ingestion/worker.py tests/pipelines/test_worker_metrics.py tests/pipelines/test_worker_metrics_live.py tests/pipelines/worker_metrics_process.py tests/pipelines/test_publication_crash_live.py
.venv/Scripts/python.exe -m ruff format --check pipelines/ingestion/worker.py tests/pipelines/test_worker_metrics.py tests/pipelines/test_worker_metrics_live.py tests/pipelines/worker_metrics_process.py tests/pipelines/test_publication_crash_live.py
.venv/Scripts/python.exe -m projectctl.schemas --check
.venv/Scripts/python.exe -m projectctl.conversation_contract --check
git diff --check
.venv/Scripts/python.exe -m projectctl env down
docker desktop stop
```

The same ignored 2-CPU/512-MiB QA overlay redirects all M04–M11 sidecars into this
checkpoint; old module evidence survives. SUT allocations remain 2,176 MiB total,
and the VM reports about 3.76 GiB/8 CPUs. Actual limits/source pins are retained in
`runtime-context.json` and `runtime-final-context.json`. No CPU/RAM allocation or
schema migration changed. Shutdown and retained-volume evidence is `shutdown.json`.
Final delivery/three CI jobs are checked after push in `github-actions.json` and
`source-snapshot.json`. Shared CI does not replace the local live evidence.

**Skips:** 124 of 133 host-skipped cases pass in final Linux, including the new
worker process check. The same nine older/unaffected checks are not rerun: six
opt-in infrastructure/transport cases, controlled broker-pause DLQ and the two
large fixtures (all detailed in [test skips](test_skips.md)). Linux's eight skips
include the Windows-only guard, which passes on the host; two large fixtures are
explicitly deselected. No new worker check is skipped in Linux. Exact lists/counts
and NOT_RUN performance are in `artifacts/m11-worker/verification.json`.

Full independent correctness gates, observer composition and B0/O1/scaling
performance remain NOT_RUN.

## M11 baseline instrumentation preparation — 2 November 2026

This checkpoint adds durable B0 sink transaction audits and corrects the flush
timer boundary. It does not enable O1 or establish a measured/correctness-gated
B0 baseline. See the [M11 handoff](m11_baseline_handoff.md) for provider usage,
nullable timing semantics, overhead and the remaining owner/collector gates.

Changed owned paths: migration 009, analytics migration loader/readiness/version
evidence, curation audit insertion/post-COMMIT timer/read provider, checker evidence
mount, owned bounds/SQL/native-process-crash tests and migration regressions.
No shared DTO, canonical endpoint/schema, dependency, evaluation config, harness,
workflow or another owner's implementation changes.

Initial source: **718dc8e7b741369439a772891cf32f2f783697ac**. Final runtime:
**12c51eb37c27a708dd1f5511a7c2b0c2d706dbcd**. All local checks below completed.
The source-pinned actual consumer process exits 73 after sink COMMIT but before
timer/offset writes. The broker has no committed offset, restart redelivers with
one logical Gold effect and the old batch timer remains NULL. Explicit clock
doubles separately prove that connection teardown and later observation work are
excluded from the flush timer. Invalid-source cases use the named outbox double.

| Check | Actual outcome | Raw evidence |
|---|---|---|
| Initial reader/B0/worker checks | 20 passed | `artifacts/m11/offline-focused.xml` |
| First real sink audit checks at 718dc8e | 6 passed, 15.60 s | `artifacts/m11/live-focused.xml`, `focused-facts/sink-crash.json` |
| First Linux regressions at 718dc8e | 318 passed, 8 skipped, 2 deselected, 171.14 s | `artifacts/m11/linux-regressions.xml`, `baseline-facts/` |
| Stronger teardown clock probe against 718dc8e runtime | Expected failure: 7.125 s versus 0.125 s; preserved before correction | `artifacts/m11/close-boundary-before.xml` |
| Final Linux regressions at 12c51eb | **318 passed, 8 skipped, 2 deselected, 199.68 s** | `artifacts/m11/linux-final.xml`, `sink-crash.json`, `regression-facts/` |
| Final host pipeline/contracts/integration at 12c51eb | **344 passed, 132 skipped, 52.24 s** | `artifacts/m11/host-final.xml`; earlier clean run in `host-first.xml` |
| Ruff lint/format; generated CLI and conversation schema checks; diff whitespace | Passed; 21 Python files formatted/current | Session commands below |
| Actual infrastructure startup | Passed; fixed 2,176-MiB SUT profile | `artifacts/infra/streaming-local/checks/3ab20afd-7800-4ada-ac76-77f7cf084ab7/streaming.json` |
| Analytics migration 009 | Applied; versions 1–9 | `artifacts/infra/analytics/checks/ec2efb4c-6284-45d9-bea6-aad3cdd54923/analytics-migration.json` |

The strengthened clock probe caught teardown included after COMMIT; 12c51eb moves
the observation inside the connection context after the transaction context exits.
No assertion was weakened. The final full selected Linux suite includes that
regression and all six new live cases. Initial and failed evidence is retained.

Exact reproduction from repository root (Python is `.venv/Scripts/python.exe`):

```powershell
$env:PROJECTCTL_ADAPTER_MODULE='infra.analytics'
.venv/Scripts/python.exe -m projectctl env up --profile streaming-local
.venv/Scripts/python.exe -m projectctl db migrate --namespace bench-m11
# Global migrate intentionally returns exit_code=4: other owner migrations/outbox are absent.
$env:POSTGRES_SECRETS_DIR=(Resolve-Path artifacts/infra/postgres-local/secrets).Path
$taskCommit=git rev-parse HEAD
docker compose -p group3-postgres-local -f infra/compose.yaml -f infra/compose.streaming.yaml -f infra/compose.storage.yaml -f artifacts/m11/evidence.compose.yaml --profile storage-check run --rm --no-deps -e RUN_VERTICAL_LIVE_TESTS=1 -e RUN_STORAGE_LIVE_TESTS=1 -e M05_CODE_COMMIT=$taskCommit storage-check python -m pytest tests/pipelines -q --tb=short -k 'not quality_ratio_smoke and not more_than_ten_thousand' --junitxml=artifacts/m11/linux-final.xml
.venv/Scripts/python.exe -m pytest tests/pipelines tests/contracts tests/integration -q --tb=short --junitxml=artifacts/m11/host-final.xml
.venv/Scripts/python.exe -m ruff check pipelines/curation pipelines/ingestion infra/analytics.py tests/pipelines/test_sink_observations.py tests/pipelines/test_sink_observations_live.py tests/pipelines/sink_crash.py tests/pipelines/test_business_gold_live.py tests/pipelines/test_silver_live.py
.venv/Scripts/python.exe -m ruff format --check pipelines/curation pipelines/ingestion infra/analytics.py tests/pipelines/test_sink_observations.py tests/pipelines/test_sink_observations_live.py tests/pipelines/sink_crash.py tests/pipelines/test_business_gold_live.py tests/pipelines/test_silver_live.py
.venv/Scripts/python.exe -m projectctl.schemas --check
.venv/Scripts/python.exe -m projectctl.conversation_contract --check
git diff --check
.venv/Scripts/python.exe -m projectctl env down
docker desktop stop
```

Use fresh output filenames when reproducing; never overwrite retained evidence.
The ignored QA overlay sets only the checker to 2 CPUs/512 MiB and redirects
M04–M10 sidecars under M11 so old evidence survives. Actual Docker inspection
is in `runtime-context.json` and `runtime-final-context.json`: VM memory remains
4,040,888,320 bytes with 8 CPUs; SUT allocations are unchanged. This is correctness
QA, not a benchmark profile or measured capacity result. Shutdown evidence is
`artifacts/m11/shutdown.json`; volumes are retained.

**Skipped coverage:** 123 of the host's 132 skipped cases pass in final Linux.
The other nine are the unchanged 2,000-record quality smoke and 10,001-record
publication fixture (verified in M10), the controlled broker-pause DLQ scenario
(verified separately in M10), and six older opt-ins: registry/all-wire compatibility,
PostgreSQL isolation/recreation, streaming retained-volume recreation, transport
ack/manual-offset uncertainty, caller-outbox savepoint and real rebalance fencing.
Those infrastructure/provider paths did not change here. Linux's eight skips are
the six older opt-ins, externally controlled DLQ outage and Windows-only guard
(the guard passes on the host). No new audit case is skipped in Linux.

`artifacts/m11/verification.json` maps counts/skips to source pins and preserves
NOT_RUN performance. `source-snapshot.json` checks delivered runtime against
12c51eb. GitHub's three shared CI jobs are read after push and recorded in
`github-actions.json`; those jobs do not replace the local M4 live checks.

Full independent 100,000-record T-03, actual outbox/catalogue/compactor integration,
real observer-factory adoption, complete B0 bottleneck trace and all paired
performance/scaling trials remain NOT_RUN. No target achievement is claimed.

## M10 durable isolated replay and semantic comparison — 2 November 2026

Baseline source: **21ba06a78c9c6e2aa6ddc5a48eb474ef5b7b9f4e**; final runtime:
**0c5415009b4d23af7e545df24588a2d8c63e4650**. The replay
provider, canonical creation/status endpoints and optional worker are implemented.
See the [M10 handoff](m10_replay_handoff.md) for source-ID bindings, namespace
ownership, fixed replay clocks, provider pinning, retry semantics and limits.

Changed owned paths: migrations 007/008 and loader/readiness/version evidence;
curation/capture/quarantine effective namespaces; reducer/backfill namespace
projections; event-time replay clocks; typed Silver namespace and publication
lineage; durable replay queue/worker/repair/reference comparison; optional Compose
worker and checker evidence mount; owned pure/live/process-crash, ingress/client
and migration
regressions; owner/pipeline documentation. No public DTO/event/HTTP schema, shared
workflow, lock, evaluation config or another owner's code changed.

Original Bronze bytes, keys, ordered headers, topics/offsets, event IDs, original
document namespace, timestamps and content hashes are retained. Exact selected
sources and reference generations are durable; a new target must be empty and is
claimed against normal ingestion. Session locks and the existing sink dedup path
recover unfinished jobs. Provider hashes prevent resuming with a different code,
lock, dictionary or schema-ID mapping. Replay cannot mutate source pointers,
reset live groups or invoke operational commands. Repair evaluation uses new IDs
and existing quarantine references in isolation; it does not promote repairs.

Pinned publications receive exact logical-row/digest/count/state/money comparison.
Capture-only jobs retain null reconciliation because no published Gold reference
was supplied. A mismatch leaves a FAILED diagnostic target, not a source promotion.
Large exact monetary sums exceeding the existing reconciliation DTO int64 bound
fail closed with the unrounded values retained privately; coordinated DTO review
is still required. This comparison does not replace Jaineel's independent oracle.

Commands use the locked `.venv/Scripts/python.exe`. Docker and host pytest require
execution outside the sandbox for the engine pipe and Windows scratch ACLs.
Development tests use the then-dirty worktree with parent d4fda59 in fixture
metadata; they do not establish a clean-d4fda59 runtime result.

| Development command/check | Actual result | Evidence |
|---|---|---|
| Adapter `env up --profile streaming-local` | Passed, exit 0; original low-memory profile retained | artifacts/projectctl/8927d567-c1f6-4360-91a9-14dcc013d53d/ |
| Host `pytest test_replay.py test_silver.py test_vertical.py -q --tb=short` | 42 passed, 18.78 s | artifacts/m10/pure-development.xml |
| Real Linux `test_replay_live.py test_event_time_live.py test_business_gold_live.py` | 28 passed, 252.46 s | artifacts/m10/live-development.xml |
| Expanded `test_replay.py test_replay_live.py` | 20 passed, 172.05 s; includes two acknowledged process exits, historical future rejection and repair isolation | artifacts/m10/replay-development.xml |
| Added provider fingerprint/resume fence, same focused files | 21 passed, 184.09 s | artifacts/m10/replay-provenance-development.xml |
| Ruff lint/format; generated `projectctl.schemas --check` and `projectctl.conversation_contract --check` | Passed; 67 formatted files; generated contracts current | Session transcript |

| Source-pinned check | Actual result | Evidence |
|---|---|---|
| Adapter `db migrate --namespace bench-m10` | Analytics 1–7 applied. Global exit_code=4 remains truthful: other service/outbox providers absent | artifacts/infra/analytics/checks/f7e4bfc0-50ba-480d-b9bd-d85e4c0b8ad6/analytics-migration.json |
| Existing persistent M05 legacy Silver/Gold checkpoint replay, then replay again | COMPLETED, reconciliation passed, repeat target generation=1, original source pointer unchanged | artifacts/m10/legacy-smoke.json, checkpoint-reference.json |

The persistent smoke uses `docker exec ... python -m artifacts.m10.legacy_smoke`
inside the live checker. Its initial script-path invocation lacked the repository
module search path and failed to import before any work; the module invocation
above passed. The new replay is retained in its isolated public namespace.

Full Linux verification uses the normal storage-check mounts plus
`-f artifacts/m10/evidence.compose.yaml` to route earlier modules' sidecars under
artifacts/m10/regression-facts. It preserves prior checkpoint logs rather than
overwriting them. The primary M10 XML and source metadata remain under artifacts/m10.

The full correctness run began with a 0.5-CPU checker cap. The engine exposes eight
CPUs; the checker was increased to two CPUs during the long quality smoke, keeping
512 MiB memory. The ignored QA overlay records that cap for subsequent checks.
PostgreSQL/Kafka/registry limits and committed SUT profiles did not change. Exact
adjustment: artifacts/m10/checker-cpu-adjustment.json. These JUnit durations are
correctness-run timings, not comparable performance measurements.

| Review regression and correction | Actual evidence |
|---|---|
| A later recapture could make an originally future-invalid source valid | Source 21ba06a reproduced invalid=0 instead of 1; raw failure preserved in artifacts/m10/first-ingress-before.xml and .json. Final code freezes first durable source ingress and passes it separately from unchanged wrapper bytes |
| Provider expected target namespace in the header, while Jaineel's existing AnalyticsClient sends source namespace | Actual client against the real in-process app returned HTTP 400; preserved in artifacts/m10/client-contract-before.xml. Provider now accepts the source context and verifies it against selected references |
| API idempotency must follow that source context, including concurrent different targets | Migration 008 renames the key namespace without rewriting migration 007. A scoped transaction lock enforces one key/signature; the real SQL concurrency test accepts one request and rejects the other |
| Focused corrections before final source pin | 6 passed, 34.17 s; raw artifacts/m10/review-fixes-development.xml. This development run used the dirty working tree with parent 21ba06a, not clean 21ba06a |

The full suite completed on 21ba06a: **299 passed, 8 skipped**, 2,657.03 s
(artifacts/m10/linux-final.xml). The two additional review regressions were not
covered by that suite and were not hidden by its green result. Final source
0c54150 is checked with all affected replay/capture/API/migration/Kafka paths;
unchanged large publisher and quality fixtures are not repeated for these fixes.

| Final corrected-source verification | Actual result | Evidence |
|---|---|---|
| Source 0c54150, storage-check pytest: all replay files; event-time, vertical/capture/HTTP/publication/storage regressions; both native Kafka slices; 24-domain and migration backfill cases | **55 passed, 0 skipped**, 307.44 s | artifacts/m10/affected-final.xml |
| Source 0c54150, controlled actual Kafka pause/resume with explicit SQL outbox/relay double | **1 passed**, 46.45 s; pending notification survives outage and is marked sent only after recovered broker ack | artifacts/m10/dlq-final.xml, regression-facts/m09/dlq-recovery.json |
| First full Windows pipelines/contracts/integration run after Docker stopped | 333 passed, 126 skipped, 1 failed, 96.89 s: unchanged `test_absolute_deadline_includes_body_and_never_extends_for_retry[search]` sent zero requests before its 25-ms deadline | artifacts/m10/host-first.xml |
| Exact unchanged deadline case rerun | 1 passed, 0.48 s; no assertion/budget/client code changed | artifacts/m10/host-deadline-retry.xml |
| Final full Windows pipelines/contracts/integration rerun on 0c54150 | **334 passed, 126 skipped**, 76.80 s | artifacts/m10/host-final.xml |
| Generated schemas/OpenAPI and Ruff lint/format | Passed; 68 formatted files | Session transcript |
| Adapter migration after correction | Analytics **1–8** applied; global exit_code=4 still reports other owners' missing providers | artifacts/infra/analytics/checks/6fe1dac5-35e8-4b1a-83af-bc331dc307b7/analytics-migration.json |
| Adapter `env down`, then `docker desktop stop` | Exit 0; volumes retained, zero Desktop/backend processes | artifacts/projectctl/67797a9f-7a54-4def-b1ec-c67c5561ce60/, artifacts/m10/shutdown.json |

The host deadline failure is retained as a transient timing observation, not
attributed to a proven cause. Its 25-ms setup assumption can depend on scheduling;
neither the consumer nor its test was changed. All affected corrected-source
paths passed, including the actual existing AnalyticsClient contract. The complete
large/quality suite was not repeated after the focused fixes; its exact earlier
source and the final affected-source results are distinguished above.

**120 of the 126 Windows skips passed in Linux** across the full/focused/broker
runs. The same six older opt-in cases were not rerun. Skip names/reasons and
cross-platform coverage are retained in artifacts/m10/skips.json
and verification-final.json. Delivery uses the user's standing authorization to
commit/push completed modules to origin/vichitr. Actions status for the delivered
HEAD is recorded in artifacts/m10/github-actions.json; the three shared CI jobs
do not replace the locally executed live checks. Runtime files remain identical
to 0c54150; the delivery commit only updates owner documentation.

Next checkpoint: M11 baseline and measured experiments.

Remaining: real shared outbox/relay integration and actual operational stock/payment
invariants are NOT_RUN (providers absent; outbox/operational spies in tests are
explicit doubles). Full 100,000-record W-QUALITY, Harsh/Jaineel adoption, integrated
gates and performance claims remain pending. No memory allocation was increased,
development data deleted, or live event/group republished/reset.

## M09 event time, late revisions and DLQ fault boundary — 1 November 2026

Source revision: **b12dd0297125415a7cfb1662b34b5d914e61d158**. The owned provider
is implemented; actual Aditya outbox adoption remains pending. See the
[M09 handoff](m09_event_time_handoff.md) for timestamp semantics, SQL inspection,
provisional finality, lineage, timing cohorts and the broker controller procedure.
Next checkpoint: M10 isolated analytical replay.

Changed owned paths: migration 006 and its loader/readiness/version evidence;
curation partition clocks/watermarks/annotations; publication lineage and idle
reevaluation; fixed worker cadence; checker M09 artifact mount; owned event-time,
DLQ recovery and migration regression tests; owner documentation. Original event
bytes, public event/HTTP/analytics schemas, Parquet schemas, dictionaries, locks,
evaluation configs, shared workflow and other owners' code are unchanged.

The transaction retains late Silver facts, updates the existing Gold revision,
and records `LATE_RECONCILIATION`. A resumed idle partition cannot move a watermark
backward. The new views separate initial visibility from late correction and keep
missing/recovery timing honest. Quarantine still uses the required local outbox
binding and stops without it. The fault test pauses the actual Kafka container;
its SQL outbox/relay is an explicit test double, not Aditya's implementation.

Commands below use the locked `.venv/Scripts/python.exe`. Docker and host pytest
run outside the sandbox for the engine pipe and Windows scratch ACLs.

| Development command/check | Actual result | Evidence |
|---|---|---|
| `PROJECTCTL_ADAPTER_MODULE=infra.analytics python -m projectctl env up --profile streaming-local` | Services started; initial verification returned dependency failure `ConnectionTimeout` during concurrent cold startup | artifacts/projectctl/0284070d-c7fe-4737-8676-cfb287bfb301/ |
| Same adapter, `env verify --profile streaming-local` after readiness | Passed, exit 0, existing resource profile retained | artifacts/projectctl/283edef3-2141-483e-9b34-f37a4f7324c1/ |
| `python -m pytest tests/pipelines tests/contracts tests/integration -q --tb=short --junitxml=artifacts/m09/host-development.xml` | 327 passed, 103 skipped, 1 failed in 256.33 s; unchanged `test_http_client_uses_merged_schema_binding` hit `DependencyUnavailable` during concurrent Docker startup. Failure retained; no timeout/assertion weakened | artifacts/m09/host-development.xml |
| Real Linux `test_event_time_live.py test_event_time.py` with `RUN_VERTICAL_LIVE_TESTS=1` | 6 passed in 19.67 s; initial five live cases plus worker cadence | artifacts/m09/event-time-development.xml |
| Real broker pause/recovery, SQL outbox/relay double | 1 passed in 41.24 s | artifacts/m09/dlq-development.xml, dlq-recovery-development.json |

Development fixture metadata records parent 35cd2f5 while executing the then-dirty
worktree. It is not a claim of testing clean 35cd2f5. Final tests use clean b12dd02.

| Source-pinned command/check | Actual result | Evidence |
|---|---|---|
| `RUN_VERTICAL_LIVE_TESTS=1 M09_BROKER_OUTAGE=1`, storage-check pytest `test_dlq_recovery_live.py` with host `docker pause/unpause group3-postgres-local-kafka-1` and marker acknowledgements | 1 passed, 36.06 s; pending=1 during unconfirmed send, pending=0 only after recovered broker acknowledgement; one invalid source, zero business facts | artifacts/m09/dlq-final.xml, dlq-recovery.json, dlq-ready.json |
| Adapter `db migrate --namespace bench-m09` | Analytics migrations 1–6 applied. Global exit_code=4 remains truthful: other service/outbox providers absent | artifacts/infra/analytics/checks/6ceb274f-467b-4acc-a9ee-4d1580711019/analytics-migration.json |
| Read-only public analytics inspection | Existing generation-one Silver/Gold checkpoints retained; migration versions 1–6; historical facts have no fabricated event-time annotations | artifacts/m09/public-database.json |
| `ruff check pipelines infra/analytics.py tests/pipelines`; corresponding `ruff format --check` | Passed; 60 formatted files | Session transcript |
| `python -m projectctl.schemas --check`; `python -m projectctl.conversation_contract --check` | Passed; generated contracts current, external owner review still pending | Session transcript |

| Final source-pinned verification | Actual result | Evidence |
|---|---|---|
| Storage-check full `python -m pytest tests/pipelines -q --tb=short --junitxml=artifacts/m09/linux-final.xml`, `RUN_VERTICAL_LIVE_TESTS=1 RUN_STORAGE_LIVE_TESTS=1 M05_CODE_COMMIT=b12dd0297125415a7cfb1662b34b5d914e61d158` | **277 passed, 8 skipped**, 478.27 s; includes owned SQL/files/native Kafka, candidate/crash/large publication, quality smoke and seven new live event-time cases | artifacts/m09/linux-final.xml |
| Final Windows `python -m pytest tests/pipelines tests/contracts tests/integration -q --tb=short --junitxml=artifacts/m09/host-final.xml`, Docker stopped | **328 passed, 105 skipped**, 49.49 s; prior contract timeout passed unchanged | artifacts/m09/host-final.xml |
| Skip reconciliation | **99 of 105 host skips passed in Linux**, including the separately controlled real-broker fault. Six older opt-in checks not rerun. Linux's other two skips are that separately passed fault and the Windows-only guard passed on host | artifacts/m09/skips.json, verification-final.json; [skip explanation](test_skips.md) |
| Adapter `env down`, then `docker desktop stop` | Exit 0; volumes retained, zero Desktop/backend processes | artifacts/projectctl/f6778034-4e54-4547-804c-8bb577dfbb82/, artifacts/m09/shutdown.json |

The unchanged contract test passed after Docker stopped; the initial failure
coincided with cold-start resource contention, but that causal explanation is
an inference. No test budget or assertion was changed. The complete Linux run
and host rerun execute b12dd02 runtime/migrations/tests; subsequent changes are
owner documentation only. The source-pinned broker test was a separate pass
because it requires deliberate external pause/resume acknowledgements.

Delivery uses the standing user authorization: commit the final owner evidence
notes and push the source/documentation commits to `origin/vichitr`. Exact Actions
status for the delivered HEAD is retained in artifacts/m09/github-actions.json.
The three shared CI jobs do not replace the locally executed live M09 checks.

Remaining: actual shared outbox/relay storage/retry, full 100,000-record W-QUALITY,
integrated G0/G1/G3/G4/T-03/T-12, labelled quality imports and real Harsh compactor
adoption are not established by this checkpoint. No performance result is claimed.
No memory allocation was increased and no development volume/data was deleted.

## M08 incremental publication and candidate safety — 1 November 2026

Implementation is ready for final source-pinned verification. See the
[M08 handoff](m08_publication_handoff.md) for exact behavior, integrity format,
resource bounds and the required Harsh/Jaineel review. This checkpoint does not
claim Harsh's actual compactor, full W-QUALITY, integrated T-04/T-12 or performance.

Changed owned paths: analytics migration 005 and migration loader/readiness/version
evidence; storage FileStore streaming verification/durability, Parquet batch reads,
incremental publication/lineage/membership, candidate validator and pinned readers;
business SQL projection helpers and pipeline candidate method; checker read-only
services/config mounts and M08 artifact mount; owned regression fixtures, digest,
candidate, crash and large publisher tests; owner/pipeline documentation. Public
DTOs, event/HTTP schemas, dictionaries, shared workflow, locks, evaluation configs
and other owners' implementation remain unchanged.

- Repeatable read freezes pending/new-visible identities in SQL. Silver appends
  fresh facts, including legacy-schema coexistence. Gold replaces dirty partitions
  in bounded files. Membership deltas inherit retained parent generations rather
  than copying all source IDs per publication. The internal iter_membership helper
  resolves complete sets, including older full-set generations.
- Version-2 lineage uses hashed member shards plus parent roots; source ranges
  preserve gaps through exact membership references. Old files/roots remain intact.
- Paired pointer CAS, frozen pending-ID deletion and bounded durable observation
  jobs preserve concurrent ingestion and truthful first visibility. Seven real
  child-process crash cases print barrier acknowledgements before abrupt exit.
- Candidate validation reads pinned files, checks unique logical keys, exact rows,
  byte-sorted framed SHA-256, counts, currency integrity sums, physical metadata and
  durable files, then rechecks the base generation. Compaction inherits membership
  without new visibility or clearing new ingress.
- The total 10,000-fact / 8-MiB snapshot cap is removed. Files use 512-row/4-MiB
  chunks; single-row 8-MiB and uncompressed row-group 32-MiB guards remain explicit.
  Temp sorts use 4-MiB work_mem. Manifest metadata and unpaginated query responses
  still grow with file/returned-row counts. No memory allocation was increased.
- ManifestCandidate's existing Money/int64 aggregate-total cap conflicts with
  larger valid Gold sums. Such candidates fail closed. A widened DTO needs
  Harsh/Jaineel/Vichitr review; no rounding or silent public-contract change occurs.

Development checks used the uncommitted working tree with base revision 62aa5cf
in live fixture metadata; they are not final-source or performance claims.
Commands use `.venv/Scripts/python.exe` from the repository root; Docker/pytest
needed execution outside the sandbox for the engine pipe and Windows scratch ACLs.

| Development command/check | Actual result | Evidence |
|---|---|---|
| `PROJECTCTL_ADAPTER_MODULE=infra.analytics python -m projectctl env up --profile streaming-local` | Existing low-memory services verified, exit 0 | artifacts/projectctl/3aa7d411-c817-43c2-b81a-91966e766d17/ |
| Existing real vertical/publication/business suites | 23 passed, 28.93 s | artifacts/m08/streaming-first.xml |
| First new candidate suite | 17 passed, 1 failed: independent fixture assertion mistakenly added five rather than three amount projections | artifacts/m08/candidate-first.xml |
| Corrected candidates + seven acknowledged process-kill cases | 25 passed, 53.40 s | artifacts/m08/candidates-and-crashes.xml |
| Additional physical guards, actual commit CAS and business/migration regressions | 36 passed, 327.83 s; no deadlock/timeout | artifacts/m08/candidate-guards-and-migrations.xml |
| Incremental membership inheritance, candidate/physical guards, publication and seven process kills | 37 passed, 94.47 s | artifacts/m08/incremental-membership.xml |
| First host pipelines/contracts/integration suite | 327 passed, 90 skipped, 50.30 s; before final additional guard cases | artifacts/m08/host-development.xml |
| Publisher-only 10,001-event fixture, real Bronze/receipts + bulk accepted staging | 1 passed, 263.35 s; 20 Silver files, max 512 rows, unique Gold count 10,001. Not a B0/Kafka/performance trial | artifacts/m08/large-publisher-first.xml |
| `PROJECTCTL_ADAPTER_MODULE=infra.analytics python -m projectctl db migrate --namespace bench-m08` | Analytics versions 1–5 APPLIED; expected global dependency exit 4 for other service/outbox composition | artifacts/infra/analytics/checks/510d2480-d196-4c97-8f00-0e874133028b/analytics-migration.json |

The amount fixture now independently asserts 12,345 +12,345 +12,345 =37,035:
order amount, daily-created amount and daily-confirmed amount. This is a physical
integrity sum across projections, not revenue. No production arithmetic was changed
to accommodate the test. The initial large fixture was tightened before final
verification to construct its document/hash from the original encoded wire bytes,
and to assert the event-identity lookup index through an actual query plan.

One diagnostic attempted to inspect the slow guard run after its container had
already completed, returning “No such container”; raw test XML independently shows
all 36 cases passed. Earlier read-only wait inspection showed no blocked backend.
The slow run is a test duration, not benchmark evidence. Lint/format feedback and
one patch-context mismatch were corrected without relaxing assertions. Raw failed
and successful XML is retained. Final verification/delivery results follow below.

Final legacy review reproduced one lineage defect: compacting a snapshot with an
older transform retained the manifest/row version but labelled the new lineage
root with the current pipeline default. artifacts/m08/legacy-transform-before.xml
retains the failing real SQL/file probe. Candidate roots now explicitly inherit
the pinned base transform; the regression is in test_publication_live.py. The
complete suite began on 560e905, and its candidate/crash cases had finished before
this one-field correction. All candidate/crash cases and the complete host suite
are rerun on the corrected source. Publisher/export code is unchanged by this fix.

### Final M08 verification and delivery

Full-suite source: **560e90591bbdf32a12d74b0755e5df7706f8a6a4**. Corrected
candidate source: **dda52f8804545d5b86c94d3ecc3a7cdbfcebba95**. The only runtime
change between them is the compaction lineage transform label; all affected
candidate/crash cases and the complete host suite passed again. The complete
Linux suite was not repeated for that isolated metadata correction. Both source
snapshots and development/final crash/large-fixture facts remain retained.

| Final check | Actual result | Evidence |
|---|---|---|
| Complete host pipelines/contracts/integration, corrected source | **327 passed, 97 skipped**, 68.80 s; zero failures/errors | artifacts/m08/host-corrected.xml |
| Complete Linux pipeline suite, full-suite source | **268 passed, 7 skipped**, 616.58 s; real Kafka/PostgreSQL/files, large fixture and process kills | artifacts/m08/linux-final.xml |
| All affected candidate/crash tests, corrected source | **32 passed, zero skipped**, 98.04 s; includes historical-transform regression | artifacts/m08/legacy-transform-corrected.xml |
| Large publisher-only fixture in the complete suite | 10,001 unique IDs, **18,920,787 document-text bytes**, 20 Silver files with at most 512 rows, Gold count 10,001; zero pending/unobserved visibility | artifacts/m08/large-publisher-fixture.json |
| Event-identity lookup plan after actual fixture ANALYZE | EXPLAIN selects Index Scan on source_receipts_event; no throughput claim | artifacts/m08/visibility-query-plan.json |
| Retained original M05 dataset | Versions 1–5, idempotent migration, unchanged canonical hash and readable legacy Silver; generation 1 / Gold count 1 retained | artifacts/m08/upgrade.json |
| Final lint/format, generated schema/OpenAPI, diff, source hash, owned-path/credential and local-link checks | Passed; no public contract or other owner's implementation change | Session transcript; artifacts/m08/source-snapshot*.json |
| Exact skip reconciliation | **91 of 97 host skips passed in Linux** across full/focused runs; six older opt-in checks not rerun. Linux's seventh skip is the Windows-only guard, passed on Windows | artifacts/m08/{verification-final,skips}.json; [skip report](test_skips.md) |

Exact final commands from the repository root:

```powershell
.venv/Scripts/python.exe -m pytest tests/pipelines tests/contracts tests/integration -q --tb=short --junitxml=artifacts/m08/host-corrected.xml
$env:POSTGRES_SECRETS_DIR=(Resolve-Path artifacts/infra/postgres-local/secrets).Path
$taskCommit=git rev-parse HEAD
docker compose -p group3-postgres-local -f infra/compose.yaml -f infra/compose.streaming.yaml -f infra/compose.storage.yaml --profile storage-check run --rm --no-deps -e RUN_VERTICAL_LIVE_TESTS=1 -e RUN_STORAGE_LIVE_TESTS=1 -e M05_CODE_COMMIT=$taskCommit storage-check python -m pytest tests/pipelines -q --tb=short --junitxml=artifacts/m08/linux-final.xml
docker compose -p group3-postgres-local -f infra/compose.yaml -f infra/compose.streaming.yaml -f infra/compose.storage.yaml --profile storage-check run --rm --no-deps -e RUN_VERTICAL_LIVE_TESTS=1 -e M05_CODE_COMMIT=$taskCommit storage-check python -m pytest tests/pipelines/test_publication_live.py tests/pipelines/test_publication_crash_live.py -q --tb=short --junitxml=artifacts/m08/legacy-transform-corrected.xml
```

Use 560e905 for the recorded complete Linux run and dda52f8 for the corrected
host/focused runs; do not rewrite their metadata to a later documentation commit.
The checker now mounts services/configs read-only, so earlier M07 collection/input
mount omissions do not recur. The retained-file helper used CODE_COMMIT, PYTHONPATH=/app
and EVENT_SCHEMA_CACHE_PATH=/app/schema-cache.json, as at M07.

This provider checkpoint is delivered to `vichitr` under the standing push policy.
The final delivery changes owner documentation only after the verified source.
The existing three-job GitHub workflow runs P5/P6/integration checks; new real
pipeline cases run locally. Current-HEAD remote status is retained in
artifacts/m08/github-actions.json. Actual Harsh compaction/T-04, full W-QUALITY,
real outbox/catalogue integration, labelled quality and performance remain NOT_RUN.
The int64 aggregate-total contract limit and row/row-group guards remain explicit.
Next implementation checkpoint: M09 late data and watermarking.

After verification, env down completed with every volume retained:
artifacts/projectctl/f63a2170-8ab3-48b5-874d-f552a2ca86d1/. Docker Desktop stop
completed and zero Desktop/backend processes remained; artifacts/m08/shutdown.json
records the state. Docker RAM allocation was not increased. Restart the documented
streaming-local profile before further live work.

## M07 business Gold provider — 1 November 2026

M07's business provider is implemented: latest order/payment/search facts, current
daily checkout conversion, distinct historical funnel stages, distinct reservation
failures and exact search duration references. Labelled evaluation imports remain
blocked on actual Jaineel/Harsh artifacts and a reviewed import contract. Full
G3/end-to-end commerce is not claimed. See [M07 handoff](m07_business_gold_handoff.md).

Changed owned paths: migration 004; gold/business.py and reducer entry point;
curation savepoint/conflict handling; migration loader/readiness/version evidence;
business Parquet schemas, frozen publication/dirty partitions and pinned readers;
checker artifact mount; pipeline READMEs; M07 tests, migration-version assertion
and owner docs. Existing migrations 001–003, public schemas/DTOs, dependencies,
application lock, workflow and other owners' code remain unchanged.

The additional reducer contribution key supports migration-time backfill without
recounting pipeline_minute. Latest facts project through SQL views so old categories
are replaced atomically. Per-event dirty membership protects concurrent arrivals
when frozen IDs are published. Business conflicts roll back Silver and reducer
effects before transactional quarantine. Unexpected database errors retain the
captured unfinished source for retry. Exact integer sums survive Parquet and JSON,
including a sum above int64. Existing 10,000-fact/8-MiB safety limits remain; M08
incremental loading is next. No synthetic performance numbers are reported.

Development commands use `.venv/Scripts/python.exe` from the repository root.
Pytest/Docker calls required execution outside the sandbox for Windows scratch
ACLs and the Docker engine pipe. Live source metadata identifies base revision
4616805 while the working changes were under development; final source-pinned
verification will be recorded below after the feature commit.

| Command/check | Actual result | Evidence |
|---|---|---|
| `PROJECTCTL_ADAPTER_MODULE=infra.analytics python -m projectctl env up --profile streaming-local` | Existing low-memory PostgreSQL/Kafka/registry verified, exit 0 | artifacts/projectctl/f7e5dbaf-5801-46dc-9217-465336e80fc6/ |
| `pytest tests/pipelines tests/contracts tests/integration -q --tb=short --junitxml=artifacts/m07/host-development.xml` | 325 passed, 61 skipped; before final unit/capacity/upgrade cases | artifacts/m07/host-development.xml |
| First real business suite | 8 passed, 1 failed: new test incorrectly expected captured source deletion on sink failure | artifacts/m07/linux-business-development.xml |
| Corrected test + capacity/actual migration upgrade cases | **11 passed**, 16.52 s; unfinished receipt, zero reducer effects, successful retry asserted | artifacts/m07/linux-business-development-fixed.xml |
| Affected Linux storage/vertical/Silver/Kafka and business suite | **85 passed, 1 Windows-only skip**, 189.40 s; before final capacity case | artifacts/m07/linux-regressions-development.xml |
| `pytest tests/pipelines/test_business_gold.py -q --tb=short --junitxml=artifacts/m07/unit-exact-representation.xml` | 1 passed | artifacts/m07/unit-exact-representation.xml |
| `PROJECTCTL_ADAPTER_MODULE=infra.analytics python -m projectctl db migrate --namespace bench-m07` | Analytics versions **1–4 APPLIED**. Expected global dependency exit 4 for other service/outbox composition | artifacts/infra/analytics/checks/fd0806b1-1536-4aeb-b393-be63739d53ff/analytics-migration.json |
| Ruff check/format; projectctl.schemas `--check`; projectctl.conversation_contract `--check`; diff check | Passed. Initial generated-check invocation used unsupported positional `check`; rerun with documented `--check` passed | Session transcript |

The real tests cover late parents, stale versions, historical milestones after
cancellation/reversal, multi-SKU reservation identity, conflicting reasons/outbox
atomicity, corrected cohorts/zero denominators, exact money/durations, HTTP JSON,
concurrent arrival, source retry and idempotent actual 003-to-004 upgrade. Producer
events are explicit synthetic fixtures. Invalid notification tests use the explicit
SQL outbox double, not Aditya's absent production implementation. The smaller
2,000-record quality smoke is regression coverage, not full W-QUALITY.

Final review of the initial source commit 779c950 found one additional semantic
defect: after a corrected creation date, an older order snapshot arriving last
did not register its empty historical cohort. The new two-permutation regression
reproduced it (1 passed, 1 failed; artifacts/m07/cohort-order-before-fix.xml).
The reducer now registers known cohort dates/currencies from every accepted order
snapshot, while only the newest version updates current state. Empty cohort rows
therefore do not depend on delivery order. The raw failure remains retained.
All **12 business cases passed** after the fix, 19.59 seconds:
artifacts/m07/business-after-cohort-fix.xml. The initial source's final Windows
suite passed 326/63 skipped; its complete Linux suite passed 234/7 skipped.
These are retained as initial-source results, not final-source claims.

### Final source verification and delivery

Initial feature: **779c950ed5b2730dbf9cbd3abbc829bf448f236b**. Corrected and
final verified implementation: **8abde279da5574d5be9263e52c7a7319c3f77881**.
artifacts/m07/source-snapshot.json records physical/Git hashes for all 20 changed
paths; source-snapshot-initial.json retains the initial checkpoint.

| Final source-pinned check | Actual result | Evidence |
|---|---|---|
| `pytest tests/pipelines tests/contracts tests/integration -q --tb=short --junitxml=artifacts/m07/host-final-corrected.xml` | **326 passed, 64 skipped**, 38.61 s; zero failures/errors | artifacts/m07/host-final-corrected.xml |
| Complete Linux `pytest tests/pipelines -q --tb=short --junitxml=artifacts/m07/linux-final-corrected.xml` | **235 passed, 7 skipped**, 219.55 s; zero failures/errors | artifacts/m07/linux-final-corrected.xml |
| Retained original M05 dataset/file verification | Versions 1–4; idempotent migration; original content hash, legacy silver-conversation-turn files, generation 1 and Gold count 1 retained | artifacts/m07/upgrade.json |
| Final lint/format and generated schema/OpenAPI checks | Passed; no generated contract change | Session transcript |
| JUnit reconciliation and exact skip inventory | 58 of the 64 host skips passed in Linux; six older opt-in checks remain unrerun. Linux's seventh skip is the Windows guard, which passed on Windows | artifacts/m07/{verification-final,skips}.json; [skip report](test_skips.md) |

The Linux command used the existing storage-check image/profile and real retained
services. Exact PowerShell setup from the repository root:

```powershell
$env:POSTGRES_SECRETS_DIR=(Resolve-Path artifacts/infra/postgres-local/secrets).Path
$taskCommit=git rev-parse HEAD
$taskServicesMount=(Resolve-Path services).Path + ':/app/services:ro'
$taskConfigMount=(Resolve-Path configs).Path + ':/app/configs:ro'
docker compose -p group3-postgres-local -f infra/compose.yaml -f infra/compose.streaming.yaml -f infra/compose.storage.yaml --profile storage-check run --rm --no-deps --volume $taskServicesMount --volume $taskConfigMount -e RUN_VERTICAL_LIVE_TESTS=1 -e RUN_STORAGE_LIVE_TESTS=1 -e M05_CODE_COMMIT=$taskCommit storage-check python -m pytest tests/pipelines -q --tb=short --junitxml=artifacts/m07/linux-final-corrected.xml
```

Broader-test environment failures were preserved and resolved through test input
mounts, without changing assertions or production code: the first expanded run
could not import services (artifacts/m07/linux-final.xml, one collection error);
the next had 231 passes/7 skips/3 missing-config failures
(linux-final-verified.xml). Read-only services/ and configs/ mounts resolved both.
The config diagnostic passed all three cases, the initial source then passed
234/7 skipped (linux-final-complete.xml), and the corrected source passed the
complete final suite above. The standalone retained-file helper also initially
needed PYTHONPATH=/app; its corrected command passed with CODE_COMMIT set to the
verified revision and EVENT_SCHEMA_CACHE_PATH=/app/schema-cache.json.

This checkpoint is delivered to `vichitr` under the standing module push policy.
The final delivery changes only owner documentation after the verified source.
The existing three-job GitHub workflow runs P5/P6 and integration checks; it does
not run these new live pipeline tests. Its current-HEAD result is tracked in
artifacts/m07/github-actions.json and the repository's Actions page; local real
provider evidence remains the basis for M07 verification. No new shared workflow
or other owner's test implementation was changed.

After verification, `PROJECTCTL_ADAPTER_MODULE=infra.analytics python -m projectctl
env down` passed (artifacts/projectctl/31e9b2c8-1ab1-49b2-9065-5e476019feba/),
retaining every volume. `docker desktop stop` completed; zero Desktop/backend
processes remained. Evidence: artifacts/m07/shutdown.json. Docker RAM allocation
was not increased. Restart the documented profile before further live work.

Labels, real operational integration, full W-QUALITY, scale/performance and M08
candidate publication remain pending; see the handoff for owners and exact bounds.

## CI follow-up — HTTP metric tests, 1 November 2026

The user explicitly authorized reading the failed GitHub evidence, then requested
the test fix. This authorizes the narrow edit to Jaineel's
tests/telemetry/test_collectors.py; no production collector/harness code changed.

Both Windows failures (runs 41282911833 and 41283612895, commits 58b7b67 and 2c4cdb5)
had **625 passed, one failed**: test_actual_http_metrics_scrape_does_not_invent_absent_metrics.
The 500-ms asyncio deadline starts before constructing httpx.AsyncClient. An
unmodified local diagnostic reproduced the failure: first client construction
**576.72 ms**, no request reached the already-ready local server; later scrapes
took **28.16/26.97 ms**. Explicit slow-setup controls confirmed the timer placement.
Raw evidence: artifacts/m06/ci-investigation/{41282911833,41283612895}/{checks.json,pytest.xml}
and scrape-startup-probe.json. The saved GitHub credential was used only in memory
for GitHub API authentication; it was not displayed or saved with evidence.

The two real-HTTP metric semantics tests now receive a preinitialized real client
through an explicit test-only constructor seam. They still use a real localhost
server/transport, the default 500-ms scrape budget, unchanged TLS defaults and
the original missing-metric/stale-sample assertions. A new withheld-response case
proves that an actual request reaches the server and still times out. The client
is closed after each case, including failure cleanup. No fake HTTP response,
larger deadline, production change or skipped test was introduced.

Commands and evidence:

- `.venv/Scripts/python.exe -m pytest tests/telemetry/test_collectors.py -q --tb=short
  --junitxml=artifacts/ci-metrics-test-fix/collectors.xml`: **14 passed**, 4.34 seconds.
- Three fresh Python processes each ran the missing-metric, stale-sample and
  withheld-response cases by full pytest node ID: **3 passed** in each,
  2.46/2.49/2.43 seconds. XML: artifacts/ci-metrics-test-fix/cold-{1,2,3}.xml.
- Those three exact node IDs are tests/telemetry/test_collectors.py:: followed by
  test_actual_http_metrics_scrape_does_not_invent_absent_metrics,
  test_http_scrape_rejects_explicit_stale_sample_timestamp and
  test_http_scrape_still_times_out_waiting_for_response. Each invocation used
  `-q --tb=short --junitxml=artifacts/ci-metrics-test-fix/cold-<trial>.xml`.
- `.venv/Scripts/python.exe benchmarks/manual/verify_p5.py`: **11/11 checks passed**,
  including **627 tests**, 120.99 seconds. Evidence:
  artifacts/p5/6a2f291a-f647-4649-92da-f62cc76b1a7c/checks.json and pytest.xml.
- Ruff lint/format and diff checks passed. This follow-up is delivered to vichitr;
  remote workflow evidence is retained in artifacts/ci-metrics-test-fix/github-actions.json.

This is the requested **test-only** repair. Production PrometheusReader still
constructs a client inside each scrape deadline. Jaineel's production follow-up
is to prepare/reuse/close its client outside timed observation startup, with the
network deadline and missing-data semantics preserved. CI passing does not
establish that this production cold-start limitation has been repaired.

## M06 — All-domain Silver provider, 1 November 2026

Implemented all 24 registered business types, canonical-model normalization and
typed all-domain Parquet. B0, original bytes/hashes, explicit nulls and caller-owned
transaction/offset safety remain unchanged. Business Gold reducers are still M07.
Full W-QUALITY/G0/G1/G4 are **NOT_RUN**, not inferred from the smaller quality smoke.
See [M06 handoff](m06_silver_handoff.md) for exact limits and consumer coordination.

Changed owned paths: analytics migration 003; curation provider/normalization;
pipeline_minute; ingestion receipts/API/runtime/worker; Parquet/publication/readers;
infra migration evidence and checker artifact mount; pipeline READMEs; owned fixture,
Silver tests and the former unsupported-TOOL_CALLED regression; this handoff/progress.
No public event/HTTP DTO, dictionary, registry asset, shared workflow, dependency,
application lock or other owner's implementation changed.

- Migration 003 backfills normalized payloads and makes aggregate versions unique
  across event types within the producer/aggregate. Immutable migrations 001/002
  and prior files remain unchanged. Older distinct versions are retained.
- The worker subscribes to all five business domains; storage/connection/SQL
  serialization/deadlock failures have three bounded retries with fresh consumer
  groups. Permanent failures and missing outbox stop without dirty classification.
- Fixed a real M05 quarantine API defect: required next_cursor was absent. Added
  ordered nonempty/empty pagination coverage. Fixed shared mutable intent examples
  at their owned fixture source; no assertion was weakened.
- The existing wrong-money-type reason is INVALID_AMOUNT; Jaineel's independent
  logical recipe expects INVALID_TYPE. Public behavior is preserved. This precise
  reason handoff needs joint review before a full W-QUALITY reason-count claim.

Development evidence (before the final source revision):

| Command/check | Actual result | Evidence |
|---|---|---|
| Focused host normalization/Parquet/B0 | 35 passed, 1.85 seconds | artifacts/m06/unit-first.xml |
| First full host pipelines/contracts/integration | 322 passed, 50 skipped, two failures caused by shared mutable intent fixture state | artifacts/m06/host-first.xml |
| Host rerun after fixture isolation | **325 passed, 52 skipped**, 46.19 seconds | artifacts/m06/host-second.xml |
| First Linux storage/vertical/Silver/native Kafka suite | 83 passed, one Windows-only skip, two failures exposed missing quarantine next_cursor; 151.44 seconds | artifacts/m06/linux-first.xml |
| Linux rerun of all new Silver cases and publication/API regressions after cursor fix | **40 passed**, 142.75 seconds | artifacts/m06/linux-second.xml |
| Existing low-memory streaming env up | CLI exit_code 0; real PostgreSQL/Kafka/registry mappings verified | artifacts/projectctl/a82d4fee-a41d-456f-8031-5e2413673772/ |
| Public local analytics db migrate | Analytics versions **1,2,3 APPLIED**; expected global dependency exit_code 4 for other owners/outbox | artifacts/infra/analytics/checks/9e15fddc-e0ee-4a6b-85a7-5c215904843c/analytics-migration.json |
| Ruff lint/format, generated schemas/OpenAPI and diff check | Passed; format check covered 45 files | Session |
| Owned-path and exact project-credential delivery scan | Passed; 23 feature paths before progress update | artifacts/m06/source-audit.json |

### Source-pinned checkpoint

Implementation commit **54c5238de9b310ffa9642217d8be07b65e7a9f42**. Its 18 non-Markdown
delivery file hashes are in artifacts/m06/source-snapshot.json. Final test facts
identify this source revision. Earlier development facts are in development/;
prior M05 facts were copied to prior-m05-facts/ before fresh tests overwrote them.
Development fixtures are not reproducible performance evidence.

| Command/check | Actual result | Evidence |
|---|---|---|
| `.venv/Scripts/python.exe -m pytest tests/pipelines tests/contracts tests/integration -q --tb=short --junitxml=artifacts/m06/host-final.xml` | **325 passed, 52 skipped**, 41.88 seconds | artifacts/m06/host-final.xml |
| Existing 512-MiB checker, RUN_VERTICAL_LIVE_TESTS=1, RUN_STORAGE_LIVE_TESTS=1, M05_CODE_COMMIT=54c5238 full revision; ten exact test files listed below | **85 passed, 1 skipped**, 167.89 seconds | artifacts/m06/linux-final.xml |
| All-domain SQL/active Parquet | 24 new valid +24 duplicate deliveries +24 redelivery no-ops; 48 source dispositions; all 24 types in active files | artifacts/m06/all-domains.json |
| Native Kafka on all five domain topics | Five new valid +five duplicates; committed next offset 2 on every partition; Gold count one per event type | artifacts/m06/kafka-domains.json |
| Real SQL/file quality smoke, explicit SQL outbox double | Exactly **1,970 new valid +20 duplicate +10 invalid =2,000 source dispositions**; ten raw recoveries, ten notices and active Gold count 1,970 | artifacts/m06/quality-smoke.json |
| Fresh Linux checker `python -m artifacts.m06.verify_upgrade` with CODE_COMMIT pinned | **PASS**: migration versions 1/2/3/idempotence, normalized backfill, unchanged original hash, existing M05 Silver schema/files and Gold generation/count 1 | artifacts/m06/upgrade.json |
| `.venv/Scripts/python.exe benchmarks/manual/verify_p5.py` | **All 11 checks passed**, including **626 tests**, 135.75 seconds; no real SUT/performance claim | artifacts/p5/bc09684f-0b9f-4c63-8021-4b9a27b14195/checks.json |
| `PROJECTCTL_ADAPTER_MODULE=infra.analytics`, `python -m projectctl env down` | CLI exit_code **0**, all volumes retained | artifacts/projectctl/7fef28bb-297a-4918-8539-62965f89a619/ |

The Linux command is `python -m pytest` followed by these exact paths under
tests/pipelines/: test_storage.py, test_storage_live.py, test_analytics_adapter.py,
test_vertical.py, test_vertical_live.py, test_vertical_publication_live.py,
test_vertical_kafka_live.py, test_silver.py, test_silver_live.py and
test_silver_kafka_live.py; then `-q --tb=short --junitxml=artifacts/m06/linux-final.xml`.
The existing Compose storage-check service supplies the named volume, analytics
secret and verified schema cache. No application image/dependency rebuild or RAM
increase was needed. All 46 relevant host skips passed in Linux; six unchanged
older live checks were not rerun. See [test_skips.md](test_skips.md).

The first ignored compatibility-helper invocation by script path lacked the
repository import path; the identical assertions passed through Python's module
entrypoint. The first env-down invocation mistakenly supplied unsupported
`--profile streaming-local`, returned CLI input exit_code 2 and changed nothing;
its evidence is artifacts/projectctl/eed4c7a1-d783-462a-9bb7-b2f478334605/. The
supported invocation above then stopped the stack. No test/assertion was weakened.
`docker desktop stop` also completed; no Docker Desktop/backend processes remained.
All data volumes and credential files were retained.

Full W-QUALITY, real shared-outbox notifications, real catalogue/dictionary/SKU
reconciliation, independent G0/G1/G4, business Gold reducers, full publication and
performance remain **NOT_RUN**. The historical GitHub Windows P5 failures are now
diagnosed; see the CI follow-up above for authorized log access and the test-only
repair. Final GitHub
branch status is retained separately in artifacts/m06/github-actions.json after
delivery. Next checkpoint: M07 business Gold and parent-late reconciliation.

## M05 — First Silver/active-Gold provider, 1 November 2026

Implemented within owned analytics, pipeline, infrastructure and test paths.
Full G1 is **not claimed**: Aditya's real outbox is absent in this checkout and
Jaineel's independent G1 provider adoption remains pending. See
[M05 handoff](m05_vertical_handoff.md). Source-pinned verification is recorded below.

- New immutable analytics migration 002 (001 unchanged) adds Silver/contribution
  keys, pipeline_minute staging, pending IDs, paired manifest pointers, exact event
  membership, visibility observations and the ordered receipt journal.
- pipelines/curation provides B0 CONVERSATION_TURN validation/dedup/atomic sink,
  strict batch controls, source corruption fencing, version/content conflict
  quarantine and post-commit observations. Missing outbox fails closed. Explicit
  test doubles never become a production outbox. DirtyPartitionSet is an owned
  canonical DTO; aggregate_gold requires the caller's active transaction.
- pipelines/storage adds stable typed Zstandard/UTC Parquet, verified file reads,
  bounded repeatable-read snapshots, namespace publisher locks, unchanged-file
  reuse, paired pointer CAS, exact-ID pending deletion and generation-pinned queries.
  The current full snapshot stops above 10,000 facts/8 MiB uncompressed document
  text; incremental publication/compactor admission remain M08.
- pipelines/ingestion adds the actual read API and explicit runtime/B0 worker.
  Internal operations use the environment bearer token. Replay and other reducers
  remain unavailable. API SQL gauges are namespace-scoped; separate worker counter
  collection/full benchmark instrumentation still need harness integration.
- infra/compose.analytics.yaml supplies opt-in localhost:8006 API and worker,
  384 MiB/0.5 CPU each, using existing locked Python dependencies and read-only
  source/cache mounts. No .env, raw data or credential enters its image/context.
  Application readiness stays 503 while the real outbox is missing.

Development verification (before the final source commit):

| Check | Actual result | Evidence |
|---|---|---|
| Initial real SQL/files suite | 4 passed, 1 fixture error: payload is a dictionary, not a Pydantic payload object. Fixed fixture access without weakening assertions | artifacts/m05/live-first.xml |
| SQL/files/API/concurrent-snapshot suite | 10 passed, 17.46 seconds | artifacts/m05/live-second.xml |
| Expanded native Kafka, SQL pointer rollback and recovery suite | 12 passed, 19.80 seconds | artifacts/m05/live-third.xml |
| Initial offline M05 boundaries | 8 passed, 24.50 seconds | artifacts/m05/unit.xml |
| Host pipeline/contracts/integration | 297 passed, 45 skipped, 45.67 seconds | artifacts/m05/host-first.xml |

The host skips comprise 24 POSIX filesystem cases, three M04 live cases, six older
infrastructure/transport cases and twelve new M05 live cases. New M05 live cases
run separately in Docker; no host skip is presented as an integration pass. The
six older unchanged live checks were not rerun for this checkpoint. Source-pinned
final runs and runtime/restart smoke are recorded below.
Development fixtures used the previous base commit identifier while working code
was uncommitted; they are diagnostic tests, not reproducible performance evidence.

### Source-pinned final verification

Implementation commit **06cd9d1**. All 29 feature delivery paths passed ownership
and exact local credential scans; raw data, secrets and generated artifacts remain
ignored. Code hashes (22 paths) are in artifacts/m05/source-snapshot.json. No
application dependency, canonical event schema, other owner's implementation or
shared workflow was changed.

| Command/check | Actual final result | Evidence |
|---|---|---|
| Host `python -m pytest tests/pipelines tests/contracts tests/integration -q --tb=short --junitxml=artifacts/m05/host-final.xml` | **298 passed, 45 skipped**, 36.11 seconds | artifacts/m05/host-final.xml |
| Existing 512-MiB checker, RUN_VERTICAL_LIVE_TESTS=1 and RUN_STORAGE_LIVE_TESTS=1; storage, adapter and all vertical test files | **51 passed, 1 skipped**, 25.02 seconds; skip is Windows-only and passed on host | artifacts/m05/linux-final.xml |
| Owned Ruff lint/format, generated schema/API checks and git diff check | Passed; final format check covered 44 files, generated outputs current | Session |
| `PROJECTCTL_ADAPTER_MODULE=infra.analytics`, existing `db migrate --namespace bench-m05` | Expected global dependency exit **4**; analytics versions **1 and 2 applied**, other owners/outbox still NOT_RUN | artifacts/projectctl/70dc9471-3c7a-4b62-9f21-673f84152e95/ and matching artifacts/infra/analytics/checks/ directory |
| Persistent `python -m tests.pipelines.vertical_checkpoint` | Real public analytics tables and lakehouse files, valid event reaches active generation 1 | artifacts/m05/checkpoint-slice.json |
| Actual Uvicorn/localhost:8006 API, then retained PostgreSQL restart and fresh-process `--resume` | **PASS**: same generation/count/files recovered, internal missing-token request 401 and authenticated receipts 200. Readiness intentionally 503 for absent real outbox | artifacts/m05/api-runtime.json |
| Actual analytics-worker entrypoint through native Kafka and HTTP Gold query | **PASS**: one unique event reaches active Gold; broker next offset 1. Deliberate malformed source at offset 1 causes expected worker exit 1, leaves committed offset 1 and preserves prior Gold | artifacts/m05/worker-runtime.json |
| Post-restart env verify with existing adapter | Exit **0**, real storage/schema mappings retained | artifacts/projectctl/6e1865d5-5fca-4f4d-a1c1-5b53681ac17c/ |
| Env down | Exit **0**, all volumes retained; temporary API/worker containers already stopped and removed | artifacts/projectctl/47fd37b3-381e-45c9-853e-f7ed527fa8f0/ |

Final valid/source/offset facts are artifacts/m05/{valid-slice,kafka-offsets}.json.
Earlier development copies and previous M04 facts are archived under development/
and prior-m04-facts/. The ignored host worker-smoke helper initially needed its
repository import path added; no application behavior or assertion was weakened.
Source-pinned checkpoint namespace is bench-m05-check-1554c98df84f4965afa003e9912b3534;
actual entrypoint namespace is bench-m05-worker-32b64150efbc44ae93178f19995224d3.
These are explicitly synthetic fixtures. API/worker each use 384 MiB and 0.5 CPU;
the existing stack was not given more RAM. Ephemeral service tokens stayed in
process memory and removed container environments, never in Git/evidence output.

All 39 platform/M04/M05 host skips passed separately in Linux. The six older live
cases were not rerun. Full G0/G1, actual production-outbox notifications, other
domain reducers, replay/compactor admission and performance are **NOT_RUN**. Runtime
worker fail-closed behavior is a verified dependency boundary, not a successful
invalid-source processing claim.

### Shared workflow follow-up

Feature commit 06cd9d1 and verification notes 58b7b67 were pushed to vichitr.
[GitHub Actions run 41282911833](https://github.com/harsh-c-16/payment-gateway/actions/runs/41282911833)
passed Ubuntu offline and conversation-postgres, but Windows failed at
`uv run --locked python benchmarks/manual/verify_p5.py`. The cause is **unknown**;
the public job annotation reports only exit 1. The failure is retained in
artifacts/m05/github-actions.json and is not treated as a passing checkpoint.

A subsequent local Windows `.venv/Scripts/python.exe benchmarks/manual/verify_p5.py`
passed all eleven checks, including **626 tests in 117.54 seconds**. Exact commands,
stdout, stderr and expected exits are in
artifacts/p5/c147c87c-cf02-4c30-8f62-abc97b3da446/checks.json. No P6 local rerun is
claimed. This successful local run does not explain or supersede the CI failure.
Anonymous GitHub log access returned HTTP 403; automatic approval review rejected
access to the saved GitHub credential without explicit authorization. No credential
was accessed. Log inspection remains pending that authorization or a user-provided
failure log; no assertion, shared harness or workflow was changed.

Docker Desktop is stopped (zero Desktop/backend processes after shutdown), with
all project volumes retained. The six older live skip reasons and the twelve new
M05 case names are recorded in [test_skips.md](test_skips.md).

## M04 follow-up — User-approved 2-MiB cap and exact skips, 31 October 2026

The user explicitly approved increasing Bronze to 2 MiB. This supersedes the
original 1-MiB capture checkpoint and its ordinary-record format blocker below.
The canonical common spec §§11.1/Appendix A, implementation, tests, package README,
plan and handoff now agree on **2,097,152 total encoded JSONL bytes**. This includes
base64, escaped headers and metadata, for all baseline/optimized/scaling variants.
The 50-ms timer, 1-MiB raw transport ceiling, 64-KiB valid-event ceiling and batch
resource bounds are unchanged. Existing smaller Bronze files remain readable.

The same user-authorized bound also requires two coordinated shared-path changes:
configs/evaluation.yaml's inherited benchmark default and projectctl/config.py's
frozen B0 validator now pin 2,097,152. Otherwise the harness would retain/reject the
wrong bound. No other harness behavior changed. Owned test_capture_config.py checks
every variant agrees with storage and rejects a stale 1-MiB B0/O1 setting. Existing
saved run/config hashes are not rewritten; no benchmark comparison is claimed.

New tests round-trip a full 1-MiB source after base64 expansion, accept an exact
2-MiB wrapper and reject a one-byte overflow including escaped-header metadata.
The size-flush fixture now crosses the new boundary; oversized capture failure
still leaves offsets untouched. No fragmentation or independent metadata budget
was introduced. The hard total encoded cap continues to guard header-heavy input.

Actual commands/outcomes:

- Host `.venv/Scripts/python.exe -m pytest tests/pipelines tests/contracts
  tests/integration -q --tb=short --junitxml=artifacts/m04-2mib/host.xml`:
  **286 passed, 33 skipped**, **59.97 seconds**.
- Existing 512-MiB Linux checker, RUN_STORAGE_LIVE_TESTS=1, `python -m pytest
  tests/pipelines/test_storage.py tests/pipelines/test_storage_live.py
  tests/pipelines/test_analytics_adapter.py -q --tb=short
  --junitxml=artifacts/m04/2mib-linux.xml`: **30 passed, 1 skipped**,
  **8.21 seconds**. A copy is artifacts/m04-2mib/linux.xml. Real filesystem and
  Kafka/PostgreSQL tests pass; the Linux skip is Windows-only and passed on host.
- All **33 host skips** are listed individually with reasons in
  [test_skips.md](test_skips.md). **27 passed separately in Linux**; six older
  infrastructure/transport live cases were not rerun for this narrow size change.
  Earlier real evidence is linked explicitly; no current rerun is claimed for them.
- Streaming env up exited **0** using existing low-memory limits:
  artifacts/projectctl/f7a1e038-445a-4ca0-bc3d-592c45d2199a/. No Docker RAM increase.
  Prior M04 raw SQL/Kafka facts were archived in artifacts/m04-2mib/prior-evidence/
  before the follow-up; current facts and machine-readable skips are retained in
  artifacts/m04-2mib/.
- Config regression command: `python -m pytest tests/pipelines/test_capture_config.py
  tests/projectctl/test_config.py -q --tb=short
  --junitxml=artifacts/m04-2mib/config.xml`: **34 passed**, **zero skipped**,
  **3.01 seconds**. Ruff lint/format and generated config/API schema checks passed.
- Final host suites after the shared default/validator updates: **289 passed,
  33 skipped**, **36.25 seconds**, artifacts/m04-2mib/host-final.xml. The skip list
  is unchanged: 27 pass separately in Linux, six older live cases not rerun here.
- Environment down exited **0**, volumes retained:
  artifacts/projectctl/d384db5a-6e0c-49c5-886e-c40462f7b34f/. Docker Desktop stopped
  after confirming no other running containers; no increase in allocated RAM.

The user authorizes this exact common-spec change; no teammate agreement is
invented. Consumers/experiment owners must use the revised common bound before
comparing variants. Full Silver/Gold, real shared-outbox integration and performance
remain NOT_RUN. This follow-up does not start M05.

## M04 — Durable FileStore, Bronze and capture ledger, 31 October 2026

Implemented within Vichitr-owned paths. This is capture and receipt **foundation**,
not a completed source disposition/Silver/Gold path. See [M04 handoff](m04_capture_handoff.md).

### Changed paths and behavior

- pipelines/storage/__init__.py and README: three-argument immutable FileStore,
  input/read-back hashes, file/directory fsync, same-directory rename, cooperating
  process lock, traversal/symlink rejection, idempotent retry and read-only orphan
  inventory. Native Windows fails explicitly; real durable execution uses the
  private Linux named volume. No deletion/cleanup implementation was introduced.
- pipelines/ingestion/{__init__,bronze,receipts}.py and README: exact base64 byte
  wrappers, duplicate header order/nulls, source coordinates/times/fingerprint,
  file/row locators, fixed 1-MiB/50-ms capture bounds and bounded input sequences.
  Receipt recovery verifies hashes/membership. Caller-owned SQL persistence keeps
  first source locators, detects changed coordinates/content and rolls back caught
  conflicts with savepoints. Same bytes at a new offset are a distinct source.
- shared/contracts/analytics.py adds internal CapturedSource/RawBatchReceipt DTOs;
  existing public API/receipt fields are unchanged. Capture-only records have no
  final disposition or Silver/Gold times and never authorize worker durability.
- migrations/analytics/001_capture.sql creates captures, source receipts, quarantine
  and processing-run foundations. Migration retry uses an advisory transaction lock
  and normalized-LF checksum; altered applied SQL fails. Aditya still owns outbox DDL.
- infra/analytics.py composes the existing env providers with this owner's migration
  provider. It applies analytics only and explicitly returns dependency exit 4 for
  incomplete global migration dispatch. It never writes another service database.
- infra/{storage.Dockerfile,compose.storage.yaml}: digest-pinned Python 3.11.15,
  existing locked dependencies, opt-in 512-MiB/0.5-CPU Linux verification worker,
  source mounts, one analytics secret and the retained lakehouse volume. Existing
  stack plus worker is 2,688 MiB; Docker RAM was not increased.
- tests/pipelines/{test_storage,test_storage_live,test_analytics_adapter,storage_restart}.py:
  real filesystem/SQL/Kafka checks and explicitly injected syscall/process faults.
  Owned test conftest uses importlib; removing its empty package marker prevents
  test pipelines from shadowing the production namespace. No shared pytest config,
  dependency lock, other owner's code or assertions changed.

### Actual verification and evidence

- Host `.venv/Scripts/python.exe -m pytest tests/pipelines tests/contracts
  tests/integration -q --tb=short --junitxml=artifacts/m04/offline-verified.xml`:
  **286 passed, 31 skipped**, **47.25 seconds**. Windows deliberately skips real
  POSIX fsync tests; explicit opt-in live tests are skipped in this invocation.
  The same new filesystem paths run in the Linux suite below, not as fake passes.
- Linux named-volume `python -m pytest tests/pipelines/test_storage.py
  tests/pipelines/test_storage_live.py -q --tb=short
  --junitxml=artifacts/m04/storage-live-verified.xml`: **26 passed, 1 skipped**,
  **13.77 seconds**. Skip is the Windows-only unsupported-host check. Real broker
  committed offset remained -1001 after capture+SQL; a commit attempt was rejected.
- Real PostgreSQL 18.2 SQL capture rollback, first-locator retry, new-offset source,
  caught corruption rollback and NULL downstream timings passed. Test schemas are
  isolated and dropped afterward; real shared outbox is NOT_RUN, not a test double
  claimed as integration. Evidence: artifacts/m04/{sql-capture,kafka-capture}.json.
- The syscall cases include pre-rename disk/file-fsync failure and directory-fsync
  failure after rename. A child acknowledged M04_AFTER_RENAME_BARRIER_ACK before
  os._exit(73); its orphan was recovered by verified immutable retry. These are
  process/syscall fault checks, not hardware power-loss measurements.
- Existing streaming env up initially returned ConnectionTimeout during cold
  startup (artifacts/projectctl/787f99ad-fdbb-47d0-b4d8-29b5335c5acd). Retained stack
  became healthy; retry exited 0 and verified mappings:
  artifacts/projectctl/85562d40-f84b-4e5c-ae5f-e8273b1ff83b/.
- CLI migration applied analytics but an initial adapter incorrectly pre-created
  the CLI-owned evidence directory; its raw provider result is preserved under
  artifacts/projectctl/57c35968-d9c4-4517-92a2-575c5c6adfea/. Fixed at the adapter's
  evidence path and added a regression test. Verified command with
  PROJECTCTL_ADAPTER_MODULE=infra.analytics, `python -m projectctl db migrate
  --namespace bench-m04`: expected exit **4**, analytics portion applied and global
  dependencies explicit. Evidence: artifacts/projectctl/f4c400ce-7b5f-4ae6-90eb-fea746a1f3f2/
  and artifacts/infra/analytics/checks/f4c400ce-7b5f-4ae6-90eb-fea746a1f3f2/.
- `python -m tests.pipelines.storage_restart` then a verified real PostgreSQL
  container restart and a fresh worker `--resume`: **PASS**; container/image/named
  volume identity retained, database receipt and exact invalid bytes recovered,
  repeat capture remained idempotent and disposition stayed NULL. Evidence:
  artifacts/m04/{restart,restart-container}.json. Public test namespace is
  bench-m04-restart-8d2d7bd3cb264505998693f42249d196; no operational data was reset.
- Initial collection failures, corrected import/source-mount setup and earlier XMLs
  are retained. No failed case/assertion was removed to obtain a pass. Final
  cross-platform migration/checker and delivery evidence follows below.
- Final Linux suite adds the adapter regression and verifies LF/CRLF migration
  retry plus rejection of an idle caller connection: **28 passed, 1 skipped**,
  **6.52 seconds**, artifacts/m04/storage-final.xml. Earlier full run (28/1,
  6.60 seconds) and the missing-source-mount collection failure are retained.
- Owned Ruff lint/format and git diff checks passed after formatting a README code
  block. Existing schemas/API fixtures are unchanged. Real infrastructure/schema
  mappings verified after restart: exit **0**,
  artifacts/projectctl/e05e8f66-05cc-4d68-896b-53596cdc17e9/.
- Environment down exited **0**, volumes retained:
  artifacts/projectctl/6f2e2bdf-0af7-4a4f-bab5-a6737b20847f/. Docker Desktop stopped
  after confirming no other containers were running. Ownership and exact retained
  credential scans passed for all **23** delivery paths; no raw CSV, credentials or
  generated evidence is staged. Audit: artifacts/m04/source-audit.json.
- Full shared Ubuntu/Windows/PostgreSQL workflow verification is performed by the
  branch's GitHub Actions run after delivery; raw status is retained locally in
  artifacts/m04/github-actions.json. Local P5/P6 scripts were not redundantly rerun
  for this module; the focused host and actual Linux capture suites are above.

### Remaining handoffs

M05 must atomically finalize dispositions with Silver/reducers or quarantine and
Aditya's real outbox, then mark durable prefixes. Public receipt/manifest/Gold API,
active publication, replay and performance remain NOT_RUN. Harsh can adopt FileStore
inside the Linux volume; his CSV parsing and source manifests remain his work.

A near-1-MiB raw invalid source can exceed the physical file cap after base64.
CaptureTooLarge backpressures it without committing offsets; fragmentation/locator
contract review is required. Native Windows directory fsync and host power-loss/
volume-loss durability are not claimed. Orphan inventory never deletes data.

## M03 — Shared transport and local diagnostics, 31 October 2026

Implemented on `vichitr` within Vichitr-owned paths. Provider adoption and Aditya's
actual outbox remain external dependencies; full G0/integrated checkout is not
claimed. See [M03 handoff](m03_transport_handoff.md) and the two shared READMEs.

### Implemented paths and behavior

- `shared/event_transport/{__init__,codec,publisher,consumer}.py`: public builder,
  validator, acknowledged publisher, manual consumer/offset functions and pure DLQ
  construction. Existing M1 keyword build/append binding is tested unchanged.
- Producer settings are fixed: idempotence, acks=all, max in-flight=5, Zstandard,
  linger=5 ms, 10,000 records/64 MiB queues, 10-second delivery timeout and 5-second
  request timeout. Queue admission is never returned as success. Ack uncertainty
  preserves event identity/content and remains retryable; no silent drop.
- Consumers preserve exact source bytes/nulls/ordered duplicate headers, namespace,
  coordinates, Kafka/ingress timestamps and a length-delimited raw-byte fingerprint.
  Automatic commit/store is disabled. Explicit durable markers gate contiguous
  delivered prefixes; partial commits release only acknowledged partitions. Revoke
  commits only durable prefixes; lost/old ownership cannot commit new assignments.
- Worker declarations split 2,000 records/16 MiB across one/three workers, including
  remainders. Static indexes, worker-thread ownership, native queue/fetch headroom,
  pause/resume and heartbeat polling are explicit. Oversized sources rewind/fail
  visibly without offsets advancing; no source/Gold success is fabricated.
- `shared/local_diagnostics/{__init__.py,schema.sql}`: caller-owned Connection
  helper/table template. Missing outbox fails before writing; savepoints also roll
  back a caught non-SQL append failure. Same-ID same-content retry is idempotent;
  altered identity conflicts. No service migration or alternate outbox was supplied.
- `shared/contracts/events.py`: typed source/validation/commit results; optional
  envelope/metadata values survive serialization. Diagnostic/DLQ services include
  analytics separately from business producers. All six domain/DLQ schema hashes
  are regenerated and backward-compatible against the actual retained registry.
- `shared/event_transport/schemas.py`, `contracts/events/supported-history.json`:
  verify/cache six current and six released-M02 schema definitions/IDs. Older
  supported records validate offline; unknown/unpublished IDs remain unsupported.
- `tests/pipelines/{transport_doubles,test_transport,test_transport_live}.py` and
  the owned registry live test: explicit doubles, real delivery/offset/rebalance,
  real SQL transaction behavior and actual schema-evolution evidence.

### Actual focused and live verification

Commands use `.venv/Scripts/python.exe` at repository root. Tests run with the
existing workspace-local scratch setup outside Windows sandbox ACL restrictions.

| Command/check | Actual outcome | Evidence |
|---|---|---|
| Initial `-m pytest tests/pipelines -q --tb=short` | **121 passed, 3 skipped**; initial lint formatting issues corrected without changing assertions | `artifacts/m03/offline-first.xml` |
| `-m pytest tests/pipelines tests/contracts -q --tb=short --junitxml=artifacts/m03/offline-verified.xml` | **236 passed, 6 skipped**, 26.93 seconds; opt-in infrastructure/live tests skipped in this offline invocation | `artifacts/m03/offline-verified.xml` |
| Final same focused suites after escaped-invalid-Unicode hashing guard | **237 passed, 6 skipped**, 23.56 seconds; unsupported escaped Unicode returns INVALID_JSON rather than crashing canonical hashing | `artifacts/m03/offline-final-verified.xml` |
| Workflow integration lint/format and `-m pytest tests/integration -q --tb=short --junitxml=artifacts/m03/integration.xml` | **45 passed**, 10.02 seconds | `artifacts/m03/integration.xml` |
| Owned Ruff lint/format and `git diff --check` | Passed | Session |
| `PROJECTCTL_ADAPTER_MODULE=infra.streaming` and `-m projectctl env up --profile streaming-local` | Exit 0. Retained resource profile/volumes; all current and released history schemas read-verified | `artifacts/projectctl/22cf29ed-149a-4268-b60c-00b2548e57d7/` |
| `RUN_TRANSPORT_LIVE_TESTS=1`, `-m pytest tests/pipelines/test_transport_live.py -q` | **3 passed**, 6.82 seconds: real broker/offset/rebalance and SQL savepoints with an explicit outbox double | `artifacts/m03/live-first.xml` |
| Final history-aware live run with `RUN_TRANSPORT_LIVE_TESTS=1`, `RUN_CONTRACTS_LIVE_TESTS=1`; `-m pytest tests/pipelines/test_transport_live.py tests/pipelines/test_event_contracts_live.py -q --tb=short --junitxml=artifacts/m03/live-history-verified.xml` | **4 passed**, 12.76 seconds; known old ID validated, all six subjects accept safe evolution/reject breaking or unsafe typed optional additions | `artifacts/m03/live-history-verified.xml`, `kafka-sdk.json`, `rebalance.json`, `diagnostics-sql.json` |
| `-m projectctl env verify --profile streaming-local` with explicit adapter | Exit 0; real infrastructure and all 12 current/released mappings verified | `artifacts/projectctl/cb6e272c-c322-4fee-a29d-f9bcd30ff77f/` |
| `-m projectctl env down` with explicit adapter | Exit 0, all volumes retained; Docker Desktop stopped after no other containers were running | `artifacts/projectctl/17e388e9-ebed-4576-9b83-690d5a2872d2/` |

Earlier intermediate offline/live XMLs are preserved, including the initial
four-live-test pass in `live-final.xml`. No failed test was removed or weakened.
The final SDK namespace is `bench-m03-3d51729df9914425aa74932f26ac0e07`; rebalance
namespace is `bench-m03-r-fbf8ed33f78b41bdaf99f4e8e77c78cb`. Released conversation
schema ID 9 is verified/cached alongside six latest schemas. Latest local IDs are
17/18/19/20/21/22 for conversation/inventory/order/payment/retrieval/DLQ respectively;
IDs are local evidence, not portable constants.

The SQL test uses a real analytics connection and a randomly named isolated schema
with an explicit transactional outbox double; it does not write operational service
databases. Caller rollback, caught append-failure rollback, one-row retry and
altered-ID rejection all pass. The isolated SQL schema is removed after evidence;
Kafka fixture topics and all project data volumes are retained. Native consumer
durability markers in the transport smoke are fixture assertions, not actual
M04/M05 source-to-Gold processing.

### Remaining adoption and checkpoint

Aditya must provide the real shared outbox. Each service owner applies the diagnostic
template and wires startup/readiness/cache/revision/transaction bindings described
in the handoff. Signature choices for group handles, explicit durable markers and
source_record=null for coordinate-free validation are documented for consumer
review. No business implementation, dependency lock, shared caller, CSV importer,
Bronze/Silver/Gold or performance result was changed/claimed. Next is M04 durable
FileStore/Bronze/actual source receipts. CI-equivalent checks are recorded below.

### CI-script verification

- Source checkpoint: `55b397b`. No application dependency/lock or other owner's
  implementation changed. A local source hash snapshot is retained in
  `artifacts/m03/source-snapshot.json`.
- `.venv/Scripts/python.exe benchmarks/manual/verify_p5.py`: exit **0**, all
  **11/11** expected outcomes matched. Its pytest suite passed **626 tests** in
  **121.58 seconds**; lint, format, generated schema/contract checks, observation
  rebuild and committed-source guards passed. Evidence:
  `artifacts/p5/3899e813-1c35-47d9-a855-dab8a4b5f878/`.
- The contracts inventory retains its expected dependency exit **4**: absent
  Harsh/Aditya providers and full G0 are visible, not replaced by SDK test doubles.
  Observer fixture results are not a real system/performance measurement.
- `.venv/Scripts/python.exe benchmarks/manual/verify_p6.py --out artifacts/m03/p6`:
  exit **0**, all **10/10** inner checks matched; **949 tests passed** in
  **246.50 seconds** with 121 existing JUnit `record_property` warnings. Real
  PostgreSQL 18.6 ran in an isolated 512-MiB Docker container. Restart retained
  container/image/volume identity and the resumed SQL smoke passed. Evidence:
  `artifacts/m03/p6/{docker-summary,docker-checks}.json`,
  `artifacts/m03/p6/checkpoint/{checks.json,pytest.xml,smoke/}`. Its event/outbox
  dependencies remain explicit test doubles, not real shared-outbox integration.
- All local workflow-equivalent checks passed sequentially, including the 45
  integration checks above; no timing assertion, test or expected dependency exit
  was weakened. Raw evidence remains ignored. The isolated P6 container is stopped
  with its volume retained; Docker Desktop is stopped after confirming no other
  running containers.

## M02 correction — Accepted receipt and CI regression, 31 October 2026

The user confirmed Jaineel's agreement with the detailed receipt format and
explicitly authorized updating the shared fixture/tests. This supersedes the
receipt-review blocker in the historical M02 entry below; other producer/G0
reviews remain pending.

- Updated `tests/contracts/provisional.py` and its generated
  `contracts/fixtures/p2/pairs.json` with namespace, source coordinates, raw hash,
  durable-stage timestamps and `timing_validity=missing`. Silver/Gold timing and
  visibility remain null in this synthetic missing-timing fixture.
- Updated `tests/contracts/test_contracts.py` to require analytics presence and
  receipt compatibility, while preserving missing Harsh/Aditya handoffs and
  NOT_RUN metrics. Added actual OpenAPI/DTO coverage that rejects the old shape.
- Recorded the user-reported agreement in the analytics module/OpenAPI generator,
  regenerated OpenAPI, and updated the owned plan/review handoff.
- `python -m pytest tests/contracts tests/pipelines -q --tb=short
  --junitxml=artifacts/m02-ci-fix/focused.xml`: **210 passed, 3 skipped**. All skipped
  tests explicitly require unrelated opt-in live Kafka/PostgreSQL checks.
- `python -m projectctl contracts check --all`: expected dependency exit **4**;
  `receipts-missing-timing` passes and no correctness FAIL remains. Full G0 is
  still incomplete. Evidence: `artifacts/projectctl/3e3991e5-fc28-4c24-8dcb-3e517bf2d99a/`.

### CI-script verification

- Locked dependency sync passed without changing the lock. Shared fixture JSON
  matches its generator; owned/shared lint and format checks passed.
- The remaining workflow steps for integration lint/format and
  `python -m pytest tests/integration -q --tb=short
  --junitxml=artifacts/m02-ci-fix/integration.xml` passed: **45 tests**.
- First `python benchmarks/manual/verify_p5.py` attempt, run concurrently with
  P6: 10/11 checks matched. The pytest step had **625 passed, 1 failed** in
  174.57 seconds. The failure was the existing 61-ms real-process telemetry
  sampler expecting four CPU samples but observing two; the receipt regression
  passed. Raw evidence is preserved at
  `artifacts/p5/8f3459f3-58d9-4eb1-9f9d-a6aa0d50eb6d/`.
- The unchanged telemetry test passed in isolation: **1 passed**, 1.14 seconds,
  `artifacts/m02-ci-fix/telemetry-isolated.xml`. No telemetry code, timing budget,
  expected sample count or assertion was relaxed.
- Serial `python benchmarks/manual/verify_p5.py` rerun passed, exit **0**:
  **11/11 checks matched**, including **626 tests passed** in 118.858 seconds,
  schema regeneration checks, the expected dependency-only contract inventory,
  observer/report reconstruction and clean source guards. Evidence:
  `artifacts/p5/1e27973f-b8f4-434b-8a8b-cf89bcd4ca8e/{checks.json,pytest.xml}`.
- `python benchmarks/manual/verify_p6.py --out artifacts/m02-ci-fix/p6` passed,
  exit **0**, using a real isolated Docker PostgreSQL **18.6** container capped
  at 512 MiB. All 10 inner verification commands matched, including **949 tests
  passed** in 245.855 seconds. The smoke and post-restart resume passed; the
  container ID/data volume were retained and the server start time changed.
  Evidence: `artifacts/m02-ci-fix/p6/{docker-summary.json,docker-checks.json}`
  and `checkpoint/{checks.json,pytest.xml,smoke/}`. Its event/outbox collaborators
  remain explicitly test doubles; no real shared checkout gate is claimed.
- Stopped only the verified isolated P6 test container, retained its volume,
  and stopped Docker Desktop after confirming no other containers were running.

No database format, event schema ID, application lock or deployment was changed.
All workflow-equivalent local checks now pass. The initial failed run is retained
alongside the successful serial run; full shared-service/G0 completion remains
incomplete and was not relabelled as a pass.

## M02 — Contracts implemented; team review pending, 31 October 2026

Branch: `vichitr`. Owned offline and real registry/wire checks pass. This is a
reviewable contract proposal, **not G0 sign-off**. The full shared suite exposes
one historical inventory/receipt-fixture failure requiring Jaineel's review.

### Changes and scope

- `shared/contracts/events.py`: 24 business payload snapshots, envelope/metadata,
  local diagnostic/DLQ shape, reason enum, publish acknowledgement, ownership,
  key/aggregate/version/state/provenance checks and strict known fields.
- `contracts/events/`: six self-contained draft-07 schemas, hash manifest and
  usage guide; `contracts/dictionaries/events/reasons.v1.json`: the 18 reasons.
- `shared/contracts/analytics.py`, `contracts/http/analytics.yaml`: canonical
  manifest/candidate/source range/reconciliation/batch DTOs and proposed receipt,
  quarantine and replay bindings for the six exact analytics endpoints. Internal
  authentication matches the existing `Authorization: Bearer` client proposal.
- `shared/event_transport/schemas.py`: actual registration/read-back, complete
  pinned cache, online policy/mapping checks and pure wire validation. Broker
  wrappers and the service-local transactional helper remain M03.
- `infra/contract_assets.py`: reproducible owned asset generation from models;
  `infra/streaming.py` and `infra/STREAMING.md`: schema-aware existing CLI startup
  and verification, preserving the same low-memory infrastructure profile.
- `tests/pipelines/{event_examples.py,fixtures/events.v1.json,test_event_contracts.py,test_event_contracts_live.py}`:
  synthetic valid/invalid contracts, consumer OpenAPI binding and real wire tests.
- [M02 decision/review handoff](m02_contract_handoff.md): concrete field choices,
  existing receipt mismatch, affected owners, migration/review and verification.

No shared canonical spec, dependency lock, consumer implementation/test, raw CSV,
service migration, business database, operational producer or Gold pipeline was
changed. Optional unknown properties/nulls remain in the immutable parsed wire
document; content hashes cover that document, including event/production times.

### Actual verification

All Python commands below use `.venv/Scripts/python.exe` from the repository root;
pytest runs outside the Windows filesystem sandbox using workspace-local scratch
directories, matching the existing infrastructure test arrangement.

| Command/check | Actual outcome | Evidence |
|---|---|---|
| `-m infra.contract_assets`; owned Ruff check/format | Generated assets reproducible; lint/format passed | Source tests/session |
| Initial contract test collection | Failed relative import; added owned test package initializer | `artifacts/m02/contracts-first.xml` |
| Second focused run | 58 passed; timestamp reason mismatch and two Windows environment-size errors caused by an oversized pytest case ID; fixed classification and bounded IDs | `artifacts/m02/contracts-second.xml` |
| First complete owned run | 99 passed, 2 live tests skipped | `artifacts/m02/offline-first.xml` |
| `-m pytest tests/pipelines -q --tb=short --junitxml=artifacts/m02/offline-final.xml` | **107 passed, 3 skipped**; all three live tests are opt-in | `artifacts/m02/offline-final.xml` |
| `-m pytest tests/pipelines tests/contracts tests/projectctl -q --tb=short --junitxml=artifacts/m02/regression-first.xml` | **336 passed, 3 skipped, 1 failed**; shared historical inventory assertion expects analytics absent/exit 4; new proposal exposes the known receipt conflict/exit 3 | `artifacts/m02/regression-first.xml` |
| Same broad suites, final rerun after the added malformed-input tests | **344 passed, 3 skipped, 1 failed**, 83.62 seconds; same documented shared inventory/receipt failure | `artifacts/m02/regression-final.xml` |
| `PROJECTCTL_ADAPTER_MODULE=infra.streaming` then `-m projectctl env up --profile streaming-local` | Exit 0; registered six actual JSON subjects, verified policy/ID/hash and infrastructure. Repeated after allowing legitimate multiword facets; registration remained backward compatible | `artifacts/projectctl/a12159ec-6e94-4a86-8648-5d0427b1f6a9/`, `artifacts/projectctl/d21a1997-8238-4ead-9140-861a732075cd/` |
| `RUN_CONTRACTS_LIVE_TESTS=1` then `-m pytest tests/pipelines/test_event_contracts_live.py -q --tb=short --junitxml=artifacts/m02/live-first.xml` | **1 passed**, real Kafka and registry, 25 acknowledged/read records | `artifacts/m02/live-first.xml` |
| Same live test, final expanded compatibility checks | **1 passed**, 8.09 seconds; all six subjects accept an unconstrained optional addition and reject both a breaking type and an unsafe typed optional addition to the open model. Old/new example validation and 25 exact-byte wire records pass | `artifacts/m02/live-final.xml`, `artifacts/m02/live-contracts.json` |
| `-m projectctl env verify --profile streaming-local` with explicit adapter | Exit 0; actual final infrastructure/schema mapping checks pass | `artifacts/projectctl/3966f6c7-6e78-4a65-b612-c990f0cfea9f/` |
| Stop live-check infrastructure | Mistakenly supplied startup-only `--profile` to `env down`, which returned 2. Corrected by stopping all three verified project containers directly, then `docker desktop stop`, exit 0. No volumes removed; final Desktop/backend process count 0 | `artifacts/projectctl/a6b8ac64-a5d5-485a-be60-36f32702f2da/`, session |
| Owned lint/format, whitespace and secret/file-scope audit | Passed. Secret audit required the existing elevated file access; no protected password values printed or included in changed files | Session |

The final live namespace is `bench-m02-41c04949c3914f6d943322b431b62dd0`.
The registry returned conversation subject ID 9/version 2, retrieval ID 10/version
2, inventory ID 4/version 1, order ID 5/version 1, payment ID 6/version 1 and DLQ
ID 8/version 1. These IDs are local facts, not portable constants. Complete
ID/hash definitions are retained in the ignored runtime mapping and live evidence.
Early local versions were test proposals; no operational traffic used them.

The broad suite's failure is preserved. `receipts-missing-timing` uses the earlier
provisional `silver_at` item, while the proposed DTO names/contains explicit source
and durable-stage fields. The shared inventory test also asserts the analytics
contract is missing. Jaineel owns those fixtures/tests. No assertion was weakened,
test skipped or consumer field silently rewritten to obtain a green shared gate.
See the handoff for exact old/new shapes and required provider/consumer review.

### Checkpoint and next handoff

M02's implementation and owned/live verification are ready for review. Producer
owners must approve their payloads; Jaineel must review receipt/pagination/source
range bindings and update his historical inventory fixture/test as agreed. G0,
real outbox integration, source-to-Gold correctness and benchmarks remain incomplete.
M03 is next: keyword-compatible builder/validation exports, acknowledged bounded
Kafka transport, offset handling and service-local diagnostics. Aditya's actual
outbox remains a dependency; an explicit test double cannot close real integration.

## M01b — Low-memory infrastructure passed, 31 October 2026

Branch: `vichitr`. PostgreSQL, Kafka **4.1.2** (single KRaft broker/controller) and
Confluent Schema Registry **8.1.0** are running. The `streaming-local` profile
caps PostgreSQL at 512 MiB/0.5 CPU, Kafka at 1,024 MiB/0.75 CPU and registry at
640 MiB/0.5 CPU: **2,176 MiB total**, within the observed Docker memory allowance.
The same PostgreSQL volume/credentials were reused. No Docker VM memory setting
was increased. **M01b passed; canonical domain contracts/full G0 and benchmarks
remain NOT_RUN.**

The supplied `data/raw/flipkart_com-ecommerce_sample.csv` is exactly 38,114,963
bytes and SHA-256 `56f8f699c9e847356666c2eab3c3ab1244340f6a98ad08e39ea2199ebe993ad1`.
It is Git-ignored and unchanged. No CSV normalization/import was implemented;
that remains Harsh's ownership.

### Changes

- `infra/compose.streaming.yaml`, `infra/streaming-profile.json`: low-memory
  overlay, pinned images, bounded JVM heaps, retained Kafka volume, local ports,
  internal DNS, real registry and shared lakehouse volume declaration.
- `infra/streaming.py`: existing CLI's `env up/verify/down` providers, explicit
  dev/bench/replay topic provisioning, partition/retention/ISR verification,
  registry compatibility and image/health/resource/volume checks. Existing topics
  are never repartitioned or silently reconfigured. Worker groups are declared;
  real groups form on consumer join/commit, as demonstrated by the smoke test.
- `infra/postgres.py`: reused credential preparation, explicit verification of
  either profile's PostgreSQL limits and bounded startup timeout support. No SQL
  migrations or credentials changed.
- `tests/pipelines/test_streaming*.py`: offline namespace/resource/idempotency
  checks and explicit real schema/JSON/broker/group/recreation smoke. PostgreSQL
  tests cover credential reuse and the smaller profile without weakening defaults.
- `infra/images.lock.json`: checksum-resolved images, actual version log lines,
  and smoke-tested states/evidence. `infra/STREAMING.md`, README and plan updated.

The canonical event/analytics contracts are still M02. The smoke subject is the
separate `infra-smoke.v1-value`, with registered ID/schema hash mappings in its
evidence. It is not a partially implemented business topic contract or an SDK.
FileStore, Bronze/Silver/Gold and operational business services remain later work.

### Commands and actual outcomes

Python module commands use `.venv/Scripts/python.exe -m`. Docker/live tests require
engine access outside the sandbox. No dependencies or the application lock changed.

| Command / check | Actual result | Evidence |
|---|---|---|
| CSV SHA-256/size and `git check-ignore` | Matches the supplied-file specification; ignored; no import | `artifacts/m01b/source-check.json` |
| Official Docker registry manifest GETs, computed SHA-256 versus response digest | Both match; immutable Kafka 4.1.2 and Registry 8.1.0 references recorded | `artifacts/m01b/kafka-resolution.json`, `schema-registry-resolution.json`, corresponding raw manifests |
| `docker pull --quiet <each pinned reference>` | Both images downloaded successfully | Session transcript; locks and runtime image checks |
| Initial `projectctl env up --profile streaming-local` | Exit 4: cold startup exceeded the original 180-second command budget | `artifacts/projectctl/0cd0b22a-9298-41a3-9d96-eb1d395b3bd4/` |
| Kafka startup diagnosis and configuration fix | Kafka started; extra JVM health probes were costly. Replaced them with a TCP probe; actual Kafka metadata/config checks remain mandatory in the CLI. Streaming `up` now has a bounded 600-second command budget | Source config and session transcript |
| Retried `projectctl env up --profile streaming-local` with `PROJECTCTL_ADAPTER_MODULE=infra.streaming` | Exit 0; three services, six dev topics and shared volume verified | `artifacts/projectctl/11f1f6e9-e5e9-45eb-8953-168ac63e68c8/` and matching infrastructure checks |
| `pytest tests/pipelines -q --junitxml=artifacts/m01b/offline.xml` | 32 passed, 2 explicit live skips | `artifacts/m01b/offline.xml` |
| Expanded final offline suite, same command with `--junitxml=artifacts/m01b/offline-final.xml` | **39 passed, 2 explicit live skips**, exit 0, 3.26 seconds | `artifacts/m01b/offline-final.xml` |
| First explicit live streaming test with `RUN_STREAMING_LIVE_TESTS=1` | Fixture failed because a temporary AdminClient was destroyed before its asynchronous request completed. Retained the client until the request finished; no assertions removed | `artifacts/m01b/live.xml` |
| `pytest tests/pipelines/test_streaming_live.py -q --junitxml=artifacts/m01b/live-verified.xml` | **1 real test passed**, zero skips, 98.48 seconds | `artifacts/m01b/live-verified.xml` |
| Real smoke/recovery evidence | Registered compatible JSON schemas; incompatible candidate check false; broker-acknowledged plain JSON/headers; both independent groups received the record; message/group offset and schema retained after both containers were recreated | `artifacts/infra/streaming-local/checks/03fe5730-05d9-41a1-b0ff-cca4c185ddd7/live-test.json` |
| Actual Kafka/Registry startup version log lines | 4.1.2 / 8.1.0, matching locked images | `artifacts/m01b/version-evidence.json` |
| Final repeated CLI `env up` | Exit 0; existing topics/data/settings reused | `artifacts/projectctl/850c2606-9d57-4595-a928-7ba8332fa681/` |
| Final CLI `env verify` | Exit 0; all declared infrastructure verified | `artifacts/projectctl/d3e048a9-6aad-4099-9b26-607f69d664b4/` and matching infrastructure checks |
| One final `docker stats --no-stream` sample | PostgreSQL 40.57 MiB, Kafka 351.4 MiB, Registry 203 MiB; a single sample, not a peak or performance result | `artifacts/m01b/final-memory-sample.txt` |

Six `dev` topics use one partition, one replica and seven-day retention; the DLQ
notification topic remains separate from the five business topics. Kafka retains
registry metadata in `_schemas`; the named shared lakehouse volume is provisioned
for the later FileStore. No development data, volumes or benchmark evidence were
deleted. Failed smoke namespaces remain for diagnosis/retention.

### Next handoff

- M02: canonical business/DLQ schemas, event dictionaries, event/analytics DTOs,
  analytics OpenAPI and producer/consumer review. G0 is not claimed from the fixture.
- M03: real event transport SDK and local diagnostics, integrating Aditya's outbox
  when supplied. No substitute outbox was added.
- Shared-template conflict to review with Jaineel: `.env.example` specifies
  `RUN_NAMESPACE=local-dev`, while common §7 specifies `dev` or isolated bench/replay
  namespaces. This infrastructure provisions `dev`; the shared file was not changed.
- Jaineel coordinates a smaller, fully declared evaluation profile once application
  services exist and the full stack is measured. This development profile is not a
  replacement evaluation config or a claim that 500 events/s is sustainable.

Setup instructions: `infra/STREAMING.md`. No commit or push was requested/performed.

## M01a — Live verification passed, 31 October 2026

PostgreSQL is running on `127.0.0.1:5432`. The pinned image actually supplies
PostgreSQL **18.2**, with pgvector **0.8.1** installed in `catalog_db`. All six
databases passed service-login, privilege, durability and resource checks.
**M01a passed; full M01/G0 remains incomplete until Kafka/Schema Registry and
the remaining contracts/profile checks are supplied.**

Docker Desktop was installed by the user. Docker's Linux engine is 29.9.2,
Compose is 5.6.1, and WSL2 reports 8 CPUs / 4,040,888,320 bytes of engine memory.
The proposed full 8-GiB SUT budget is not available in this Docker VM yet; the
PostgreSQL-only 0.75-core/2-GiB allocation was verified. No engine settings changed.

### Changes from the initial checkpoint

- Distinguished a Docker command timeout from a missing Docker installation.
  The timeout still fails visibly and instructs checking container state before retry.
- Added nonsecret live-test evidence for all 30 denied cross-database connections,
  different before/after container IDs, the retained volume and persisted marker.
- Updated `infra/images.lock.json` to `SMOKE_TESTED` using actual server facts and
  the live evidence path. The offline lock check now validates both the unresolved
  and smoke-tested lifecycle states, including required evidence/version fields.
- Updated the README and plan. No business migrations, imports, commits or pushes.

### Commands and actual outcomes

Use `.venv/Scripts/python.exe -m` for the Python module commands below.
`PROJECTCTL_ADAPTER_MODULE=infra.postgres` selects the existing CLI's owned adapter.
Docker/live pytest calls required access outside the sandbox for the engine pipe
and pytest's Windows scratch-directory ACLs.

| Command / check | Actual result | Evidence |
|---|---|---|
| `docker version`, `docker info --format ...`, `docker compose version --short` | Engine running on linux/amd64; versions/resource facts recorded | `artifacts/m01a/docker-environment-20261031.json` |
| First `projectctl env up --profile postgres-local` | Exit 4: 180-second Docker command timeout during cold startup; container continued initialization on its retained volume | `artifacts/projectctl/1c7571d3-cff1-41a6-ae87-e3dc54d726f3/` |
| Second `projectctl env up --profile postgres-local` | Exit 4: database check failed; no reset performed. Direct verification subsequently passed all six databases; exact transient DB error was not retained by the safe CLI boundary | `artifacts/projectctl/635e0215-510a-4bac-a85e-143ce89e59ad/` |
| `pytest tests/pipelines -q --junitxml=artifacts/m01a/docker-live-20261031.xml`, with `RUN_POSTGRES_LIVE_TESTS=1` | **19 passed, zero skipped**, exit 0, 36.57 seconds | `artifacts/m01a/docker-live-20261031.xml` |
| Real isolation/recreation proof from that test | All 30 cross-service connections denied; container ID changed; data-volume identity and stored marker preserved; probe removed | `artifacts/infra/postgres-local/checks/7671ad46-0834-4918-ab03-3a1be5ce3888/live-test.json` |
| Final `projectctl env up --profile postgres-local` | Exit 0; existing container/credentials/volume reused | `artifacts/projectctl/663452c9-ea1f-4ead-9a09-1970fa1f4793/` |
| Final `projectctl env verify --profile postgres-local` | Exit 0; running database verified | `artifacts/projectctl/67103724-78e4-4c3c-9e3a-ac36a55e8166/` and matching `artifacts/infra/postgres-local/checks/67103724-78e4-4c3c-9e3a-ac36a55e8166/postgres.json` |
| `pytest tests/pipelines/test_postgres.py -q --junitxml=artifacts/m01a/post-smoke-offline-20261031.xml` | **18 passed**, exit 0, after updating the smoke-tested lock | `artifacts/m01a/post-smoke-offline-20261031.xml` |
| Final Ruff lint and format checks | Passed after formatter wrapped the timeout diagnostic | Session transcript |

The running named volume is `group3-postgres-local_postgres_data`. Local URLs and
passwords remain in the ignored `artifacts/infra/postgres-local/` directory; no
credentials are copied to evidence. Kafka, registry, business tables, source import
and performance results remain NOT_RUN. Next checkpoint: Kafka/Schema Registry in
M01, including a feasible full-stack resource profile and locks.

## M01a — Initial foundation, 31 October 2026

Branch: `vichitr`. Implementation and offline checks are ready. **Real Docker
startup, isolation and persistence remain NOT_RUN**, because Docker is not installed
on this machine. The user will install Docker Desktop. Full M01/G0 is not complete.

### Changes

- `infra/compose.yaml`: pinned PostgreSQL 18 / pgvector 0.8.1 image, persistent
  named volume, loopback-only port, TCP health check, seven file-mounted secrets,
  PostgreSQL-only enforced resource allocation and owner labels.
- `infra/postgres/10-databases.sh` and `infra/.gitattributes`: first-volume
  initialization of six service logins/databases, restricted database privileges,
  catalogue vector extension and LF checkout for the Linux shell script.
- `infra/images.lock.json`: registry-resolved manifest digest, supported Linux
  architectures and explicit unverified smoke status. Actual server patch/evidence
  remains null until Docker runs.
- `infra/postgres.py`: existing `projectctl` providers for PostgreSQL-only
  `env up/verify/down`; private generated credentials; retained-volume shutdown;
  runtime image/resource/role/version/durability checks and safe evidence.
- `tests/pipelines/`: offline dependency/security checks, workspace-local pytest
  configuration using Jaineel's existing convention, and opt-in real Docker test
  for cross-database denial and persisted data after container recreation.
- `infra/README.md`: setup, credentials, boundaries, verification and recovery notes.
  `docs/vichitr/implementation_plan.md` remains the module sequence.

No teammate's service code, migrations, shared tooling, dependencies, lock or
evaluation configuration was changed. No commit or push was performed.

### Commands and actual outcomes

All commands ran from the repository root unless noted. `.venv/Scripts/python.exe`
below is Python 3.11.15 installed from the repository's locked environment.

| Command / check | Actual outcome | Evidence |
|---|---|---|
| `docker version`, `docker compose version` and standard install-path checks | Docker unavailable; user confirmed not installed | Session transcript |
| Initial `python -m pip install --target artifacts/tooling/uv-package uv==0.10.8 --disable-pip-version-check` | Failed to resolve under restricted network | Session transcript |
| `python -m pip --isolated install --index-url https://pypi.org/simple --no-cache-dir --target artifacts/tooling/uv-package uv==0.10.8 --disable-pip-version-check` | Passed with approved network access; workspace-local uv 0.10.8 | `artifacts/tooling/uv-package/` |
| Workspace-local `uv.exe sync --locked --python 3.11`, with workspace `UV_CACHE_DIR` and `UV_PYTHON_INSTALL_DIR` | Passed with approved network access; Python 3.11.15 and 37 packages installed from unchanged lock | `.venv/`, `artifacts/tooling/python/` |
| Official Docker registry token/manifest GET using Python urllib | SHA-256 over manifest bytes matches response digest; Linux amd64/arm64 available | `infra/images.lock.json` and `artifacts/m01a/registry-resolution.json` |
| Initial Ruff lint then format | Five line-length findings; formatter corrected all | Session transcript |
| Initial focused pytest with explicit basetemp/cache and JUnit | 3 passed, 15 errors, 1 skipped; missing temp parent | `artifacts/m01a/pytest.xml` |
| Rerun after workspace scratch configuration | Windows sandbox ACL denial on pytest private temp directory | Session transcript |
| `python -m pytest tests/pipelines -q --junitxml=artifacts/m01a/offline-verified.xml` using `.venv`, outside sandbox | **18 passed, 1 skipped**, exit 0; skipped test requires real Docker | `artifacts/m01a/offline-verified.xml` |
| `python -m pytest tests/pipelines tests/projectctl -q --junitxml=artifacts/m01a/final-checks.xml` using `.venv`, outside sandbox | **154 passed, 1 skipped**, exit 0, 71.03 seconds; includes existing CLI regression tests | `artifacts/m01a/final-checks.xml` |
| `python -m ruff check infra/postgres.py tests/pipelines` using `.venv` | Passed | Session transcript |
| `python -m ruff format --check infra/postgres.py tests/pipelines` using `.venv` | Passed | Session transcript |
| Git Bash `-n infra/postgres/10-databases.sh` | Sandbox signal-pipe failure; approved read-only rerun outside sandbox passed, exit 0 | Session transcript |
| `python -m projectctl env verify --profile postgres-local` with explicit adapter | Expected exit 4, Docker unavailable; real checks NOT_RUN | `artifacts/projectctl/17d0fb15-048d-4ef4-a14a-246da3c17387/` |
| `python -m projectctl env up --profile postgres-local` with explicit adapter | Expected exit 4, Docker unavailable; no database or credentials created | `artifacts/projectctl/c6084735-a918-4fdc-b6b4-082506e1ee0b/` |
| Final Ruff lint/format, `git diff --check`, owned-path/local-link/whitespace/LF checks | Passed; changes confined to owned paths; no runtime credentials created | Session transcript |

`PROJECTCTL_ADAPTER_MODULE=infra.postgres` selects the owned providers; it does not
replace Jaineel's registry or create a competing CLI. Offline test doubles are
explicitly test-only. No synthetic performance values or real integration pass
are claimed. Connection-denial assertions use libpq's failure message because
connection-establishment errors do not expose a PGresult SQLSTATE.

### Next checkpoint and handoffs

1. User installs and starts Docker Desktop with Linux containers/WSL as required
   by Docker's installer. No Windows features or Docker installation were changed.
2. Run the README's `env up`, `env verify` and opt-in live test. Resolve any real
   initialization/permissions/port/resource issues, preserve evidence and then
   update the image smoke status with actual server facts.
3. Give teammates generated URL variable names and reproducible setup instructions,
   never another user's passwords. Each owner applies only their own migrations.
4. Finish M01 with Kafka/Schema Registry, schema-dependent readiness and the full
   enforceable resource profile. Reset/migration dispatch remains a later scoped
   handoff; no destructive reset provider exists at M01a.

Do not mark M01a's real acceptance or M01/G0 complete before the missing checks run.
