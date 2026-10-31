# Shared event transport (M03)

Owner: Vichitr. Authority: [common §§6.1, 7 and Appendix A](../../docs/specs/02_COMMON_SPEC.md).
Import opens no Kafka connection and registers no schemas. Use the existing
`infra.streaming` environment adapter to prepare current/historical mappings.

## Startup and construction

```python
from shared.event_transport import build_event, configure_transport

configure_transport(source_service="conversation", dataset_revision=actual_dataset_revision)
event = build_event(
    event_type="ADD_TO_CART",
    payload=payload,
    context=request_context,
    aggregate_type="session",
    aggregate_id=request_context.session_id,
    aggregate_version=next_session_event_version,
    event_time=occurred_at,
)
append_outbox(tx, event)  # Aditya's library; caller's existing transaction
```

The M1 keyword binding is unchanged. Configure once before readiness; missing or
tampered cache fails visibly. Default cache is ignored
`artifacts/infra/streaming-local/registry-manifest.json`; override with `cache_path`
or `EVENT_SCHEMA_CACHE_PATH`. Bootstrap uses `bootstrap_servers` or
`KAFKA_BOOTSTRAP_SERVERS`, otherwise `127.0.0.1:9092`. Container callers supply
`kafka:9092` and mount a verified cache. `.env` is not automatically loaded.
Dataset revision falls back to `CATALOG_DATASET_REVISION`; catalogue-linked facts
require a real revision. Namespace is `dev` or isolated `bench-`/`replay-`, never
the shared template's older `local-dev`. Source defaults to the declared event
owner unless explicitly configured; this is not an authentication mechanism.

Construction deep-copies input, allocates event_id/produced_at once, validates and
does not publish. Optional keywords `metadata`/`source_service` support declared
simulation/benchmark producers. Treat the result as immutable; retries reuse the
stored event. Optional root/metadata values and explicit nulls survive serialization.

## Delivery and validation

`publish_event(event, topic, key)` returns PublishAck only after broker delivery
confirmation, never queue admission. `RetryablePublishError` exposes event_id,
reason, retryable=true and uncertain: false means not queued; true means delivery
is unconfirmed. Retry with identical identity/content. Another Kafka delivery is
possible, so consumers still deduplicate. `close_transport()` flushes and reports
unconfirmed publication. Explicit EventCodec/KafkaPublisher instances are available.

Fixed settings in `publisher.PRODUCER_SETTINGS`: idempotence on, acks=all, maximum
in-flight=5, Zstandard, linger=5 ms, native queue=10,000 records/65,536 KiB,
delivery timeout=10,000 ms and request timeout=5,000 ms. Application pending entries
are capped at 10,000 records or 64 MiB of value/key/header bytes. Callers must
also bound their own worker/task counts. No SDK retry regenerates identity.

`validate_event(raw_bytes, headers, topic, key)` returns ValidEvent or
ValidationFailure without writes or per-event registry calls. `source_record=record`
binds exact bytes/coordinates and checks the normal five-second future bound from
ingress time. Four-argument pure validation explicitly returns source_record=null;
coordinates cannot be inferred. Tombstones require their SourceRecord to preserve
its original hash. ValidEvent.document retains the complete parsed immutable object.
Replay must supply its declared ingress clock/policy without altering source time.

The cache verifies current pins and released hashes in
`contracts/events/supported-history.json`. Startup retrieves matching historical
definitions/IDs once; offline validation still checks hashes. Unknown/unpublished
IDs fail explicitly. Registry IDs are local and are never copied across computers.

## Manual offsets and ownership

```python
from shared.event_transport import ConsumerGroup, consume_records, commit_offsets

group = ConsumerGroup("dev.analytics.v1", topics, "127.0.0.1:9092")
try:
    for record in consume_records(group, topics, 100, 50):
        persist_durable_disposition(record)  # M04/M05 caller, not supplied here
        group.mark_durable(record)  # after actual successful durability
    result = commit_offsets(group, group.durable_next_offsets())
    if not result.succeeded:
        retain_and_retry_unconfirmed_offsets(result)
finally:
    group.close()
```

`group` is a long-lived handle used on its creating worker thread. Subscription
and namespace are fixed; automatic commits/offset storage are disabled. Requests
are `{(topic,partition): next_offset}`. Only the ordered delivered durable prefix
can advance; actual Kafka log-numbering gaps do not invent source records. Partial
commit acknowledgements release only successful partitions. Uncertain offsets
remain buffered for retry. Revoke commits only already-durable prefixes; lost
ownership commits nothing. Old ownership tokens are fenced after reassignment.

SourceRecord preserves raw key/value bytes, null versus empty values, duplicate
header order, nullable Kafka timestamp and UTC ingress. Its raw_sha256 hashes the
versioned length-delimited original byte stream in `consumer.raw_fingerprint`,
not parsed JSON. assignment_epoch is runtime-only and excluded from source hashes.

Declare one or three workers, identical group worker counts and unique indexes.
Static IDs fence duplicate indexes. The 2,000-record/16-MiB raw-buffer group budget
is split including remainders. Application bytes use half the share; quarter-sized
native queue/fetch allowances reserve native headroom. These controls do not bound
total Python/native RSS to that number. Sources above 1 MiB rewind/fail without
commit; normal event values stay capped at 64 KiB. Resource failures never become
fabricated successful/dirty dispositions. At capacity, pause/resume preserves
polling; max_records=0 services heartbeats/rebalances without handing new records
to the caller. Poll wait is 0–1,000 ms; commit RPC socket bound=5 seconds. Classic/
range assignment, session=10 seconds and max-poll interval=300 seconds are fixed.
Analytics business ingestion excludes DLQ; explicit DLQ reads are diagnostic only.

Real and explicit-double tests are in `tests/pipelines/`. See
[M03 handoff](../../docs/vichitr/m03_transport_handoff.md). Actual source durability,
Bronze/Silver/Gold and Aditya's outbox remain separate modules/dependencies.
