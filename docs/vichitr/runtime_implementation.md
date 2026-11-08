# M4 runtime implementation — 8 November 2026

Implementation is available on `vichitr` after integrating main `a76c1df`.
O1/scaling can now be selected in code; this does not freeze B0, establish a
performance improvement or approve an evaluation run. CI workflows are unchanged.

## B0 and O1

`SINK_BATCH_MAX_ROWS=1` selects B0; `100` selects O1. Other values and coercions
are rejected. `SINK_BATCH_MAX_WAIT_MS` remains exactly 50. Both workers request
the same available input bound: up to 100 records over 50 ms. Bronze retains its
2-MiB/50-ms chunk limits. Only sink transaction grouping changes between variants.
The wait bounds collection, not SQL/fsync duration.

Each group atomically commits source dispositions, Silver/Gold changes,
quarantines, notification outbox entries and one `sink_batches` membership/count
audit. A failed group rolls back together. Post-commit observations and metrics
follow the group commit; Kafka durability/offset marks follow successful curation.
Publication checks remain on the 250-ms schedule, including between B0 commits
within a raw capture. Slow operations can miss ticks; no missing timing is invented.

Worker zero is the sole scheduled publisher and starts the existing shared
analytics outbox relay. Other workers ingest only. The relay uses the canonical
25-ms poll/100-row pass and shared acknowledgement logic. Shutdown does not claim
success if its background thread has not joined. Pausing worker zero pauses its
publisher/relay too; the process-level fault receipt is not a claim that only its
Kafka polling was paused. Separate-publisher experiments require a reviewed layout.

## Deployment and scaling

`infra.analytics_deployment.AnalyticsDeployment` generates an ignored, scoped
Compose overlay for 1 partition/1 consumer, 3/1, or 3/3. The caller supplies the
total worker CPU and memory; totals are divided across workers, including integer
memory remainders. Existing infrastructure limits are not increased. An API keeps
its existing constant 384-MiB/0.5-CPU allocation separately from the worker group.
The caller must include that API allocation in the complete SUT resource budget.

Worker IDs are distinct; the shared SDK divides its 2,000-record/16-MiB group
buffer. Sink session concurrency is capped at 12 across workers (12 or 4 each);
worker zero's publisher/relay share a separate cap of two, and the API has a cap
of two. These are bounded live-session limits, not pre-opened connection pools.
Deployment feasibility and final profile allocation remain unmeasured.

Worker Prometheus targets are loopback ports 18060–18062; the separate API is
loopback port 8006. These bindings support serial local runs. `start()` waits for
the API's real readiness; `stop()` stops only that run's named services. It never
uses stack-wide `down`, removes volumes or changes other services.

Fault callbacks accept the canonical consumer-pause, analytics-outage and
kafka-outage targets, at most 30 seconds, only with both `BENCHMARK_MODE=true`
and `FAULT_INJECTION_ENABLED=true` in an isolated namespace. Kafka outages also
require constructing the deployment with `dedicated_stack=True` after reviewing
that the shared broker is dedicated to this run. Recovery runs in `finally`.
Recovery-command acknowledgement is not whole-service recovery acceptance.

## Runner handoff

Use a Linux controller with Docker CLI access and the actual lakehouse volume
mounted at `LAKEHOUSE_ROOT`. `pipeline_from_env()` creates the real owner pipeline.
Supply a separate read-only-role `read_connect` factory; using the writer's handle
for audits is rejected. No credentials belong in an overlay or evidence file.

`pipelines.ingestion.adapters.AnalyticsRunner` can be constructed before a run
exists. Its `owner_callbacks(seed_audit=..., independent_audit=...,
resource_factory=...)` returns the existing `OwnerCallbacks` for Jaineel's
`RuntimeBindings.workloads`. No alternate CLI, oracle or workload registry is added.
Seed audits, independent verdicts, reviewed resource collectors and owner review
files remain actual team inputs; this provider does not fabricate them.

- `fresh_namespace(context)`: refuses existing SQL, files and Kafka topics,
  applies analytics migrations, provisions the requested topology and starts the
  scoped worker/API deployment. Its acknowledgement covers analytics only; merge
  operational fresh-storage proofs in the team composition.
- `drain(context, remaining_seconds)`: requires complete Kafka lag observations,
  no undecided/unpublished valid sources, no pending export and no unpublished
  analytics notification outbox. Missing offsets never count as zero.
- `sources_factory(context)`: existing read-only `QualitySources` exports with
  all declared Gold tables supported. `export(context, directory)` writes raw
  evidence, including exact Bronze, source/quarantine/Silver, pinned Gold,
  membership, sink audits and offsets; the independent harness computes verdicts.
- `owner_callbacks(...).observer_factory`: real worker Prometheus, Kafka lag,
  pinned Gold and the caller's actual SUT resource collectors. Clock sharing is
  not assumed. API and worker metric registries remain separate.
- `stop(context)`: call in the deployment composition's `finally`, including
  failed setup/validation/measurement, before beginning the next serial run.

W-PIPE input topics are known. Quality callbacks use the harness's
`quality_topics`; business integrations must explicitly supply `analytics_topics`.
The runner refuses changed namespace/run IDs or parameters after allocation.
Quality can reuse `fresh_namespace`/`sources_factory` in `QualityOwners`; its seed,
collector, cache/registry/broker and reviewed mapping inputs remain explicit.

Global migration composition uses `infra.analytics.migrate_action` as the
`analytics` participant of Jaineel's `MigrationCoordinator`. It returns success
for this database alone. The legacy standalone `infra.analytics` entry point
continues to report global incompleteness instead of claiming all databases ran.

For explicit cleanup, `runner.for_run(context).reset_participant` is the owner-local
reset participant for a reviewed global coordinator. It requires the original
run context, stopped deployment/readers, final evaluation acceptance, expired
30-day source/manifest retention, no replay pins and no unpublished/retained
outbox rows. It deletes only namespace-scoped analytics rows, transactionally,
while holding sink/publication/replay guards. Immutable files remain retained;
Kafka topics/offsets, other owner databases and evidence are untouched. Start
subsequent experiments with a new namespace, not by reusing old Kafka offsets.

## Verification limits

Focused offline checks exercise batch membership/rollback and offset gating,
fixed resource division, context isolation, fault guards/recovery, reset refusal,
missing-lag drain behavior and shared-relay wiring with explicit doubles.
No Docker stack, real reset, benchmark or live O1/scaling acceptance was run in
this implementation pass. The existing CI upload-permission defect is unchanged.
