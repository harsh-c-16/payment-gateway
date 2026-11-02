# M05 single-event vertical slice

Owner: Vichitr. Authority: common §§11–12. Source code implements the M05 provider;
full G1 remains dependent on Aditya's real outbox and Jaineel's harness adoption.
This is not an all-domain pipeline or a measured performance result.

## What runs

AnalyticsPipeline in pipelines.curation connects verified Bronze to one supported
schema, CONVERSATION_TURN. It validates with the registered cache, inserts unique
Silver events, applies the pipeline_minute reducer and persists final source
dispositions and export-pending IDs in the same B0 transaction. Same source/hash
is a redelivery no-op; same event/content at a new offset is duplicate_delivery.
Changed event content or conflicting aggregate version takes quarantine. Other
valid event types fail visibly without becoming dirty records.

Capture-only receipts remain ineligible for offsets. ingest_once consumes through
the SDK, captures exact bytes, finalizes SQL, observes its acknowledgement and only
then marks original owned SourceRecords durable and commits the SDK's contiguous
prefix. Any exception requires closing/restarting that consumer; the default worker
exits rather than discarding failed in-flight work and polling past it.

route_dlq uses the caller's analytics transaction and Aditya's append_outbox binding.
It stores an original raw locator/hash/reason plus a registered DlqNotice. Its
savepoint protects callers that catch an append failure. No substitute production
outbox was added. With the current absent library, malformed records remain pending
and offsets do not advance. Explicit SQL outbox doubles exist only in owned tests.

aggregate_gold returns the canonical DirtyPartitionSet and requires an active
caller transaction. Contribution identity and the exact integer unique count are
atomic. The reducer counts each accepted event ID once, including an older event
minute; other reducers and watermark policy are later checkpoints.

## Publication and observations

publish_snapshot takes a single-publisher session lock per namespace and freezes
exact pending IDs/facts in repeatable read. It writes typed Zstandard Silver/Gold
Parquet files, verifies hashes/schemas/counts, reuses untouched logical files and
publishes both complete manifests/pointers in one generation-checked transaction.
Only frozen pending IDs are cleared. A concurrent new event remains pending.
Empty, unpublished datasets raise LookupError; an unchanged existing dataset
returns its current Gold manifest. Compactor candidates remain M08 work.

Immutable lineage lists exact accepted event IDs and original contributing source
coordinates/capture IDs/hashes, not only min/max ranges. It records code commit,
application-lock/dictionary hashes and registered schema hashes. DatasetManifest
input_manifest_ids and source membership refs point to that asset. Full original
envelopes/metadata remain in Silver; raw bytes remain in Bronze. No source origin,
facets, CSV metadata or business values are invented.

The M05 publisher deliberately stops above 10,000 facts or 8 MiB of uncompressed
document text. This bounds its current full-snapshot implementation; incremental
loading/complete publication precedes large W-QUALITY or performance runs. A failed
write or pointer transaction leaves the old active datasets and pending work intact.
Orphans and retired files are retained; there is no automatic cleanup.

Post-COMMIT observations use durable observation_jobs. A failure to journal timing
does not erase committed data. Recovery records a labelled recovery_upper_bound;
no missing timestamp is backfilled as a fast exact commit. Receipt updates append
to a per-namespace ordered journal, so captured but unfinished lower sequence IDs
cannot disappear behind a cursor. A nonempty receipt page returns its last cursor;
an empty page returns null. Repeated source entries expose the latest stage state.
For quarantine pagination, use the last returned quarantine_id as the next cursor.

Readers pin one manifest at query start and hash/schema-check exactly its files.
Gold queries cannot glob the directory or execute caller SQL. pipeline_minute has
no currency dimension; supplying currency is rejected. Other Gold tables and replay
operations return unavailable until implemented, never fabricated rows/jobs.

## Runtime and owner adoption

Use only an analytics connection factory (autocommit=True outside explicit
transactions), FileStore on the Linux named volume, EventCodec with the verified
registry cache, and the actual Git commit:

```python
pipeline = AnalyticsPipeline(connect, store, codec, code_commit=actual_git_commit)
receipt = BronzeCapture(store).ingest_bronze(source_records)
outcome = pipeline.curate_silver(receipt, {"run_id": actual_run_id})
manifest = pipeline.publish_snapshot(namespace)
```

infra.analytics composes existing env commands and applies immutable analytics
migrations 001 and 002. Global db migrate still returns dependency exit 4 until the
other owners/outbox migrations are composed; its evidence identifies the applied
analytics versions. Migration 001 was not rewritten. No other service database is
read or written.

Runtime entrypoints are pipelines.ingestion.runtime:app_from_env (Uvicorn factory)
and python -m pipelines.ingestion.worker. They open nothing on import. Supply
CODE_COMMIT (actual 40-character revision), LAKEHOUSE_ROOT, EVENT_SCHEMA_CACHE_PATH,
INTERNAL_API_TOKEN, RUN_NAMESPACE (dev or isolated bench/replay), RUN_ID and an
analytics URL or analytics password-file binding. .env is not loaded implicitly.
The B0 worker rejects unsupported batch controls instead of silently running O1.
Override the older shared template's local-dev namespace with dev or an isolated
namespace; local-dev does not satisfy the common contract.
It subscribes only to the conversation topic and stops on other conversation types
until M06. Publication is scheduled at 250 ms; slow I/O is not claimed to meet a
hard wall-clock deadline.

infra/compose.analytics.yaml is opt-in alongside the existing base/streaming files.
It reuses the locked Python dependency image from M04, mounts source/cache read-only
and exposes analytics:8006 only on localhost. API and worker each have 384 MiB/0.5
CPU limits; API request concurrency is capped at eight. Start the API with profile
analytics; opt into analytics-worker separately. The current absent outbox keeps
/health/ready at 503 even while valid-event read paths work. /health/live is liveness.
No image build context includes source credentials, .env or raw data.

The API exposes the agreed manifest/Gold/receipt/quarantine paths, bearer-token
authentication for internal operations, common structured errors and /metrics.
Metrics include only observed instance counters/timings. Runtime API SQL gauges
are scoped to RUN_NAMESPACE. Separate worker-process counter collection and full
benchmark lag/resource instrumentation still need harness integration; no zero or
cross-namespace cumulative count is presented as a measured run.

Harsh can pin these manifests later, but candidate publication is not yet supplied.
Jaineel must adopt the provider/receipt cursors and add his independent G1 adapter.
Aditya supplies the actual shared outbox before real invalid-ingress integration.
See [progress](progress.md) for exact commands, failures, test-double distinctions
and final verified source revision.
