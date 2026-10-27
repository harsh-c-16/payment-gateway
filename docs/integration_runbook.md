# Jaineel P8 integration checkpoint

The normative commands and assertions remain in [runbook §§2–4](specs/09_EVALUATION_RUNBOOK.md),
[evaluation §§7/9](specs/03_EVALUATION_SPEC.md), and
[common §§8–12/15](specs/02_COMMON_SPEC.md). This document describes the harness
binding and the handoffs still needed to execute them. P9 is not part of this checkpoint.

The current checkout has only M1 and the harness. Catalogue, transaction,
transport, outbox and analytics implementations/contracts are absent. PostgreSQL
alone cannot complete G1/G3 or prove Kafka recovery. The real gates remain
**INCOMPLETE**, with individual unavailable cases **NOT_RUN**. Unit tests use
explicit doubles; they do not establish real integration success.

## Execute and inspect

Use the locked Python 3.11 environment:

```powershell
uv sync --locked
.venv/Scripts/python.exe -m benchmarks.manual.verify_p8 --out artifacts/p8/NEW_RUN --database-file PATH_TO_LOCAL_DATABASE_JSON
```

Replace `NEW_RUN` with a new directory and `PATH_TO_LOCAL_DATABASE_JSON` with the
ignored local database record emitted by the existing Docker test setup. Its
`url` is used only in the subprocess environment, never recorded in command logs.
The verifier confirms it identifies Docker PostgreSQL 18 with durability enabled.
Without this option, database tests visibly skip and the harness checkpoint fails.
The verifier neither resets existing databases nor substitutes domain providers.

The verifier retains command arguments, exit codes, stdout/stderr, JUnit,
independent source checks and the contract inventory. It attempts setup in the
canonical order. After the first failed prerequisite, dependent setup remains
NOT_RUN; independent contracts and the four P8 evaluation commands still run.
Exit 4 means missing real handoffs/evidence, even when all harness tests pass.

Each `eval run` output names its `evidence_dir`. Inspect its `case_plan.json`,
`tests.jsonl`, `correctness.json`, `summary.json` and `manifest.json`. Cases are
expanded from `benchmarks/integration_cases.py`, including separate T-11 targets.
Aliases deduplicate overlapping cases. Direct performance IDs remain unavailable
until their measurement adapters are supplied; no performance work is attempted.

Recheck saved P8 evidence without calling a provider or changing the original:

```powershell
.venv/Scripts/python.exe -m projectctl benchmark reconcile --run-dir EVIDENCE_DIR_FROM_EVAL_OUTPUT
```

This checks saved hashes, frozen independent fixtures, active Gold membership and
generations, signed ledgers, immutable quotes and inventory conservation. It writes
a fresh evidence directory. Missing original cases stay incomplete; reconciliation
does not retrospectively turn an unexecuted fault test into a pass.

For `benchmark run` evidence, the reviewed audit adapter must preserve independent
`expected.json` and read-only `observed.json` projections, indexed in that run's
artifact manifest; real mode also needs the approved `binding_review.json`.
Reconciliation refuses missing projections or an audit from another namespace.

## Explicit production composition

`PROJECTCTL_ADAPTER_MODULE` optionally names an importable composition module with
`register(registry)`. This is an explicit local executable-code selection. There is
no automatic discovery or fallback. Registration errors become dependency evidence.
The production CLI rejects any `CaseBinding(mode="stub", ...)` before preparation.
The unit-test-only `run_cases(..., allow_test_doubles=True)` entry point labels its
results and cannot declare a real integration pass.

Register each available case using `registry.register_case(case_id, CaseBinding(...))`.
Bindings are Jaineel-owned consumer adapters using reviewed public APIs, SDKs and
owner audit exports. `benchmarks.integration_clients.ConversationHTTP` implements
the M1 HTTP surface required by `IntegratedDriver`, validates the owned OpenAPI
contract, preserves identity/confirmation and makes no hidden mutation retries.
Existing catalogue, Orders and analytics HTTP clients continue using owner schemas.
Missing provider DTOs are not inferred from consumer fixtures.

`CaseBinding` requires a fixture path and three async callbacks:

1. `prepare(context)` creates a fresh case namespace, acknowledges it with
   `created_new=true`, and returns verified setup proof. Real cases require actual
   PostgreSQL/Kafka, frozen environment, verified source/import/active-SKU manifests,
   simulator seed and all 19,920 initial stock projections. Benchmark/fault controls
   must be enabled in this isolated namespace.
2. `exercise(context, fixture, fault_gate)` drives the frozen scenario through
   public interfaces. It retains actual requests/responses, broker coordinates,
   audit snapshots, observer journals and manifest references in `context.directory`.
   Fixture expectations are saved before this callback, and passed as a copy.
   Integrated tests must let actual simulated transactions produce domain events.
3. `audit(context)` reads owner-approved namespace-scoped snapshots. It does not
   receive the expected answer. It returns `namespace`, `run_id`, `case_id`,
   `collection_complete`, `facts`, and (for reconciliation cases) `audit` in the
   existing independent oracle projection. These are **harness projections**, not
   new public service DTOs. Their mappings need owner review before real execution.

`facts` contains the independently collected scenario observations named in the
frozen case checks; it must not contain precomputed pass flags substituted for
observations. Raw audit/receipt evidence must substantiate them. G1 additionally
requires `bronze` physical record IDs/hashes/coordinates and `quarantine` record IDs;
the harness verifies exact archived hashes and physical versus logical effects.
G3 requires the public `workflow` trace through search/cart/quote/confirmation/
checkout/order/projection/Gold, bound quote/cart identities and a nonempty signed
transaction audit. The oracle detects wrong totals, missing IDs, duplicate effects,
false visibility, namespace mismatches and unresolved finality independently.

The immutable fixture JSON contains `case_id`, nonempty `input`, and `expected`
for the oracle. Author expected event/quote/stock/Gold values before execution;
do not derive them from the provider output. G1 also freezes
`expected.bronze_sha256` keyed by physical record ID. Do not use the small unit-test
evidence double as a real catalogue or transaction fixture.

Generated order/quote/session IDs need not be predictable. A fixture may declare
`@id:NAME` tokens; `exercise` can return `identities` mapping these tokens to the
actual captured UUIDs. For transaction-generated source events it may also return
`source_expectations` for explicitly null `events`, `source_dispositions` or
`source_manifest_ids` slots. These must come from captured producer/broker inputs,
not Silver/Gold output. The reviewed mapping must preserve their raw source proof.
The harness records this receipt and its derived `bound_fixture.json` before the
separate sink audit. Runtime binding cannot change frozen prices, quantities,
expected outcomes or Gold aggregates. Saved reconciliation reconstructs the binding
and verifies it still equals the recorded bound fixture.

Real bindings require a `review_path` JSON record with `schema_version: 1`,
`read_only_audit: true`, `namespace_scoped: true`, reviewers Jaineel/Harsh/Aditya/
Vichitr, `fixture_sha256` of the exact independent fixture bytes, and nonempty
`contracts: [{path, sha256}]` covering the approved canonical contracts and export
mapping implementation. These references must resolve within the repository and
still match their recorded bytes. This record documents actual completed review;
the harness does not generate owner approvals. No such review currently exists.

## Fault and recovery evidence

Each fault binding provides async `arm(context, barrier, target)`, `wait(context,
receipt)`, `stop(context, acknowledgement)` and `restart(context, acknowledgement)`.
The returned acknowledgement must contain the exact namespace/run/case/barrier/
target, a nonempty receipt ID and `acknowledged=true`. A rejected acknowledgement
is retained and cannot trigger a stop. Restart must prove the same namespace/run/
target, readiness and retained volume. There is no arbitrary shell/process-kill API.
Restart is attempted even when the stop response is lost; failed recovery remains
incomplete. Fault callbacks and case execution have bounded timeouts.

Canonical hook names remain in common §14. Additional case boundaries such as
before local commit, staging promotion, stock-commit saga recovery, compensation,
and file rename are explicit pending owner bindings, not newly invented provider
endpoints. Agree their exact mapping before registration. A random process kill
cannot satisfy these cases.

For each T-11 case, start W-CHECKOUT and the collectors first, then call
`fault_gate.run(measurement_origin=ACTUAL_MONOTONIC_MEASUREMENT_START)` concurrently
with the workload. The gate schedules injection at measurement second 180, requests
restart after 30 seconds and requires recovery within 120 seconds. Analytics and
Kafka run in separate fresh namespaces. Save acceptance, all finality samples,
1-second lag/outbox/pending-export journals and post-recovery independent audits.
Unit tests inject an explicit clock; actual execution uses a monotonic real clock.

T-12 replay starts with an empty isolated effective namespace and repeats into
that same target to prove idempotence, preserving original envelopes/event times.
Save operational stock/payment snapshots before and after, the two logical digests,
replay receipts and manifest history. An optional second fresh target is additional
evidence; it cannot replace the same-target repeat required by common §12.

## Pending owner handoffs and manual review

| Owner | Required before real gates |
|---|---|
| Harsh | Catalogue/quote/facet OpenAPI and DTOs; source/normalized/active-SKU manifests; independent normalization comparison; stock projection/bootstrap/version receipts; import/compaction barriers |
| Aditya | Orders/Inventory/Payments APIs and DTOs; shared transactional outbox/DDL; deterministic seed/payment controls; namespace-scoped quote/order/stock/reservation/ledger/guard audits; race/response-loss/compensation hooks |
| Vichitr | Locked Compose/Kafka/registry environment; event schemas/builder/transport; Bronze/Silver/quarantine/active-Gold membership and receipts; publication/replay hooks; analytics/Kafka stop/restart receipts and observers |
| Jaineel with consumers | Review exact provider exports/fixtures, register real consumer mappings and setup actions, freeze ready evaluation config only after actual locks/manifests exist |

After handoffs, follow file09 §2 in order and rerun this checkpoint into a fresh
directory. Trace one success and one decline by the same session/cart/version,
quote, confirmation, order, reservation, payment, ledger, stock event and active
Gold generation. Verify multiple duplicate deliveries have one logical effect.
Inspect fault receipts before crashes and restart volume identity. Verify replay
leaves operational snapshots unchanged. For any contract mismatch retain the
exact request, expected/actual response, fixture hash, evidence path and named
owner; leave the case failed/incomplete until that owner's fix is merged and rerun.

All required real cases must execute without skips before claiming the P8 real
gate. G4 also requires the actual correct baseline artifacts defined in the common
spec; this P8 harness never claims that P9 measurement work has happened.
