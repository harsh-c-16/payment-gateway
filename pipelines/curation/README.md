# Transactional Silver provider (M06)

Owner: Vichitr. See [common §11](../../docs/specs/02_COMMON_SPEC.md) and the
[M05 handoff](../../docs/vichitr/m05_vertical_handoff.md).

AnalyticsPipeline.curate_silver(raw_receipt, batch_config) accepts all 24 registered
business event types. It verifies Bronze, validates registered wire content,
deduplicates source/event/aggregate identity, inserts Silver, applies the unique
pipeline_minute contribution, marks export pending and commits source disposition
atomically. B0 requires one row per sink transaction; booleans/coercions and O1
batch sizes are rejected. Normalized payloads use the existing canonical payload
models, preserve explicit optional nulls and retain the original document/hash.
Versions are unique across event types within a producer/aggregate, as required
by common §7. Older distinct versions remain valid facts. Business reducers are M07.

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

The M05 tests use real PostgreSQL/files/Kafka. Invalid notification atomicity also
has explicitly labelled outbox doubles; full real-outbox integration remains pending.
See the [M06 handoff](../../docs/vichitr/m06_silver_handoff.md) for typed files,
the quality smoke, missing catalogue handoff and exact remaining checks.
