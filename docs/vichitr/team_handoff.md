# M4 integration handoff and remaining gates

10 November recovery follow-up: **initial catch-up is now complete**. All 19,920
seed SKUs are projected, zero deferred; all 19,920 stock events reached Gold.
At 10:53:10 UTC all five business-topic lags, unfinished receipts, pending exports
and analytics notifications were zero (Silver/Gold generation 269). The public
Gold API later returned HTTP 200, generation 273, with stock counts
11,000 + 8,920 = 19,920. Development workers now have bounded `on-failure:3`
restarts after the real stock-worker connection-timeout exit. Normal prototype
resource verification passed after restoring the temporary bootstrap CPU cap.

**Current demo blocker for Harsh/Jaineel:** real `POST /v1/search` still returns
503 `STORAGE_UNAVAILABLE` after drain. PostgreSQL logs identify a two-second
statement timeout on the eligible-product count joining `products` and
`stock_projection`. The text turn returns `dependency_error` and no products;
cart, quote and checkout were not reached. A temporary PostgreSQL CPU increase
did not make the structured HTTP attempt succeed and was reverted. Separate
read-only execution plans under both audit and catalogue roles use a hash join
and finish below two seconds, so the exact difference in the HTTP execution
context remains unresolved. Harsh should review the real request/SQL path;
Jaineel should recheck the turn once search succeeds. No deadline, catalogue
logic or query assertions were changed. Raw local attempts and plans are in
`artifacts/prototype-recovery-20261110/`; see [progress](progress.md).

10 November prototype update: [prototype-local](../../infra/PROTOTYPE.md) now
starts/verifies the six APIs, stock/analytics workers and real operational relays
inside 3.5 GiB of container limits on the current 8-CPU Docker VM. Linux import,
verification and stock seeding used the existing owner implementations; all
19,920 seed rows reached broker acknowledgement. Initial stock/analytics catch-up
and M1's three-second turn deadline still prevent claiming a complete checkout
demo. See the current [progress evidence](progress.md). This development launcher
does not satisfy the separate proposed evaluation profiles or runtime-case gates.

8 November startup follow-up: Windows setup/verification now retains per-stage,
credential-free attempt diagnostics and retries transient failures in repeatable
probes/provisioning at most three times. A real retained-volume startup exposed
Kafka Java heap exhaustion after loading 497 partitions. The development heap
ceiling is now 512 MiB inside the unchanged 1,024-MiB Kafka container; container
and VM limits, data and offsets are preserved. Cold-start health budgets now
allow retained-log recovery. See [startup instructions](../../infra/STREAMING.md)
and [progress](progress.md) for exact commands and actual verification outcomes.
Historical connection/read failures remain recorded; their original causes were
not captured precisely enough to attribute retrospectively.

8 November follow-up on `vichitr`: catalogue shared-relay wiring, live Compose
API/stock-worker/relay acceptance and all four real-broker projection fault
cases are now implemented/verified. The evidence-path portability bug is fixed;
the missing-outbox fixture was already fixed. Resource accounting now includes
multiple process containers per service. See the latest [progress](progress.md)
for 45 passing focused cases, three real audit-role checks and startup limits.
No image download is needed: spec 08 requires preserving image URLs and prohibits
downloads during ingestion. Cold-query `NOT_RUN` handling and catalogue outbox
migration 005 are delivered; older handoff requests for those are stale.

Updated 8 November 2026, incorporating main `a76c1df` and the remaining M4
implementation. [Runtime implementation](runtime_implementation.md) describes O1,
scaling, lifecycle/evidence callbacks, notification relay and guarded cleanup.
These are implemented, including consumer-only pause, concrete M4 runtime
composition and guaranteed teardown. Live acceptance/measurement, actual
credentials/resource/review inputs and other owners' runtime composition remain
pending. Historical module
notes describe their own checkpoints; use this file, the current implementation
plan and canonical specs for remaining work. Evidence/source pins are in
[progress](progress.md) and [test skips](test_skips.md). No owner approval,
full-business integration or performance result is implied by a local pass.

Local actual-data acceptance passed for **19,920 active SKUs**, including real
outbox/Kafka, catalogue stock projection, Bronze/Silver/Gold, full repeated replay
and logical-equivalent compaction. Source and replay snapshots use isolated QA
namespaces. The local ignored `artifacts/integration-20261106/context.json`
identifies the inventory/analytics schemas; the Linux volume root is
`/lakehouse/vichitr-integration-20261106`. Catalogue rows are namespace-scoped in
`catalog_db`. The normal analytics schema also has migrations 1–10 applied.

**Operational evidence:** the 6 November local Desktop restart/timeouts remain
historical local limitations. Upstream main's 8 November CI passed native
Kafka/registry/PostgreSQL/volume test steps; its final failure was artifact upload
permissions on `artifacts/ci-volume/tmp`. The small verifier fix now places
pytest scratch data outside the upload folder; workflows/test selection remain
unchanged. No Docker startup or live O1/scaling acceptance is claimed. The 100,000-packet result below
remains wire-only.

## What is available

| Provider | Actual binding |
|---|---|
| M4 runner | `PROJECTCTL_RUNTIME_MODULE=infra.analytics_runtime` with `projectctl.jaineel`: concrete W-PIPE and W-QUALITY/G1 callbacks, read-only SQL, Docker cgroup collectors and post-observer cleanup. See runtime handoff for required live inputs and profile mismatch. |
| Infrastructure | `PROJECTCTL_ADAPTER_MODULE=infra.analytics`; `projectctl env up --profile streaming-local`, `projectctl env verify --profile streaming-local`, `projectctl env down`. PostgreSQL/Kafka/registry/file volume and registered current/historical schemas. |
| Analytics schema | `projectctl db migrate --namespace bench-...` applies analytics migrations 1–10, including the real shared outbox table. Global command still reports dependency exit 4 until other database migration dispatch is composed. |
| Producer SDK | `shared.event_transport`: configure registered schema cache/source service, build/validate immutable events, publish with real broker acknowledgement. README documents exact keyword calls and fixed settings. |
| Consumer SDK | Long-lived owner-thread `ConsumerGroup`; validate and durably process before `mark_durable`, then commit only the contiguous prefix. `buffer_snapshot()` is read-only. |
| Diagnostics | `shared.local_diagnostics` and curation quarantine bind to the caller's real `append_outbox(tx,event)` and transaction; missing binding fails closed. No substitute production outbox. |
| Analytics HTTP | `pipelines.ingestion.runtime:app_from_env`; `contracts/http/analytics.yaml` defines manifest, Gold query, receipts, replay creation/status and quarantine inspection. Internal endpoints require the shared token and canonical request context. |
| Immutable snapshots | `AnalyticsPipeline.publish_snapshot`, active manifest/query readers and `publish_candidate`. Read only manifest-listed files; compactor writes candidate files and submits a pinned candidate. |
| Replay | `pipelines.replay.jobs.create_replay/get_status/run_replay`; optional `pipelines.replay.worker`. Source capture/lineage IDs, immutable bytes and isolated effective namespace are preserved. See M10 notes for source-versus-target request context. |
| Sink audit | `read_sink_batches(connect, namespace, run_id, after=0, limit=1000)`. Export after drain; retain missing timers and source identity. |
| Worker observations | Internal `http://analytics-worker:8006/metrics` for the worker registry; JSON `consumer_buffer` stdout records for application queue state/limits/peaks/pauses. The API's registry is separate. |

Normal startup uses the locked application image and explicit runtime variables
from `infra/compose.analytics.yaml`. API/worker profiles are opt-in and each
retains its existing 384-MiB/0.5-CPU allocation. Use actual `CODE_COMMIT`, schema
cache path, namespace/run identity and credentials from the local secret binding.
Do not copy passwords into source, run manifests or team messages.

The development stack keeps PostgreSQL 512 MiB, Kafka 1,024 MiB and registry
640 MiB (2,176 MiB total). QA checker/rehearsal allocations are separate correctness
resources, not a benchmark resource profile. No eight-GiB VM allocation is needed
for these standalone checks; integrated benchmark feasibility is still unmeasured.

## Exact remaining inputs

| Owner | Required input/adoption | Work unlocked |
|---|---|---|
| Harsh | Review/adopt the locally generated actual CSV artifacts and facet mapping | The importer is available: 19,998 listings /19,920 active SKUs were loaded into an isolated benchmark namespace. Manifest and source/archive hashes are retained locally; these are no longer missing implementations. |
| Aditya | Adopt the small relay-ordering correction and compose owner-local migration/reset/startup callbacks; review whole-service recovery | Inventory/Orders/Payments SQL already includes diagnostic/outbox tables. Actual inventory seed and relay integration ran locally; analytics installs its own real outbox. The new guard prevents later aggregate versions overtaking a failed head. |
| Jaineel | Adopt/review `pipelines.ingestion.quality.QualityMaterializer`, bind its explicit raw-fixture publisher and independent oracle; compose real lifecycle/observer callbacks using receipts, pinned visibility, sink audit and existing collectors | Full 100,000-record T-03, complete baseline trace and independently calculated measurements. The pure SDK materializer now exists; normal publisher validation remains strict. See [binding details](m11_baseline_handoff.md#quality-wire-handoff--6-november-2026). |
| Harsh + Aditya | Start/review actual service APIs and their audit/lifecycle bindings for the runner; Harsh has included the shared outbox template in catalogue migration 005 | Catalogue outbox migration 005 is now merged. The actual CSV and stock-projection path passed; catalogue event-producing mutations and whole checkout require this local table and owner composition. |
| Harsh + Jaineel | Actual cold-storage measurements require a platform exposing `/proc/self/io` | The missing-counter handling is implemented: `--cold` records `NOT_RUN` with a reason and retains warm results. No additional crash-handling implementation is requested from Harsh. |
| Affected DTO owners | Review oversized aggregate-money representation | Exact private sums/fail-closed DTO limits are retained. The money-type reason conflict is resolved with user approval: `INVALID_TYPE` for wrong types; `INVALID_AMOUNT` for invalid integer amounts. The independent fixture is unchanged. |
| All database owners + Jaineel | Owner-local reset callbacks and quiescence/lifecycle composition | Complete global `env reset`/migration dispatch. The M4 guarded reset participant now exists; the global coordinator must compose other owners and stop all readers/writers. |

Merged main `f488f637c6a6578188cff53594f2ea6c9f63af4e` contains the actual
catalogue, operational services, shared outbox and compactor implementations.
Their presence unlocks real integration; it does not establish full-business
acceptance or supply the reviewed benchmark lifecycle/observer/oracle binding.

`env reset` must coordinate owner databases and idle workers, preserve unrelated
namespaces, and account for replay references to source captures/snapshots. M4
cannot delete another service's tables or invent its reset API. No partial
destructive cleanup is registered as global success, and no automatic file GC or
volume deletion is added. Normal `env down` retains all volumes.

## Buffer observation semantics for the collector

Call `buffer_snapshot()` on the consumer's creating thread. The worker does this
on fixed one-second loop deadlines and before closing each handle. It skips
missed ticks rather than inventing samples; slow SQL/publication can therefore
leave gaps. Raw JSON includes UTC observation time, run/namespace/group/handle
identity, queue counts/bytes, configured limits and lifetime counters.

Pending records include handed-out records until offset acknowledgement or
ownership loss; `mark_durable` alone does not release memory. `fetch_paused` is
the current SDK pause state; `pause_required` is its existing headroom threshold.
Peaks and pause/overflow counts survive drain/rebalance for that handle, then
reset under a new `consumer_instance`. A rejected oversized source is an overflow
attempt, not a fabricated admitted or quarantined record.

Bytes count original key/value/header bytes in the application ledger. Native
queue/fetch limits are configuration, not observed native occupancy or total RSS.
Collect actual container/process resources separately. Per-worker lifetime peaks
are not simultaneous group peaks. Keep raw identity out of Prometheus labels.
The log sampling interval is not an event latency or a publication SLO.

Worker metrics are reachable by a collector on its Compose network. A host-only
collector needs an agreed loopback mapping/network placement. No automatic host
discovery or new shared metric vocabulary is supplied. Counter resets on worker
restart are expected; durable source/transaction/manifest records remain the
authority for cross-restart reconciliation.

## Order once inputs arrive

1. Adopt/review actual providers and mappings; compose migrations and readiness.
2. Run applicable T-01/T-03/T-07/T-12 with the independent full fixture and actual
   dependencies. Keep all failed/raw evidence and unresolved cohorts visible.
3. Freeze a correct B0 commit/config/resource budget. Collect the initial trace
   and identify where backlog/time accumulates.
4. Close live correctness for the implemented O1 (100 rows or 50 ms) with identical raw capture,
   producer settings, validation, durability and 250-ms publication cadence.
5. Run the three paired comparisons through Jaineel's runner, then P10/P30/P33,
   skew, stress and integrated recovery trials with fixed total worker resources.

O1/scaling implementation is now available. Live verification and performance
evidence remain Vichitr work after the ordered correctness/baseline gates close. Independent readiness does not mark
M11/M12 or whole-team G0–G6 complete. Neutral/negative measured results remain valid.
