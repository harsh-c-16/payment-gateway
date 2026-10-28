# P5 telemetry handoff

This implements J03/P5 only. It does not start services, implement provider
instrumentation, or establish G1/G3, a baseline, or performance results. P6 is
not started. Canonical authorities: [common §14 and Appendix A](../specs/02_COMMON_SPEC.md),
[evaluation §5](../specs/03_EVALUATION_SPEC.md), [runbook §7](../specs/09_EVALUATION_RUNBOOK.md).

## Reproduce the checkpoint

From the repository root, with Python 3.11 and the unchanged application lock:

```powershell
uv sync --locked
uv run --locked python -m pytest tests/telemetry -q
uv run --locked python -m benchmarks.manual.observer_stall
uv run --locked python benchmarks/manual/verify_p5.py
```

The demo prints its evidence directory. `stub-stall/` contains explicit doubles:
Kafka lag stays zero, pending Gold rises 0/10/20/30, and outbox rows rise 0/2/4/6.
The projection collector succeeds once, then fails for three one-second ticks.
Its missing values are null, including its latest value; the summary is
`INCOMPLETE`. This is a checkpoint assertion, not a measured SUT workload.
`real-generator/` separately contains three actual one-second CPU/RSS readings
of the demo's Python process. Its scope is **generator_process**, not total SUT
CPU, host memory, or container memory. No Kafka broker, database or Grafana is
started. `demo_checks.json` labels both kinds of evidence.

Open `observations.jsonl`, `lag.csv`, `backlogs.csv`, `resources.csv`,
`observation_context.json`, `observation_end.json` and `offline_summary.md`.
Each raw row records run/namespace/workload/variant, collector mode, UTC time,
scheduled and observed monotonic offsets, unit, labels, sequence, status and
missing-data reason. Kafka rows retain **next** offsets and their partition.
An absent committed offset is unknown, not a zero-lag reading.

Rebuild into a fresh output directory without any service or Grafana:

```powershell
uv run --locked python -m benchmarks.observation_summary --run-dir artifacts/p5/DEMO/stub-stall --out artifacts/p5/REBUILD
```

Replace `DEMO` with the emitted directory name and choose a new `REBUILD` name.
The command validates hashes and writes JSON plus Markdown. Exit 0 means the
reconstruction succeeded; the table's `status` still shows incomplete evidence.
Missing/corrupt evidence returns exit 4. Repeat with `real-generator/` to inspect
actual process resources. Offline rebuilding does not rerun the experiment.

## Provider instrumentation

Owners add instrumentation only in their own service code. The complete common
names and labels are implemented in `shared/telemetry/metrics.py`. Example:

```python
from shared.telemetry import Telemetry, bind_context, log_operation

metrics = Telemetry(label_values={
    "service": {"catalog"},
    "route": {"/v1/search", "/v1/products/{sku}"},
    "status": {"200", "404", "409", "422", "503"},
})
metrics.record("request_duration_seconds", measured_seconds,
               service="catalog", route="/v1/search")
metrics.record("requests_total", 1,
               service="catalog", route="/v1/search", status="200")
with bind_context(request_context, "catalog"):
    log_operation(logger, "search", "success", measured_seconds,
                  resource_id=search_id)
```

Expose `metrics.exposition()` from the owner's `/metrics` endpoint using the
Prometheus content type. Use a dedicated registry; do not combine this library's
process metrics with a second default process collector in the same registry.
Owners must register finite label vocabularies. Use route templates and stable
reason/status enums, never resource IDs, SQL, error text, user text or URLs with
IDs. A metric family is created on its first actual observation. Missing samples
must not be recorded as zeros. Known health failure may set
`benchmark_observation_up{collector}=0`; that does not replace the missing value.
The logical-series cap is 1,000 by default; histogram buckets expand each series.

Latency histograms use the exact common buckets (seconds): .001, .005, .010,
.025, .050, .100, .200, .500, 1, 2, 5, 10, 30, 60, with the client's +Inf bucket.
The row-count histogram has separate row-count buckets. Per-ID timings remain
authoritative for exact nearest-rank quantiles. `TimingWriter.span` retains
`perf_counter` elapsed durations even if the operation raises. `append` accepts
owner-measured durations with an explicit clock domain; a missing timer stays
null/MISSING. It does not subtract different machines' clocks.

`timings.jsonl` is flushed after every record; `TimingWriter.close()` creates
`timings.parquet` in bounded batches. After interruption, `rebuild_timings` can
recreate the Parquet in a copied evidence directory where no target exists.
Do not overwrite raw evidence. JSONL stores per-ID samples, not Prometheus labels.

## Collector bindings and lifecycle

`observe_run(ObservationConfig)` is an async observation stream.
`ObservationSession` persists it while P4 runs. Smoke/performance uses one-second
fixed ticks and a default 800-ms reader deadline. Only explicitly labelled tests
may use shorter ticks. Slow polls cannot shift the declared schedule; missed
ticks get missing rows. Every collector declares expected series beforehand,
so partial/empty responses do not disappear from denominators. Reader callbacks
must cooperate with cancellation and SDK calls must have their own deadline.

Available real collector paths:

| Reader | Source and limits |
|---|---|
| `PrometheusReader` | Explicit HTTP(S) metrics URL, exact metric/label selection, bounded 2-MiB response and total timeout; missing series stay missing. Supports outbox count/oldest age, pending Gold, quarantine/projection/saga and service CPU/RSS. |
| `KafkaLagReader` | Real `confluent_kafka.admin.AdminClient` reads for declared consumer group and partitions; log-end next minus committed next. No subscribe/commit/reset/create. Missing/uninitialized partitions stay missing. Admin reads are not an atomic broker snapshot; inconsistent offsets are rejected. |
| `SelfResourceReader` | Actual generator `process_time` and Windows working set or Linux `/proc/self/statm` current RSS. Unsupported current RSS stays missing; it is never replaced with historical peak RSS. |
| `CgroupV2Reader` | Explicit owner-supplied Linux cgroup directory: cpu.stat, memory.current and memory.peak. Missing files remain missing. Allocation and resource_scope are retained; no automatic attribution of a host cgroup to the SUT. |
| `GoldVisibilityReader` | Owner-supplied read-only P3 active-Gold audit projection, pinned as described below; never substitutes Kafka commits or staging counts for membership. |

For example, a provider factory constructs a real AdminClient with the locked
broker settings, then `collector("kafka", KafkaLagReader(admin, group, partitions))`.
An explicit `Series("outbox_pending", "orders", "rows", (("service", "orders"),))`
can be passed to `PrometheusReader`, then to
`Collector("orders", (series,), reader, mode="real")`. Add a separate
`outbox_oldest_age_seconds` series and a separate `gold_pending_events` series.
The default registry still contains **no real workload bindings**. There is no
automatic localhost discovery and no fallback to the test directory.

Register an explicit P4 `ExperimentBindings.observer_factory(context, directory,
evidence_kind)` that returns `ObservationSession(ObservationConfig(...))` using
the exact context IDs, mode, evidence kind and directory. The runner starts it
after validation and stops it after drain/reconciliation, before hashing run
artifacts. Real sessions reject collectors labelled stub. Stub performance is
forbidden. Missing factory keeps the existing visible unexecuted collector slots;
it does not fabricate samples. `sut_performance` remains INCOMPLETE/NOT_RUN until
the later real evidence gates; a file's presence alone cannot lift that gate.

Optional `ExperimentBindings.telemetry` connects the shared registry to P4's
planned/admitted counters and active-plus-queued count/bytes. Register phase
values warmup/measurement. Drain admissions do not enter measurement counters.
Passing the same registry as `ObservationConfig.telemetry` records collector
health with a finite registered collector vocabulary. Expose that registry from
the harness's own metrics endpoint when Vichitr provides its scrape target.

`GoldVisibilityReader` consumes the **existing harness audit projection**, not a
new canonical provider DTO: namespace, generation, manifest_sha256,
query_generation, query_manifest_sha256 and membership_ids. Vichitr's binding
must read the actual active-manifest pointer, its membership proof and query
that exact generation. Persist the full source projection with its provenance.
The reader rejects mismatched/regressing generations, changed hashes at the same
generation, wrong namespaces and duplicate membership IDs. It retains all raw
projections under `manifests/gold-audit-*.json` and the first observed visibility
of each unique ID with generation/hash and evidence reference. Polling times are
conservative upper bounds. These consumer checks supplement the independent P3
oracle; an arbitrary acknowledgement list is not a valid provider binding.

Offline offered/admitted rates use P4's frozen physical cohort and actual timing
denominator. Gold goodput additionally requires complete active-membership
collection and `shared_host_clock=True` after verifying the single-host clock
profile. Without those controls it remains null. It counts only unique valid
measurement IDs first observed within the measurement window, excluding warmup,
duplicates and drain observations. Missing raw timers remain visible beside
completed-only quantiles. No unconditional SLO is inferred from these tables.

CPU utilization uses adjacent valid counter deltas / (actual monotonic elapsed ×
declared allocated cores) ×100. Gaps, resets and changed allocations invalidate
that interval. Process RSS is a sampled peak per component; cgroup memory has
separate accounting. No sum of per-component peaks is labelled simultaneous SUT
memory. Provider durations, produced_at and active-Gold timing receipts are still
needed for real producer-to-Gold, Silver and publication latency claims.

## Grafana / Prometheus handoff

`dashboards/benchmark.json` is a deterministic importable definition generated by
`dashboards/build_dashboard.py`. It shows run/variant/workload/evidence context,
offered/admitted/goodput, histogram quantiles, per-partition lag, pending Gold,
outbox count/age, quarantine, projection, stock/saga states, queues, CPU/RSS and
availability. Nulls are not connected or filled with zero. Operator-supplied
context is descriptive: select only that run's actual scrape jobs and time range.
Run/event IDs are not added as new Prometheus labels. Exact cohort results live
in the offline table, not histogram estimates.

The harness-only `benchmark_inventory_units{state}` gauge is an optional approved
read-only inventory audit aggregate (on_hand/reserved/available); Aditya must
review the projection before use. Likewise `benchmark_gold_visible_total{phase}`
must be incremented only by a reviewed active-membership/cohort binding, never a
staging or acknowledgement counter. These absent series are intentionally blank.
They are monitoring projections and do not alter public business/event DTOs.

Vichitr owns Compose, server/image locks, scrape targets, dashboard provisioning,
one-second scrape/refresh support and retained-volume startup. Coordinate those
settings with him; this milestone changes no infrastructure files. Import into
his running Grafana, choose the Prometheus data source/jobs, set run context and
time range, then repeat the stall/gap check with actual owner services. Grafana
import, PromQL execution against a real Prometheus server, real Kafka/cgroup/SUT
measurements and G1/G3 are **NOT_RUN** here. Hosted Windows/Linux CI is also
unverified until GitHub executes it.

Implementation references: [Prometheus Python histogram API](https://prometheus.github.io/client_python/instrumenting/histogram/),
[Grafana JSON model](https://grafana.com/docs/grafana/latest/visualizations/dashboards/build-dashboards/view-dashboard-json-model/),
[Arrow ParquetWriter](https://arrow.apache.org/docs/python/generated/pyarrow.parquet.ParquetWriter.html).
