# Exact-byte Bronze capture and ledger (M04)

Owner: Vichitr. Authority: [common §§11–12](../../docs/specs/02_COMMON_SPEC.md).

```python
from pipelines.ingestion import BronzeCapture, ingest_bronze, read_bronze
from pipelines.ingestion.receipts import persist_capture
from pipelines.storage import FileStore

store = FileStore("/lakehouse")
receipt = BronzeCapture(store).ingest_bronze(source_records)
# Or ingest_bronze(source_records) with explicit LAKEHOUSE_ROOT=/lakehouse.
assert read_bronze(store, receipt)
with analytics_connection.transaction():
    persisted = persist_capture(analytics_connection, receipt, store)
```

Capture accepts a nonempty available sequence bounded at 2,000 records/16 MiB,
using one namespace and the five business topics. DLQ is excluded. JSONL wrappers
preserve base64 key/value bytes, null versus empty, ordered duplicate headers,
coordinates, nullable broker timestamp, UTC ingress, raw fingerprint and
file#one_based_row locator. Ownership tokens are runtime-only. No parsed event
substitutes for source bytes; malformed UTF-8/JSON is retained.

Physical chunks use fixed 2-MiB and 50-ms accumulation bounds across sink variants.
The function never waits to accumulate another input batch. The timer bounds
accumulation, not disk latency; callers supply already available bounded sequences.
Receipt timestamps are observed after file durability, not Kafka acknowledgement,
Silver commit or Gold visibility.

The **encoded JSONL wrapper**, including base64, escaped headers and metadata,
must fit 2 MiB (2,097,152 bytes). The user approved this common-spec increase on
31 October 2026. A 1-MiB raw source with ordinary headers now fits after encoding;
the SDK's raw-source ceiling and normal domain value limit (64 KiB) are unchanged.
Header-heavy wrappers exceeding the total encoded cap still raise CaptureTooLarge
with offsets untouched. No separate unbounded metadata allowance is added.

persist_capture verifies files/receipt before SQL writes in the caller's active
analytics transaction. Its savepoint rolls back even a caught content conflict.
Identical source coordinate/hash is a capture redelivery no-op and keeps the first
locator/ingress/time. Changed hash at that coordinate is corruption; the helper
rolls back. Same event bytes at a new offset are a new source record; event-ID dedup
is M05/M06. Capture IDs cannot change content on retry.

**Capture alone never authorizes an offset commit.** M04 rows have NULL disposition,
event ID and downstream times, with timing_validity=missing. They are not public
SourceReceipt responses. Neither capture nor persistence calls mark_durable,
commit_offsets, Silver, Gold or an outbox. M05 must atomically finalize disposition
with Silver/reducers or quarantine plus Aditya's real outbox, commit that transaction,
then mark only the durable contiguous consumer prefix. Live broker tests prove
capture-only commits are rejected.

migrate_analytics(tx) applies only migrations/analytics/001_capture.sql using a
transaction lock and normalized-line-ending checksum. Caller owns commit. It creates
capture/source receipt, quarantine and processing-run foundations; no substitute
outbox. See [handoff](../../docs/vichitr/m04_capture_handoff.md) for CLI composition
and remaining provider work.
