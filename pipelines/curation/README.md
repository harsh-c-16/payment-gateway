# Transactional Silver provider (M05)

Owner: Vichitr. See [common §11](../../docs/specs/02_COMMON_SPEC.md) and the
[M05 handoff](../../docs/vichitr/m05_vertical_handoff.md).

AnalyticsPipeline.curate_silver(raw_receipt, batch_config) implements the first
CONVERSATION_TURN slice. It verifies Bronze, validates registered wire content,
deduplicates source/event/aggregate identity, inserts Silver, applies the unique
pipeline_minute contribution, marks export pending and commits source disposition
atomically. B0 requires one row per sink transaction; booleans/coercions and O1
batch sizes are rejected. Full normalization/all event types are M06/M07.

route_dlq preserves the first raw locator/hash and uses Aditya's append_outbox in
the same transaction. Missing outbox or append failure leaves the source unfinished
and never authorizes an offset. No production fake/outbox table is provided.

ingest_once uses the SDK's ownership and contiguous-prefix guards only after SQL
COMMIT. Close/restart the ConsumerGroup after an exception so unfinished input is
redelivered. The supplied B0 worker exits on failure. Typed errors are not swallowed
as successful/dirty input. Observations are post-commit upper bounds; recovery is
labelled, and receipt-journal cursors preserve later updates to earlier sources.

The M05 tests use real PostgreSQL/files/Kafka. Invalid notification atomicity also
has explicitly labelled outbox doubles; full real-outbox integration remains pending.
