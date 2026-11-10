# Send this to the teammate running evaluation

Jaineel has implemented the harness handoff after Vichitr's PR #12. Please run
the final evaluation on a dedicated Linux Docker machine after closing the
explicit owner handoffs below. No evaluation was run on Jaineel's laptop.
Use [the canonical evaluation runbook](../specs/09_EVALUATION_RUNBOOK.md) for test
requirements and [P9](p9_performance.md)/[P10](p10_report.md) for receipt/report
formats. The steps below identify the actual implementation and remaining work.
See the [10 November audit](PENDING_WORK_AUDIT_2026_11_10.md) for the current
J01–J07 responsibility register. The successful local prototype is separate
from the formal evaluation described here.

## 1. Freeze machine and source

Use Linux x86_64, SSD, at least 12 logical CPUs and 32 GiB RAM. Plan the complete
`integrated-linux9c8g` SUT from
[`configs/evaluation_profiles.json`](../../configs/evaluation_profiles.json).
It counts every API, standalone worker and relay, including background saga,
expiry, Gold publisher and analytics relay threads in their owning process.
Generator/observer has a separate 1-core/1,024-MiB budget. Record actual CPU model,
physical/logical cores, RAM, OS/kernel/WSL if applicable, SSD/storage and Docker
engine limits. Vichitr must enforce and export real cgroup limits for every
process and prove their totals fit the frozen SUT budget. The planned profile
alone is insufficient. Keep unrelated project processes stopped during trials.

Enforce the declared SQL caps as well as CPU/RAM. For one API process each,
use `CONVERSATION_MAX_CONNECTIONS=3` (including its intent-audit slot),
`CATALOG_MAX_CONNECTIONS=4`, `ORDERS_MAX_CONNECTIONS=4`,
`INVENTORY_MAX_CONNECTIONS=4` and `PAYMENTS_MAX_CONNECTIONS=4`.
Add each separate relay's one connection, and catalogue projection's two.
M4 has twelve sink slots across consumers, two publisher/relay slots on worker
zero and two API slots. At P33 the worker caps are 6/4/4; the API remains separate.
Every process's proposed cap is recorded in `configs/evaluation_profiles.json`;
these declarations do not prove that an unconfigured API's defaults were changed.

Start from the reviewed committed revision shared on `jaineel/prototype-demo`;
use the final agreed revision for every comparator. A dirty tree is rejected by
the real runtime. Install using the unchanged application lock:

```bash
python -m pip install --no-deps uv==0.10.8
uv sync --locked --python 3.11
```

Place the original private CSV at `data/raw/flipkart_com-ecommerce_sample.csv`.
Do not commit it. Prepare a fresh offline packet on this machine:

```bash
uv run --locked python -m projectctl.evaluation_packet --out artifacts/evaluation-handoff/final-machine-01
uv run --locked python -m projectctl.evaluation_packet --verify artifacts/evaluation-handoff/final-machine-01
```

This starts no service and performs no evaluation. Send `input_lock.json`,
`input_hash_policy.json`, `recipes.json`, the two proposed reviews and candidate
configs to the team. The packet is ignored locally, so send it separately along
with this document. Review the actual machine's hashes; Windows CRLF pins are
not automatically the Linux raw-byte pins. Keep the existing LF dictionary
identity/dataset revision. See [Harsh's handoff](HARSH_REVIEW_2026_11_09.md).

The generated integrated YAML is the candidate for the official full matrix.
`pipeline-linux4c4g.yaml` is only a separate pipeline study and cannot be mixed
with official integrated-profile comparisons. Candidate YAMLs remain
`state: draft` and `allocation_status: planned` until real prerequisites are met.

## 2. Finish the owner callbacks before requesting measurements

Set the real team composition:

```bash
export PROJECTCTL_ADAPTER_MODULE=projectctl.jaineel
export PROJECTCTL_RUNTIME_MODULE=projectctl.team_runtime
# Set only when an actual reviewed owner extension module exists:
# export PROJECTCTL_OWNER_RUNTIME_MODULES=your_package.operational_runtime
```

An extension exports `runtime_bindings() -> projectctl.runtime.RuntimeBindings`.
It can supply `workloads` (`OwnerCallbacks`), `g3` (`G3Binding`), remaining
`cases` (`CaseBinding`), `migrations` (database -> callable) and `resets`
(database -> `ResetParticipant(preflight, apply)`). These are harness extension
interfaces, not claims that a teammate already exports those functions. Module
registration is lazy. Duplicate registrations fail rather than replacing M4.

| Owner | Exact work needed |
|---|---|
| Vichitr | Enforce the full process allocation, provide the mounted real lakehouse, schema cache, private service credentials and SELECT-only audit bindings. Supply a drained, isolated `M4_SEED_NAMESPACE`; keep its catalogue/inventory services stopped for a pipeline-only study. Verify `PROJECTCTL_SUT_CONTAINERS` maps each service to all actual container IDs, including API/worker/relay. Establish the shared clock domain for latency collectors; the current M4 observer conservatively defaults to unshared clocks. Review the concrete mappings and fault scope. |
| Aditya | Supply Orders/Inventory/Payments migration participants, real operational fresh-storage proofs, explicit payment controls, signed-ledger/stock/order snapshots, outbox receipts and recovery barriers. Check the exact Inventory SKU key set against the pinned manifest as well as uniform counts/versions. No generic M3 migration callbacks currently exist in this composition. Expose standalone relay startup bindings and count them. |
| Harsh | Confirm input manifests/hashes; connect real catalogue seed/projection/layout/query callbacks, pinned query day/generation, independent import/query expectations, and reviewed request templates. Human relevance review is pending. |
| Jaineel + affected owners | Bind and review each missing D/T/G case listed in `integration_inventory.json`. M4 workload callbacks do not automatically become general suite case adapters. Connect G3 to the actual public services and immutable producer evidence. Preserve the independent expected answer. |

The owned seed auditor now enforces exact active SKU membership across Catalogue,
Inventory and stock projection. The team runtime extends the original M4 seed
callback through `benchmarks.seed_audit.with_seed_membership`; it uses the original
seed namespace and existing restricted SELECT-only readers. Review these mappings
and audit roles as part of the byte-pinned analytics review. Operational extensions
must supply complete unique `catalog_skus`, `inventory_skus` and `projected_skus`
lists or use the same wrapper; count-only evidence fails before emission.

For resets, **all six owner participants** and all read-only preflights must be
present before apply. M4's existing apply helper additionally enforces original
context, quiescence, acceptance, 30-day retention and replay/outbox guards.
Do not delete tables/topics/volumes as a substitute. Start with fresh benchmark
namespaces; reset is not a prerequisite and should not be run during this setup.

## 3. Complete actual reviews and preparation

After reviewing, create new receipts from the proposals; do not edit the frozen
proposal files. Provider review format is schema version 1, `surfaces` keyed by
directory, each with `status: APPROVED`, actual owner + Jaineel in `reviewers`,
and the exact `contracts` list from that surface. Pending entries stay pending.
Analytics review needs all four actual affected reviewers and the complete
byte-pinned mapping references. Proposed review files contain no approvals.

```bash
export PROJECTCTL_CONTRACT_REVIEW_PATH=artifacts/evaluation-handoff/provider_review.json
export ANALYTICS_BINDING_REVIEW_PATH=artifacts/evaluation-handoff/analytics_review.json
```

Supply the private variables documented in
[Vichitr's runtime implementation](../vichitr/runtime_implementation.md#concrete-m4-runtime),
including `CODE_COMMIT`, benchmark/fault controls, broker/registry/cache,
database/audit URLs, service token, lakehouse mount and seed namespace. Keep
secrets out of config, review documents, logs and version control.

1. Bring up and independently verify `streaming-local` through Vichitr's adapter.
   This verifies existing infrastructure; it does not enforce the proposed
   integrated application profile by itself.
2. Run global migrations only after all six callbacks are registered. Missing
   participants now fail before any database migration is called.
3. Import the unchanged catalogue into fresh isolated operational storage, verify
   manifests, seed exactly 19,920 active SKUs at 10,000/0/version 1 with seed 42,
   drain outboxes and cross the complete stock-projection barrier. See canonical
   runbook §2 for the catalogue commands and private deployment instructions.
4. Freeze real checkout/integrated templates and their logical hashes. Retain
   nulls for missing human labels or providers; do not fill them with sample data.
   New transaction recipes pin `transaction_scenario_version=2`: every logical
   purchase has a distinct stable scenario ID and seeded 95/5 outcomes per block
   of 100 offers, with 100-ms delay. Regenerate and review the packet/recipe hashes
   before comparison. Historical version-1 recipes preserve their original
   materialization and cannot share controls with the corrected recipes.
5. Create a new reviewed execution config from the candidate once resources are
   actually enforced and inputs/callbacks are complete. Set `ready/enforced`
   only with evidence. Regenerate/review an input packet if any input changes;
   preserve all earlier packets and keep each comparator on identical controls.

Now run the real contracts and correctness gates, using the reviewed execution
config path in place of `EXEC_CONFIG`:

```bash
uv run --locked python -m projectctl contracts check --all
uv run --locked python -m benchmarks.quality_trial --config EXEC_CONFIG --out artifacts/g1/final-machine-01
uv run --locked python -m projectctl eval run --suite contracts,data,smoke --config EXEC_CONFIG
uv run --locked python -m projectctl eval run --suite correctness --config EXEC_CONFIG
uv run --locked python -m projectctl eval run --suite T-10,D-05,T-11 --config EXEC_CONFIG
```

Replace placeholders with actual repository-relative paths. The separate G1
command runs three records; full T-03 remains 100,000. Generic `smoke/G1` and
`T-03/quality` still need their complete reviewed case bindings. A passing
separate G1 or provider pytest suite does not satisfy an unbound case.
Inspect `tests.jsonl`: no required case may be NOT_RUN/INCOMPLETE/skipped.
Exit 4 is a missing dependency/evidence result, not a pass. Preserve the reason
and return it to the named owner before proceeding.

## 4. Measure and return evidence

Build the actual P9 correctness/resource review receipt using
[the exact existing format](p9_performance.md#provider-composition). It must pin
the clean revision, actual host/images/resources, all logical fixture files and
same-revision real correctness bundles. No generated proposal is a readiness
receipt. Use `--readiness` or `PROJECTCTL_PERFORMANCE_REVIEW_PATH` for workloads.

Follow the P9 sequence: short B0 smoke, one full B0 qualification, bottleneck
diagnosis and owner hypotheses, then the matrix once with three paired
repetitions. These are the existing commands; they are intentionally blocked
until the preceding handoffs pass:

```bash
uv run --locked python -m projectctl benchmark run --workload W-PIPE --variants B0 --repetitions 1 --smoke --readiness P9_REVIEW --config EXEC_CONFIG
uv run --locked python -m projectctl benchmark run --workload W-PIPE --variants B0 --repetitions 1 --readiness P9_REVIEW --config EXEC_CONFIG
uv run --locked python -m projectctl benchmark matrix --matrix configs/core_matrix.yaml --readiness P9_REVIEW --config EXEC_CONFIG
```

Bind the actual smoke/baseline/diagnosis receipts between steps. Do not also run
the equivalent example list as extra matrix trials. C-BEST/stress rows remain
pending until reviewed measured selection exists; then resume the matrix with
the actual `--selection` receipt. Keep offered/admitted/achieved counts, missed
offers, every latency sample/unresolved count, lag, outbox/pending Gold and all
process resources. Record unavailable I/O as null. Keep all failures and runs.

Return the source commit, frozen packet/execution config, owner review receipts,
actual resource/host/image proof, all `artifacts/projectctl/` and
`benchmarks/results/` bundles, matrix plan/results, raw logs/Parquet/JSONL/CSV,
and module-owner bottleneck notes. Exclude credentials and private env files.
Maintain the repository-relative directory layout so hashes resolve.

Jaineel then runs the existing `benchmark reconcile`, three-pair
`benchmark compare`, and `report build --matrix-results MATRIX_RESULTS --out REPORT_OUT`
as documented in [P10](p10_report.md). Add actual dataset/evaluation/selection/
conclusion/rehearsal support references without overwriting the original matrix
result. Reports must retain null/NOT_RUN for missing work. Do not transcribe
numbers manually, sum overlapping pytest phases, or reuse the old lab examples.
