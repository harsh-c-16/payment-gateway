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
success if its background thread has not joined. Consumer-pause now pauses only
worker zero's Kafka fetch/application intake; heartbeat polling, scheduled
publication and the independent relay continue. The owner-thread SDK pause
survives partition assignment. Private request/ack files carry exact run identity
and a maximum 30-second lease, so a lost controller cannot leave intake paused.
Both benchmark/fault flags must be enabled inside the worker container.

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
The concrete M4 composition is now available as described below.

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
- `stop(context)`: connected through the optional shared `cleanup` callback,
  after observer teardown on success, setup failure or cancellation. Cleanup
  also runs when earlier teardown fails; failures remain visible. It stops only
  staged services and never creates a deployment just to clean it up.

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

## Concrete M4 runtime

Select `PROJECTCTL_ADAPTER_MODULE=projectctl.jaineel` and
`PROJECTCTL_RUNTIME_MODULE=infra.analytics_runtime`. Registration is lazy and
starts nothing. This module supplies real W-PIPE and W-QUALITY/G1 analytics
callbacks using Jaineel's existing workload, source exporter, observer and
independent reconciliation. It does not register other owners' workloads/G3 or
pretend partial migrations/resets are global success. W-PIPE expectations derive
from the frozen plan and acknowledged wire bytes; receipts, exact Bronze,
Silver payloads/hashes, Gold minute counts, membership and paired lineage are
checked without invoking reducers or operational mutations.

Use a Linux controller with Docker CLI, the real lakehouse volume and the current
locked application image. Local `env up --profile streaming-local` now provisions
SELECT-only audit roles for analytics, catalogue and inventory, grants current
and owner-created future tables, and stores generated secrets under the existing
ignored `artifacts/infra/postgres-local/secrets/` plus private `audit.env`.
Existing credentials are never rotated automatically. Default read-only mode
alone is insufficient: runtime rejects table write privileges. Optional
`*_AUDIT_DATABASE_URL` overrides support explicit remote connection placement;
local fallback URLs address host loopback and are not container DNS addresses.

Before a live run, supply these actual deployment inputs:

- `M4_SEED_NAMESPACE`: an already seeded isolated benchmark namespace with the
  actual pinned catalogue revision, all 19,920 stock rows at 10,000/0/version 1,
  one original seed run ID and a drained outbox/projection. The runtime reads
  proof; it does not seed or change operational tables.
- `ANALYTICS_BINDING_REVIEW_PATH`: a real affected-owner review pinned to current
  source hashes. Include the existing quality mapping references plus
  `benchmarks/pipeline_audit.py`, `infra/analytics_runtime.py`,
  `infra/analytics_resources.py` and `pipelines/ingestion/adapters.py`.
  No approval document is generated by the runtime.
- A feasible reviewed/frozen resource profile, actual clean `CODE_COMMIT`, schema
  cache/registry/broker addresses, service token and normal private writer binding.
  Docker collectors inspect real limits and cgroup counters; missing readings
  remain missing. CPU/RAM totals must match every declared service allocation.
- `PROJECTCTL_SUT_CONTAINERS`: JSON service-name-to-actual-Docker-ID overrides
  for other SUT services outside the shared Compose project. Analytics containers
  come only from the scoped deployment; duplicate cgroups are rejected.

The current draft `local4c8g` evaluation profile is not verified feasible on this
machine. Its analytics allocation also omits the separately allocated API when
combined with its worker-group total. The runtime refuses that mismatch. This
change neither raises Docker RAM nor rewrites the canonical profile. Live runs
need a consistent feasible profile first.

## Small CI artifact fix

Main's run `42477036723` passed the native tests and then failed uploading
artifacts: the host could not scan Docker-created private pytest directories at
`artifacts/ci-volume/tmp`. `verify_prompt6.py` now puts pytest scratch data in a
sibling `<out-name>-pytest-tmp` directory, outside recursive report uploads.
Reports/XML/logs remain in the original output folder. Workflows and test
selection are unchanged; the fix was made on `vichitr` without pulling a teammate
branch.

## Verification limits

Focused offline checks exercise batch membership/rollback and offset gating,
fixed resource division, context isolation, fault guards/recovery, reset refusal,
missing-lag drain behavior and shared-relay wiring with explicit doubles.
No Docker stack, real reset, benchmark or live O1/scaling acceptance was run in
this implementation pass. The upload-path regression is covered offline; a new
GitHub native job is still required to confirm the permission fix on its runner.
