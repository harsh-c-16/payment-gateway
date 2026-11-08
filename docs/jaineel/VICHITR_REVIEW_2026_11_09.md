# Vichitr merge review and evaluation handoff

9 November 2026. Jaineel's harness checkpoint, based on `6e1e633` (PR #12).
The initial implementation pass ran no evaluations, Docker startup or reset.
The later authorized review/push is recorded in `docs/jaineel/progress.md`;
copyable teammate messages are in `docs/jaineel/TEAM_MESSAGES_2026_11_09.md`.
The existing local edit in `.github/workflows/offline.yml` is retained.

## What the pulled changes do

| Commit | Change and implication |
|---|---|
| `7a31a4e` | B0/O1 transaction grouping and bounded 1/1, 3/1, 3/3 deployments. All consumers share a fixed group budget; worker zero publishes Gold and runs the shared analytics outbox relay. Owner-local reset preserves retention and replay guards. |
| `33e6b68` | Consumer-only pause with a lease, lazy concrete `infra.analytics_runtime`, restricted audit roles, cgroup readers and cleanup forwarding. It connects real exports to the independent harness; registration does not establish readiness. |
| `5b5c171` | Catalogue API, projection worker and shared outbox relay are separate processes. Resource targets can list all three containers. Broker conflict/rebalance/process-death coverage and an isolated Compose round trip are recorded in Vichitr's progress. |
| `7c1ab54` | Safe bounded startup retry/journaling and retained-broker recovery. Kafka's heap becomes 512 MiB within its unchanged 1,024 MiB container; health/startup budgets accommodate the observed cold start. No offsets/volumes are deleted. |
| `d53e633` | Explicit worker test doubles accept the current allocation arguments and capture bound. This corrects test fixtures rather than changing production sink batching. |

Read [Vichitr's evidence and limitations](../vichitr/progress.md) and
[runtime deployment contract](../vichitr/runtime_implementation.md). Their earlier
passes are historical provider evidence, not a new full-team integration or
benchmark pass on this checkout.

## Changes made in this checkpoint

- `projectctl.provider_validation` executes public export/signature, event
  manifest/schema and catalogue schema/dictionary checks. `contracts check`
  consumes `PROJECTCTL_CONTRACT_REVIEW_PATH`; a matching affected-owner review
  changes a validated surface to PASS. Missing reviews remain UNREVIEWED, stale
  receipts and broken validators fail. Pure compatibility is separately visible
  as `validation=PASS`; it does not assert live durability or G0 completion.
- `projectctl.team_runtime` composes M4 with explicitly named operational runtime
  modules through `PROJECTCTL_OWNER_RUNTIME_MODULES`. Duplicate callbacks fail.
  `RuntimeBindings.migrations` and `.resets` carry owner-local participants.
  Global migration checks all six registrations before work. Global reset checks
  all registrations and all read-only preflights before any apply callback.
  Cross-database reset is not atomic; an apply failure records completed stages.
- G1 now receives dataset/resource context, exposes a module CLI, and invokes
  cleanup after setup failure as well as normal completion. Quality topics and
  selected SKU provenance are available before deployment callbacks execute.
- W-PIPE reconciliation rejects wrong export run IDs, omitted/repeated offers,
  reused broker coordinates, unexpected/duplicate Bronze rows and altered event
  time. Expectations still come from the plan and emitted wire bytes.
- Live M4 audits now retain expected/observed mappings and the actual source
  mapping review. Saved performance validation uses `analytics_recheck` to
  rebuild W-PIPE/W-QUALITY verdicts from raw files and the same independent
  oracle, rather than trusting a saved PASS. Generic transaction/import/query
  audit review behavior is retained. New mapping code must appear in the review.
- `projectctl.evaluation_packet` prepares and verifies exact input pins,
  five available workload recipes, proposed review records and a complete
  integration-registration inventory. It starts nothing and never writes owner
  approvals. Candidate configs remain draft/planned.

## Evaluation profile decision

The official full matrix should use one **integrated-linux9c8g** profile on a
dedicated Linux Docker host, SSD, at least 12 logical CPUs and 32 GiB RAM.
The machine identity remains to be supplied by the teammate executing it.
This is a capacity proposal, not measured feasibility or enforced allocation.

The process inventory in [evaluation_profiles.json](../../configs/evaluation_profiles.json)
counts 8.25 allocated CPU cores and 7,808 MiB inside a 9-core/8,192-MiB SUT cap:
PostgreSQL, Kafka, registry; analytics API and consumer group; catalogue
API/worker/relay; conversation API/relay; Orders API with saga thread plus relay;
Inventory API with expiry thread plus relay; Payments API plus relay.
Generator/observer gets a separately reported 1 core/1,024 MiB. Publisher and
analytics relay threads are included in worker zero's process allocation.

The separate **pipeline-linux4c4g** profile allocates 3.75 cores/4,096 MiB,
including analytics API 0.5 core/384 MiB and worker group 1.5 cores/1,536 MiB.
P33 splits the group into three 0.5-core/512-MiB workers. Use this only for a
separately labelled pipeline study; its configs reject integrated variants.
Do not combine its runs with integrated-profile comparator runs.

The laptop inspected here has 16,802,910,208 bytes physical RAM and 12 logical
CPUs; the observed free memory was 867,056 KiB. No final evaluation is run here.
The old `local4c8g` draft remains historical; its catalogue and analytics
allocations do not account for the newly separate processes. Replacing it with
the counted proposed profiles does not claim the unchanged infrastructure has
already enforced those profiles.

## Mapping review and remaining integrations

| Evidence | Mapping and independent check |
|---|---|
| Planned workload and emissions | Frozen logical IDs, scheduled timestamps, wire hashes and acknowledged broker coordinates; not inferred from sink counts. |
| Bronze and receipts | Exact key/value/ordered headers against wire; one final disposition per coordinate, namespace/run scope, no extra physical records. |
| Silver | Exact event IDs/content hashes and payload fields; unrelated Arrow struct fields must remain null. No cleaner/reducer import in the oracle. |
| Gold | Pinned generation/query generation, manifest hash, membership IDs, per-minute totals and paired Silver/Gold lineage references. Source file readers verify files; paired lineage agreement is not a separate proof of every lineage document's contents. |
| Quality | Independent 100,000-record recipe: 98,500 unique valid, 1,000 physical duplicates, 500 invalid; exact dispositions/quarantine, sink-batch membership and drained offsets. G1 is three records and never substitutes for T-03. |
| Operational data | Existing G3/reconciliation contracts need reviewed snapshots of orders, holds, signed ledgers, stock, original producer envelopes and broker acknowledgements. M4-only setup does not prove fresh operational databases. |

The concrete seed audit currently proves counts, uniform initial values and a
matching catalogue revision/run; it does not independently compare the complete
Inventory SKU key set with the pinned SKU manifest. Aditya/Jaineel must include
that exact membership check in the reviewed operational seed binding before
qualification. A count of 19,920 alone cannot establish that they are the same SKUs.

`integration_inventory.json` lists every remaining D/T/G case and whether its
real callback is registered. The M4 runtime provides W-PIPE and quality callbacks;
it does **not** register general `smoke/G1`, `T-03/quality`, G3 or remaining
`CaseBinding` entries. The separate G1 CLI is available, while generic suite
cases remain explicit NOT_RUN until their reviewed bindings exist. Do not turn
the provider pytest results into those case receipts.

Missing global migration participants are Orders, Inventory and Payments.
Their owner must expose migration callbacks; this checkpoint does not implement
a second migration engine from their SQL. Owner-local reset preflights/apply
callbacks are still required for all six databases. M4's existing apply helper
requires the original deployment context, stopped writers/readers, accepted
evaluation, elapsed retention and no replay/outbox pins. It is not safe to infer
those facts from a namespace string. No reset is necessary to begin fresh runs.

The teammate instructions are [EVALUATION_TEAMMATE_RUNBOOK.md](EVALUATION_TEAMMATE_RUNBOOK.md).
Harsh's input decisions are [HARSH_REVIEW_2026_11_09.md](HARSH_REVIEW_2026_11_09.md).
