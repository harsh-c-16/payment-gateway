# M10 isolated analytical replay

Replay owns analytics rows and immutable files only. It never resets live Kafka
offsets, republishes business events, calls operational APIs, or promotes a target
over a source manifest. Actual operational-service integration and Aditya's real
outbox remain pending; see [progress](progress.md) for executed evidence.

## Entry points and source IDs

- `POST /internal/v1/analytics/replays` returns the existing canonical 202
  `ReplayAccepted`. Supply the internal bearer token and canonical X-Namespace,
  X-Run-ID, X-Correlation-ID and Idempotency-Key headers. X-Namespace identifies
  the selected source, as Jaineel's existing AnalyticsClient expects; the body
  names a separate isolated target. Status uses the existing authenticated GET URL.
- `AnalyticsPipeline.replay_bronze(request)` is the common-spec synchronous
  provider and returns `ReplayJob`. `create_replay`, `get_status`, `run_replay` and
  `pipelines.replay.worker.run_once` provide the durable queue/worker boundary.
- Run the worker with the existing analytics runtime bindings using
  `python -m pipelines.replay.worker`, or the optional `analytics-replay` Compose
  profile in infra/compose.analytics.yaml. It shares the existing 384-MiB/0.5-CPU
  analytics allocation. It is not part of the default low-memory environment.
  No new projectctl command or independent benchmark harness is introduced.

The frozen request contains `source_manifest_ids`, `target_namespace` and
`transform_version`. This provider resolves source IDs against owned SQL records;
arbitrary JSON paths/URLs are not read as source manifests:

1. One published lineage ID from `DatasetManifest.input_manifest_ids` pins the
   paired Silver/Gold generation. Exact accepted source membership is resolved
   through retained ancestry, including compaction generations and membership
   deltas. Only those source records are selected, even when their original
   capture contains other records or newer facts arrive later.
2. One or more `RawBatchReceipt.capture_id` values select original Bronze
   captures, including duplicate and invalid records. All must share one original
   namespace. Capture-only replay has no independent published Gold reference;
   its reconciliation is explicitly null. It must not be reported as semantic
   Gold equality. Use a pinned publication ID for that comparison.

These concrete source-ID bindings are the owned provider handoff for Jaineel to
adopt/review; no public DTO or header/schema was renamed. Mixed publication/capture
selectors and cross-namespace merges are rejected. A transform must be installed
in the executing pipeline; changing a tag alone never installs another transform.

## Durable ownership and original content

Migration 007 stores replay jobs, idempotency bindings, exact source selections
and pinned snapshot references. A new target must be an empty `bench-` or `replay-`
namespace. The target is claimed under the same namespace lock as the sink.
Another request cannot take it over, and normal ingestion into a claimed target
is rejected. Repeating the same request/key returns the same job. A failed job
requires an explicit repeated creation request to queue a retry.

Migration 008 names the key's request namespace explicitly. API keys are scoped to
the caller's source namespace and replay operation; concurrent reuse of one key
for two different targets conflicts under a transaction lock. Library-only calls
without an HTTP namespace retain their target-scoped request-digest bindings.
The source header must match the selected capture/publication namespace.

Workers use a session advisory lock and resume PENDING/RUNNING jobs after process
loss. Code commit, transform, application lock, event dictionaries and verified
schema-ID mapping are fingerprinted. Resuming with a different provider fails
closed; deploy the original pinned provider or evaluate a new target explicitly.
The worker selects jobs for its installed code/transform.

The original capture/receipt and physical files are reused, not regenerated.
Source topics, offsets, keys, ordered headers, raw hashes, original ingress times,
event IDs, original envelope namespace, event/production times and JSON content
remain intact. Effective target namespace is a separate SQL/typed-file key.
Reducers receive an internal namespace projection; the stored original document
and content hash never change. Backfill also respects the effective namespace.

Replay time uses a frozen maximum original ingress from the selected records.
Validation still checks each event against its first durable source ingress, so an
originally future-invalid record does not become valid merely because replay
happens later. Recaptured wrappers retain their own original timestamp/bytes, while
the processing receipt and frozen clock use the source coordinate's first ingress.
A missing/conflicting original source ledger is corruption, not silently omitted
input. Replay clocks/latencies are not live streaming freshness samples.
Publication lineage records the replay ID, source IDs, provider fingerprint,
clock policy and original source namespaces. No cleanup is added: retained source
dedup keys, captures, immutable files and snapshots remain pinned by references
and the existing 30-day/final-acceptance retention policy.

## Equality, failures and repairs

Pinned-reference comparison reads verified source and target Parquet files into
a temporary SQL comparison table. It compares exact canonical logical rows and
framed sorted SHA-256 digests with 4-MiB work_mem; source-file layout and row order
do not affect equality. Event IDs, original content hashes, normalized payloads,
business versions/states, counts, nulls and integer money remain significant.
Processing namespace, publication generation/time, revision and transform labels
are excluded. Both current typed Silver and legacy conversation Silver are read.

`replays/<replay_id>/semantic.json` retains dataset digests, row counts, exact
monetary integrity sums and the canonical reconciliation result. These sums cover
multiple projections; they are not revenue. Up to 1,000 difference examples are
returned with an explicit truncation failure if needed. The frozen DTO's int64
aggregate-money bound can be smaller than valid Gold sums. Such reports fail
closed, retain exact values privately and require coordinated DTO review; no
rounding or unilateral contract widening occurs.

An isolated target can be published before comparison reports a mismatch. Its
job is FAILED and its files remain diagnostic evidence. Source pointers are
never changed. A changed-transform comparison therefore retains explicit old/new
differences instead of calling them equality or automatically promoting data.
This provider comparison does not replace Jaineel's independent workload oracle.

Sink/source dispositions remain transactional and resume through the existing
deduplication path. Repeating a completed replay performs no additional logical
effect or publication generation. Pointer/file failures retain pending progress;
a process exit after pointer commit retains the complete target and recovers
missing post-COMMIT observations with their existing upper-bound marker.

Invalid replay records require the real local `append_outbox` binding and produce
isolated-target DLQ notices referencing original raw bytes. Missing infrastructure
fails the job without becoming an invalid-data reason. Tests explicitly double
the absent outbox. Notification delivery by Aditya's real relay is not established.

Repair annotations require a distinct new event ID when an original ID is known,
a nonempty reason and a source locator in durable quarantine for the original
namespace. The isolated replay validates these annotations. It does not mark the
original quarantine repaired, replace original bytes, run another checkout, or
offer an automatic promotion endpoint. Promotion still needs explicit manifest
review/reconciliation with the affected owners.

Next checkpoint: M11 baseline evidence and controlled batching/scaling experiments.
