# M4 integration handoff and remaining gates

This is the current handoff after independent readiness work. Historical module
notes describe their own checkpoints; use this file, the current implementation
plan and canonical specs for remaining work. Evidence/source pins are in
[progress](progress.md) and [test skips](test_skips.md). No owner approval,
full-business integration or performance result is implied by a local pass.

## What is available

| Provider | Actual binding |
|---|---|
| Infrastructure | `PROJECTCTL_ADAPTER_MODULE=infra.analytics`; `projectctl env up --profile streaming-local`, `projectctl env verify --profile streaming-local`, `projectctl env down`. PostgreSQL/Kafka/registry/file volume and registered current/historical schemas. |
| Analytics schema | `projectctl db migrate --namespace bench-...` applies analytics migrations 1–9. Global command still reports dependency exit 4 until other database/outbox migration dispatch is composed. |
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
| Harsh | Real active-SKU/catalogue manifest, dataset/rules/dictionary hashes and reviewed facet values | Actual workload materialization and full independent W-QUALITY; no guessed SKU population or facets. |
| Aditya | Real `append_outbox`/relay, caller-local migrations and retained recovery behavior | Actual invalid-source/DLQ integration, whole-service readiness and relay portion of T-07. Current notification checks label their doubles. |
| Jaineel | Reviewed fixture-to-SDK binding and independent oracle; real runner/observer factory using receipts, pinned visibility, sink audit, worker logs/metrics and existing lag/resource readers | Full 100,000-record T-03, complete baseline trace and independently calculated measurements. Do not replace his collectors or oracle. |
| Harsh + Aditya | Actual catalogue/transaction/projection APIs, seed controls and audit exports | Search-to-checkout-to-Gold G3/G4/T-11 integration and operational invariant checks. |
| Harsh | Actual `compact_snapshot` candidate generator and query benchmark | Real T-04/compactor adoption; M4 already verifies stale generations, row/content equivalence and pointer safety. |
| Affected DTO/fixture owners | Review oversized aggregate-money representation and the `wrong_money_type` reason mapping (`INVALID_AMOUNT` provider versus `INVALID_TYPE` fixture expectation) | Shared edge-case agreement. Existing exact private sums/fail-closed DTO limits are retained; no oracle or common DTO is silently widened. |
| All database owners + Jaineel | Owner-local reset callbacks and quiescence/lifecycle composition | Complete global `env reset`/migration dispatch. The reset adapter is currently absent; CLI namespace guards alone are not cleanup. |

The latest fetched `origin/main` was inspected during this checkpoint. The
outbox, catalogue, operational services and compactor paths contain scaffolding
READMEs there; this does not assert that teammates have no work on other branches.
Exact inspected revision/paths are retained in local dependency evidence.

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
4. Implement/correctness-test O1 (100 rows or 50 ms) with identical raw capture,
   producer settings, validation, durability and 250-ms publication cadence.
5. Run the three paired comparisons through Jaineel's runner, then P10/P30/P33,
   skew, stress and integrated recovery trials with fixed total worker resources.

O1/scaling implementation and performance evidence remain Vichitr work after
the ordered correctness/baseline gates close. Independent readiness does not mark
M11/M12 or whole-team G0–G6 complete. Neutral/negative measured results remain valid.
