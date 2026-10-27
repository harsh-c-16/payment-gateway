# P9 performance handoff

This implements Jaineel's P9 orchestration checkpoint. It does not establish a
real B0, G4/G5, a winning optimization, or a sustainable rate. Follow the canonical
[P9 scope](../specs/10_JAINEEL_CODEX_PLAYBOOK.md#p9--baseline-and-controlled-optimization-experiments),
[evaluation protocol](../specs/03_EVALUATION_SPEC.md), and
[matrix](../specs/09_EVALUATION_RUNBOOK.md#5-performance-commands-and-matrix).
P10 report/release work is not implemented.

## Provider composition

Use `PROJECTCTL_ADAPTER_MODULE=your.reviewed.module` as documented in the
[P8 runbook](../integration_runbook.md). The module explicitly registers
`ExperimentBindings` for each workload. There is no automatic test transport or
fallback. Harsh supplies import/search/query/compaction adapters, Aditya supplies
transaction preparation/audits and worker fault hooks, and Vichitr supplies real
transport/analytics observations, deployment controls and recovery hooks.

Bindings continue to use the P4 driver/prepare/validate/drain/audit callbacks.
`prepare` must acknowledge a new namespace, actual `resource_profile` equal to
the resolved profile, matching `effective_parameters`, and the actual
`topics_partitions_groups` list used by the run manifest. P33 splits the existing total consumer allocation;
it does not increase it. `validate` must verify deployed treatment, actual topic
partitions/groups, pinned input/seed/projection and the fresh namespace before
timing. This is a provider handoff, not an implementation of those services.

`performance_review_path`, or CLI `--readiness`, identifies an explicit JSON
review receipt. Do not commit generated receipts, source data or results. Receipt
fields are exactly:

```text
schema_version: 1
content_sha256: canonical hash excluding this field
reviewers: [Jaineel, Harsh, Aditya, Vichitr]
git_commit: clean frozen application revision
controls_sha256: benchmarks.performance.controls_hash(config)
resource_receipt: {path, sha256}
correctness_runs: [{path: .../manifest.json, sha256}, ...]
inputs: [{path, sha256}, ...]
smoke_run: null initially, then {path: .../manifest.json, sha256}
baseline_run: null initially, then {path: .../manifest.json, sha256}
diagnosis: null initially, then {path: .../diagnosis.md, sha256}
hypotheses: [{path: .../hypothesis.md, sha256}, ...]
```

Paths are repository-relative. `inputs` covers exact source, dictionaries,
canonical/SKU manifests and frozen logical fixtures. Freeze separate recipes for
short smoke, rate and skew series. Their JSON is the exact `generate_workload`
manifest; it is checked before emission when the base template hash differs.
Source/rules, cache, payment semantics and resources remain fixed within pairs.

The resource receipt is an actual infrastructure-owner export with
`test_mode=real`, `enforced=true`, matching `git_commit` and complete `profile`,
`image_digests` containing pinned `image@sha256:...` values, and `host` containing
`cpu_model`, `physical_cores`, `total_memory_bytes`, `os`, and `storage`. Planned
allocations and a local PostgreSQL-only smoke do not establish this receipt.

Correctness receipts reference complete, hash-verified, same-revision real
`eval run` bundles. All cases in `correctness,smoke,T-10,T-11` must pass with
assertions and raw evidence, with no skipped/unavailable cases. Optional live
model results do not enter core success. Missing owners remain visible.

## Measurement sequence

1. Finish preparation, review and commit code/config; keep B0/candidates
   selectable from that revision. Run the canonical setup and correctness gates.
   Review/freeze actual feasible resources and input hashes. Keep generated
   evidence in ignored paths so it does not dirty the code revision.
2. Run a short setup check (not performance):
   `python -m projectctl benchmark run --workload W-PIPE --variants B0 --repetitions 1 --smoke --readiness artifacts/p9/review.json --config configs/evaluation.yaml`.
   Bind its hash-verified manifest to `smoke_run` in the reviewed receipt.
3. Run one full baseline:
   `python -m projectctl benchmark run --workload W-PIPE --variants B0 --repetitions 1 --readiness artifacts/p9/review.json --config configs/evaluation.yaml`.
   Inspect raw emissions/timings/lag/resources, active membership and independent
   audit. Bind `baseline_run`; record the observed backlog/CPU/query-plan cause
   in `diagnosis` and each owner's predeclared hypothesis and cost risks.
4. Launch the matrix once:
   `python -m projectctl benchmark matrix --matrix configs/core_matrix.yaml --readiness artifacts/p9/review.json --config configs/evaluation.yaml`.
   First-stage independent rows run; selected rows remain pending until measured
   choices exist. Do not also run the runbook's equivalent example command list.
5. Compare all three paired repetitions, using comma-separated directories:
   `python -m projectctl benchmark compare --baseline benchmarks/results/B1,benchmarks/results/B2,benchmarks/results/B3 --candidate benchmarks/results/C1,benchmarks/results/C2,benchmarks/results/C3 --out artifacts/comparisons/pair`.
   Replace B1..C3 with actual IDs from the plan results. A single best run is
   rejected. Output includes median/min/max, individual values, sample/unresolved
   counts, correct percent direction, and null percentages for a zero baseline.
6. Review the measured selection receipt below and resume the same matrix with
   `--selection artifacts/p9/selection.json`. Unchanged completed trials are
   reused only after full raw hashes, controls, revision and real collectors
   validate. Failed/incomplete runs are retained and get fresh retries.

The first standalone baseline is a qualification repetition, not one of three
matrix repetitions: its resolved repetition protocol differs deliberately.
Matrix results link every run. C-BEST is an evidence label in execution order;
the underlying registered variant and complete effective parameters remain
visible in the run. No teammate optimization is implemented here.

## Audits and collector outputs

Each real trial retains `performance_review.json`, `resource_receipt.json`, raw
P4 journals and P5 telemetry, `expected.json`, `observed.json`, owner-reviewed
`binding_review.json` and `performance_validation.json`. Required collectors are
real and complete; missing samples invalidate promotion. Stream trials also
require lag, outbox/pending-export and active-Gold evidence. All nested plan and
manifest files are indexed and hashed by the final run manifest.

Stream audits use the existing independent reconciliation projection. Import,
search and analytical adapters use a reviewed harness projection with
`expected.logical_results` frozen before execution and matching
`observed.logical_results`, `namespace`, `test_mode=real`, and
`collection_complete=true`. These are audit projections, not replacement public
DTOs. Expected import results must include full source accounting and independent
business digest; query results include fixed per-query results/filter verdicts
and pinned input generation. Providers must review those mappings.

Imports retain `import_timings.json` with existing `raw_to_ready_seconds`,
`logical_digest`, and `stages.staging_seconds`; throughput uses actual finite
elapsed time (20,000 source / total, 19,998 canonical / staging), never 600 s.
I0/I1 digests must match. Analytical runs retain raw query results and execute
Q1–Q6 with 3 warmups and 30 measurements, in three paired repetitions. The two
F-PARTITION children both use compact 32-MiB zstd files; partition-only comparison
accepts only the difference in partition keys. Search ranking modes remain
separate paired series.

Timing producers use stages `producer_to_gold`, `schedule_to_gold`, `query`,
`workflow`, `acceptance`, and `finality` for corresponding primary p95 metrics.
Stage distributions retain namespaced p50/p95/p99 and unresolved counts. Actual
usage/resource costs remain separate from requested rates and targets.

## C-BEST and stress

The selection JSON has `schema_version=1`, `content_sha256`, and `choices` with
exactly `W-PIPE` and `W-INTEGRATED`. Each choice contains `variant`, `metric`,
`rationale`, `reviewers` (all four owners), `costs_accepted=true`, and
`comparisons` (path/SHA references to complete `comparison.json` files).
The runner recomputes each comparison from its six raw bundles. A candidate
needs measured improvement in the chosen metric and explicit cost review. O3
additionally needs independently justified O1/O2 plus measured integrated
interaction. Negative results can select B0; no winner is assumed.

Selection uses only registered provider-supported configurations. A new combined
treatment outside that registry requires its owner's adapter/configuration and
reviewed comparison; it is rejected here rather than silently implemented or
represented as O3. This is a remaining provider handoff if selected.

Stress evaluates 500, 1,000 and 2,000 in ascending tiers, with all three repetitions
and raw UTC-aligned one-second lag/outbox/pending samples. `*-capacity.json`
retains eligibility, OOM/resource evidence failures, missing samples, lag slope,
admission and SLO qualification separately. A failed/incomplete lower tier blocks
higher-tier emission. Optional 5,000/s is not automatically launched. Recovery
uses the named 30-second consumer pause and retains its acknowledgement and
recovery receipt. A missing fault acknowledgement is incomplete evidence.
Capacity requires cgroup memory samples for every declared SUT component,
matching its allocation, and actual `details.oom_kill_count=0`. A reader without
OOM evidence leaves capacity invalid; it does not supply a default zero.

## Available local checkpoint

Run `python -m benchmarks.manual.verify_p9` only while these provider handoffs are
absent. It retains the actual dependency failures for contracts, all correctness
cases, one smoke, one B0 and exactly one matrix invocation. It asserts that none
started and that metrics remain null/NOT_RUN. This verifies honest failure
handling, not provider correctness or benchmark performance. Stop before P10.
