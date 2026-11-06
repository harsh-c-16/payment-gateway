# M11 baseline instrumentation checkpoint

Owner: Vichitr. This is preparation for M11a, not a correct-B0 freeze or a B0/O1
performance comparison. The independent full T-03 fixture, applicable integrated
correctness gates and initial measured B0 bottleneck trace remain pending.

The existing B0 path retains one source row per sink transaction. No batch limit,
raw chunk bound, validation, producer setting, publication cadence or SUT resource
allocation changes here. The timer previously included post-COMMIT receipt
observation work; it now stops immediately after the sink transaction context
acknowledges COMMIT.

## Provider and timing semantics

### Quality wire handoff — 6 November 2026

`pipelines.ingestion.quality.QualityMaterializer` supplies the pure materializer
callback expected by `benchmarks.drivers.PipelineDriver`. Construct it with a
verified `EventCodec`, the frozen workload recipe's exactly 10,000 sorted unique
`selected_skus`, and the actual catalogue `dataset_revision`. The harness remains
responsible for verifying the catalogue manifests and freezing that selection.

Call `(record, context)` using the scheduler's existing context: namespace, run ID,
request ID, scheduled UTC time and produced UTC time. It returns the existing
`Packet` DTO with plain JSON/raw bytes, topic, key and JSON-journalable text headers.
The publisher binding converts header values back to UTF-8 bytes. Valid stock
facts use the independent recipe's ordinal modulo 10,000 and version division;
runtime IDs come from the scheduler's request identity. Simulation provenance
is explicit. No dictionary/facet values are guessed.

The ten invalid subcases deliberately mutate validated SDK bytes. They require
the runner's explicit raw-fixture publisher with the same frozen Kafka settings;
do not weaken normal `KafkaPublisher` validation to send dirty fixtures. Duplicate
records deliberately fail if rematerialized: the existing scheduler must reuse
the original persisted packet, including identity, timestamps and headers.

Sixteen focused checks cover identity/bytes stability, key/version boundaries,
every independent `SUBCASES` reason and rejected duplicate/namespace/selection
inputs. These are pure schema checks with explicit test SKUs/registry IDs, not
the 100,000-record Kafka run or an independently reviewed performance result.
Jaineel still owns the publisher/lifecycle/audit/observer factory and its review.

Migration 009 creates `sink_batches`. Each transaction atomically stores its
source coordinates, capture ID, effective namespace, caller's run ID, optional
replay ID, code/transform pins, row count and four disposition counts alongside
the final source disposition and any Silver/Gold/quarantine changes. The counts
sum to the transaction's rows. `redelivery_noop` counts processing attempts,
not extra admitted Kafka records or new Silver effects. A rollback leaves no
committed batch row; Bronze/captured source receipts may still exist unfinished.

`started_at` and `committed_observed_at` are UTC wall-clock observations from
the sink process. `flush_duration_seconds` uses that process's local monotonic
clock, from before connection acquisition through COMMIT acknowledgement. It
includes connection/lock waits, validation, reducers and the batch-audit INSERT.
It excludes connection teardown, Bronze capture, subsequent timer/receipt-observation SQL writes,
Gold publication and offset commits. It is not DB-only execution time or
end-to-end visibility latency. Do not subtract wall clocks to reconstruct it.

After COMMIT, a separate analytics connection records the elapsed sample. A crash
or failure before that write leaves the committed batch's timer NULL/`missing`;
recovery never fabricates the elapsed value. Retry uses normal source dedup and
creates a separate attempt row. An observation failure propagates before Kafka
durability marks/offset commits. Receipt-observation recovery and Gold visibility
keep their existing semantics. Transaction membership survives a missing timer.
The existing sink histogram uses the same elapsed sample. The worker now serves
its own process-local registry as described below; the API does not aggregate it.

The extra INSERT and post-COMMIT UPDATE are instrumentation overhead. Keep them
enabled identically in both future comparators. No throughput claim is made.
Old schema-008 runs gain no invented historical batch rows when migrated.

## Bounded read-only handoff

```python
from pipelines.curation.sink_observations import read_sink_batches

page = read_sink_batches(connect, namespace, run_id, after=0, limit=1000)
# Repeat using page[-1]["batch_sequence"] until the page is empty.
```

The provider validates canonical namespace/run identity and strict bigint cursor
and 1..1000 row limits before connecting. Results are SQL dictionaries containing
UUID/datetime values; the harness owns artifact serialization and metric
calculation. Namespace and run filters are mandatory. It performs no writes or
business calls. Sources are bounded by the sink row limit (currently one).

Export after stopping/draining writers and completing receipt observations. This
is a transaction audit, not a live change-feed: concurrent batches can commit
while reading and an already-read NULL timer can later become observed. Re-read
from zero after drain for the authoritative export. Preserve NULLs in raw evidence.
No new endpoint or CLI command is added to the canonical surface.

Jaineel already supplies one-second `KafkaLagReader`, resource readers,
`ObservationSession`, independent workload accounting and receipt/visibility
collection. Use those rather than a second collector. The API already reads
namespace-scoped pending exports/generation from SQL. Queue observations are now
available from the SDK and worker JSON logs; see the
[current handoff](team_handoff.md#buffer-observation-semantics-for-the-collector).
Real observer-factory adoption still needs Jaineel's bindings before a complete
baseline trace. Worker metric exposure is described below.

## Worker metrics preparation checkpoint

`python -m pipelines.ingestion.worker` starts the installed Prometheus client's
HTTP exporter using that worker's dedicated `pipeline.telemetry.registry` before
entering the consumer loop. Inside Compose, scrape
`http://analytics-worker:8006/metrics`; no host port is published for the worker.
The API remains at `http://analytics:8006/metrics` with its own registry and its
SQL-backed namespace gauges. Scraping the API cannot recover worker histograms.
Each container has its own network address, so the internal port is independent.

The worker endpoint exposes observed source dispositions, unique Silver counts,
sink row/flush histograms and the existing publication duration/generation/backlog
observations. Empty metric families stay absent. The exporter never polls Kafka,
opens a database connection or touches offsets: its HTTP thread reads registry
samples while the worker retains SDK thread ownership. No default global registry
or second process collector is added. Container CPU/RSS and Kafka lag still come
from Jaineel's existing resource/lag readers; this endpoint does not invent them.

The worker's entrypoint closes the listener when its loop returns or raises. A
bind failure propagates before consumption starts. A forced process exit relies
on OS socket cleanup and normal Kafka redelivery. HTTP availability alone does
not prove data readiness or progress; counters reset on process restart and gauges
show the latest local observation. Use the durable transaction/receipt audit for
cross-restart reconciliation, and the API's SQL gauges for namespace-wide state.
Jaineel should bind a separate worker Prometheus target and keep its identity
distinct from API or future worker instances. Collector composition stays his work.
The Compose DNS target is reachable by collectors on that Docker network. A
host-only collector needs an explicitly coordinated loopback mapping or network
placement; this checkpoint publishes no additional host port or automatic discovery.

The real check starts `worker.main` in a separate process with only its connection
factory/FileStore bound to an isolated test schema/root. It uses actual HTTP,
Kafka, PostgreSQL and Parquet and verifies two broker records (one duplicate), two
committed sink attempts, one visible Gold effect and committed next offset 2.
The parent process registry stays empty. Lifecycle/bind-error unit checks use
explicit server/worker doubles. No real outbox is needed for these valid sources.
This checkpoint changes no migration, public DTO/endpoint contract, sink batching,
producer setting, publisher cadence or container CPU/RAM allocation. Full baseline
gates and performance/scaling trials remain pending.

The append-only audit currently has no retention/GC, like the retained source
ledger. Keep benchmark runs isolated and account for disk/SQL growth. No live
namespace cleanup is introduced.

## Verification and next checkpoint

Verification is recorded with actual source commits, commands and raw evidence
in [progress](progress.md). Pure reader bounds, real SQL/file audits, rollback,
missing-timer recovery, migration upgrades, native Kafka redelivery after actual
process death and existing affected regressions are the required local checks.
The elapsed-clock test uses an explicit clock double to prove the timer boundary;
it is not a measured latency. Invalid disposition tests use an explicit local
outbox double; the real shared outbox remains an Aditya handoff.

Before O1 or scaling experiments: close applicable T-01/T-03/T-07/T-12 with the
actual providers and independent 100,000-record oracle, freeze the real B0
commit/config, then collect and diagnose its initial trace. Harsh's real SKU
manifest and Aditya's outbox/providers remain necessary for the affected gates.
Jaineel owns runner/observer composition and independent reconciliation. Only
then implement and correctness-test 100-row/50-ms transaction grouping and run
the three paired comparisons with fixed controls. No result is assumed faster.
