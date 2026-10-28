# P10 report and reproducibility handoff

P10 implements Jaineel's saved-evidence reporting and isolated setup rehearsal.
The canonical requirements remain [playbook P10](../specs/10_JAINEEL_CODEX_PLAYBOOK.md#p10--report-reproducibility-and-release-check),
[evaluation §10](../specs/03_EVALUATION_SPEC.md#10-reporting-rules-and-final-tables)
and [runbook §7](../specs/09_EVALUATION_RUNBOOK.md#7-required-artifacts-collectors-and-final-report).
No tracker, provider implementation, public service DTO or P11 behavior changes.

The available checkpoint has no measured B0, candidate, C-BEST or stress result.
The generated report is **INCOMPLETE**, with no accepted performance values or
plots. All 73 actual P9 result records and 37 unavailable real-evaluation cases
are retained. Source accounting can pass independently; it does not establish
provider normalization, facet quality, import performance or integrated correctness.

## Saved input and output

`report build` consumes the native `benchmark matrix` result object:

```text
plan: filename of the saved plan beside this result file
runs: [{run_id, evidence_dir, exit_code}, ...]
pending: exact pending records from the saved plan
support: optional P10 fields described below
```

Every support reference is exactly `{path, sha256}`, with repository-relative
paths and SHA-256 of exact bytes. `support` accepts `dataset_checks` (one independent
source report), `evaluations` (a list of real evaluation manifest references),
`selection` (one actually reviewed P9 selection receipt), `conclusions` (owner
bottleneck/causation/cost documents), and `rehearsal` (one completed verifier
`checks.json`). Absent or unsuccessful required evidence blocks completion.
Do not manufacture a receipt or owner approval to populate these fields. Adding
support creates a new input file; preserve the original matrix output unchanged.

`report.json` follows `contracts/evaluation/report.schema.json`. `report.md`
contains the required dataset/import/stream/index/scaling/layout/fault/integrated
tables and separate optional assistant/ANN tables. Metrics preserve their original
unit, cohort, numerator/denominator, sample/unresolved count, quantile/timing method,
run/config hashes and raw path. Failed measurements retain reasons and source
links; invalid measurements are withheld. Actual hardware, locks, controls,
resources and raw diagnostics remain in each run's context and evidence index.

Every advertised comparison is rebuilt from all six raw bundles, with repetitions
1/2/3, fixed treatment and equal controls. Values include each repetition and
median/min/max. Lower latency/resource use is a reduction; higher throughput is a
gain. A cost increase is negative improvement. Baseline zero leaves percentage
null and retains absolute change. Unknown metric directions are not guessed.
Comparisons do not automatically select a winner. Required-core completeness is
separate from release review; optional live-model/ANN absence cannot establish or
replace required results.

`evidence-index.json` hashes the matrix input, plan, all accepted run files and
supplied supporting evidence, including reviewed transitive references. Preserve
the repository-relative layout when exporting. Raw datasets/results remain ignored
and are not committed. No workload, provider action, database write or reset is
performed by report construction.

## Commands and review

Use actual runner directories for the first two commands, with all three paired
repetitions for comparisons:

```powershell
.venv/Scripts/python.exe -m projectctl benchmark reconcile --run-dir benchmarks/results/RUN_ID
.venv/Scripts/python.exe -m projectctl benchmark compare --baseline benchmarks/results/B1,benchmarks/results/B2,benchmarks/results/B3 --candidate benchmarks/results/C1,benchmarks/results/C2,benchmarks/results/C3 --out artifacts/comparisons/new-pair
.venv/Scripts/python.exe -m projectctl report build --matrix-results artifacts/p10/input/core_matrix_results.json --out artifacts/p10/new-report
```

Replace the capitalized identifiers with actual paths. Current real reconcile,
compare and report attempts return 4 because the necessary measurements do not
exist. A blocked baseline is not a successful performance measurement. A single
baseline/candidate pair is rejected as bad input (exit 2).

Run the clean rehearsal command in [the integration runbook](../integration_runbook.md#p10-saved-report-and-clean-rehearsal).
Choose a new output directory on every attempt. Inspect the checked-out revision,
fresh namespace, locked-install log and source checksum. Follow setup outcomes:
migrations/import/seed/projection must not be called after their prerequisite
fails. Read the independent contract and data/smoke case journal too.

Compare the rebuilt `report.json` bytes and content hash without rerunning
workloads. Trace an actual metric to its raw evidence and recompute the recorded
quantile/rate; use its sample count and denominator. The current checkpoint has no
performance metric to trace, so that manual check is NOT_RUN. Unit fixtures test
the raw trace and repeated-run presentation with explicit loader doubles. The
independent CSV accounting can be traced to the exact source checksum separately.

The verifier removes `summary.json` only from its fresh disposable evidence copy.
Its copied result must be rejected with exit 4 and no accepted measurements.
Original evidence is retained. Have Harsh/Aditya/Vichitr repeat setup and a small
success/decline flow, returning their command logs and identity-linked audit paths.
This human reproduction is still NOT_RUN; no messages were sent on your behalf.

## Remaining owners and release evidence

- Harsh: canonical catalogue/facet/quote contracts and data manifests, verified
  normalization/category quality, import/query/layout evidence and cost conclusions.
- Aditya: real Orders/Inventory/Payments, shared outbox, deterministic seed and
  scoped ledger/stock/finality audits with acknowledged recovery hooks.
- Vichitr: locked enforceable Compose/Kafka/registry deployment, transport,
  analytics/replay/publication membership, real collectors and fault controls.
- All owners: real correctness, clean same-revision B0, controlled paired matrix,
  measured selection/stress/recovery, actual resource/cost limitations, required
  plots from real data and independent clean-setup review. No sample figures apply.

Report implementation and dependency handling can be reviewed locally. G4/G5/G6
and the real P10 release remain incomplete until those handoffs actually execute.
Stop before P11; fixed mode remains zero-generative-call behavior.
