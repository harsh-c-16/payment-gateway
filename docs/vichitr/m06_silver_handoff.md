# M06: all-domain Silver provider

Owner: Vichitr. Authority: common §§7/11 and personal brief V04.

The provider accepts all 24 registered domain event types. The worker subscribes
to conversation, retrieval, order, inventory and payment topics in its existing
namespace/group. DLQ notices remain outside business ingestion. B0 still commits
one source record per sink transaction; batching controls and Kafka durability
rules are unchanged.

## Data and compatibility

Apply analytics migrations with the existing `PROJECTCTL_ADAPTER_MODULE=infra.analytics`
and `python -m projectctl db migrate --namespace bench-<run>` before starting the
API/worker. The global command still reports dependency exit 4 for absent other
owners/outbox providers; inspect the owned evidence for versions 1, 2 and 3.
Migration 003 adds/backfills normalized payloads and enforces one event per
producer/aggregate/version across event types. Existing immutable envelopes,
canonical hashes, source locators and migrations 001/002 are unchanged.

Payload normalization uses the registered typed models, supplies optional nulls
and performs no catalogue re-parsing, attribute inference, currency conversion or
timestamp backdating. Integer money/stock fields stay exact. Older valid versions
remain in Silver; M07 decides latest business state. Only fresh event IDs affect
pipeline_minute, reducer contribution keys or export-pending membership. Conflicts
and their raw quarantine/notification remain in the same caller transaction.

New files use `silver-events-v1`: typed envelope/provenance plus a payload struct
for every known field, including nullable intent category/brand/size/colour/material,
UTC timestamps, int64 money/counts and string arrays. Unused payload fields are
null. Original canonical envelope/metadata JSON retains unknown optional additions
and supplied dictionary revisions/hashes. Existing `silver-conversation-turn`
Parquet remains readable; a manifest can contain old and new descriptors. Files
still use Zstandard and event-date/event-type logical partitions.

The current event contracts do not contain a full Product snapshot. Intent facets
are request filters, not inferred product attributes. Harsh's real catalogue/facet
artifacts are absent, so this checkpoint preserves supplied provenance but cannot
verify it against those artifacts or claim authoritative SKU/facet reconciliation.

## Failure and API behavior

Storage/connection/serialization/deadlock errors get three bounded retries with
250/500/1,000-ms backoff. Each failed consumer group closes before a fresh group
rejoins from committed offsets. Exhaustion propagates. Missing outbox and other
permanent failures stop immediately; no dependency failure becomes dirty input.
Previously committed B0 records remain durable if the next record fails.

The quarantine API now includes its required next_cursor for empty/nonempty pages.
Pagination uses the existing ordered quarantine identity, not UUID sorting. No
public DTO, schema registry asset, reason dictionary or HTTP path changed.

## Quality evidence and handoffs

The owned live quality smoke is explicitly synthetic: 2,000 distinct source
coordinates, expecting 1,970 new valid +20 duplicate deliveries +10 invalid records
covering all ten dirty subcases. It checks real SQL, raw recovery, active Parquet,
and notifications through an explicitly labelled SQL outbox double. It is not the
required full 100,000-record W-QUALITY run or a throughput measurement.

An exact reason-code conflict remains for consumer review: benchmarks/quality.py
SUBCASES expects `wrong_money_type → INVALID_TYPE`; the existing registered-event
validator classifies wrongly typed monetary fields as `INVALID_AMOUNT`. This
checkpoint preserves that public validator behavior and records the difference;
Jaineel/Vichitr must agree before freezing full-fixture reason reconciliation.
Both paths classify the source as invalid, so disposition arithmetic is unaffected.

Full W-QUALITY and independent G0/G1/G4 remain NOT_RUN. Aditya must supply the real
shared outbox; Harsh supplies reviewed catalogue/SKU/dictionary artifacts; Jaineel
adopts the provider and independent fixture. The M05 full-snapshot cap (10,000 facts
or 8 MiB document text) remains explicit. M08 incremental publication is needed
before full W-QUALITY active-file/scale runs; this module does not raise that cap.

See [progress](progress.md) and [test skips](test_skips.md) for actual runs, preserved
failures, source revisions, evidence and pending GitHub Windows CI investigation.
Next implementation checkpoint: M07 business Gold reducers and reconciliation.
