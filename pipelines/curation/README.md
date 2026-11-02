# Transactional Silver and event-time provider

Owner: Vichitr. See [common §11](../../docs/specs/02_COMMON_SPEC.md) and the
[M05 handoff](../../docs/vichitr/m05_vertical_handoff.md).

AnalyticsPipeline.curate_silver(raw_receipt, batch_config) accepts all 24 registered
business event types. It verifies Bronze, validates registered wire content,
deduplicates source/event/aggregate identity, inserts Silver, applies the unique
pipeline_minute/business contributions, marks export pending and commits source disposition
atomically. B0 requires one row per sink transaction; booleans/coercions and O1
batch sizes are rejected. Normalized payloads use the existing canonical payload
models, preserve explicit optional nulls and retain the original document/hash.
Versions are unique across event types within a producer/aggregate, as required
by common §7. Older distinct versions remain valid facts. M07 business reducers
use latest versions for state and distinct historical stages for the funnel.
Semantic Gold conflicts roll back the Silver/reducer savepoint before atomic
quarantine and outbox append. Unexpected SQL errors leave the source unfinished.

M09 tracks durable partition maxima, ten-second idleness and a non-regressing
watermark with 120 seconds allowed lateness. Late facts keep their original
content and revise Gold with `LATE_RECONCILIATION` lineage. See the
[M09 handoff](../../docs/vichitr/m09_event_time_handoff.md) for timestamp flags,
provisional windows and separate initial/late visibility inspection.

route_dlq preserves the first raw locator/hash and uses Aditya's append_outbox in
the same transaction. Missing outbox or append failure leaves the source unfinished
and never authorizes an offset. No production fake/outbox table is provided.

ingest_once uses the SDK's ownership and contiguous-prefix guards only after SQL
COMMIT. Close/restart the ConsumerGroup after an exception so unfinished input is
redelivered. The B0 worker subscribes to all five business topics. It retries storage,
connection, serialization and deadlock failures at most three times, with fresh
consumer groups and 250/500/1,000-ms backoff; exhaustion propagates. Missing outbox
and other permanent errors stop immediately. Errors are not classified as dirty
input. Observations are post-commit upper bounds; recovery is
labelled, and receipt-journal cursors preserve later updates to earlier sources.

M11's baseline instrumentation retains each committed transaction's source membership,
four disposition counts, run/capture/replay identity and code/transform pins in
`sink_batches`. The nullable flush timer spans connection acquisition through the
sink COMMIT acknowledgement, excluding later observation writes. Read a drained run
with the bounded `read_sink_batches` provider; missing timers cannot be recovered.
See the [M11 handoff](../../docs/vichitr/m11_baseline_handoff.md) for exact semantics
and the remaining correctness/benchmark gates. This checkpoint still rejects O1.

The existing `quarantine_total{reason}` metric records only new committed invalid
source dispositions. Rollback and already-final source redelivery do not increment
it. These process counters can reset/lose an observation at a crash; durable
source/quarantine audits remain authoritative across restarts.

The M05 tests use real PostgreSQL/files/Kafka. Invalid notification atomicity also
has explicitly labelled outbox doubles; full real-outbox integration remains pending.
See the [M06 handoff](../../docs/vichitr/m06_silver_handoff.md) for typed files,
the quality smoke, missing catalogue handoff and exact remaining checks.
