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
The existing sink histogram uses the same elapsed sample; process-local histograms
in the worker are not automatically shared with a separate API process.

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
namespace-scoped pending exports/generation from SQL. Queue saturation, real
observer-factory adoption and cross-process metric exposure still need explicit
bindings before a complete baseline trace; this checkpoint does not supply them.

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
