# Analytical query suite (M2)

Owner: Harsh Chaudhari. Authority: [common §13](../../docs/specs/02_COMMON_SPEC.md),
[evaluation §5.2](../../docs/specs/03_EVALUATION_SPEC.md) and [runbook §5](../../docs/specs/09_EVALUATION_RUNBOOK.md).

`suite.py` holds the frozen Q1-Q6 SQL. Each query runs in DuckDB over the explicit file list of one
manifest, never a glob. It records wall time, CPU, files opened, selected file bytes, read-syscall
bytes and returned rows. File-size sums are selected bytes, not bytes read.

`fixture.py` builds a labelled synthetic dataset through the real Bronze, Silver, Gold and publication
code, publishing often enough to create the small-file layout. `experiment.py` runs F-COMPACT and
F-PARTITION on it: `ANALYTICS_DATABASE_URL=... python -m analytics.queries.experiment --out DIR`. Add
`--cold` for the separate cold-cache series, on real storage and on Linux only.
