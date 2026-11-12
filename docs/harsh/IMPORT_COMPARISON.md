# Import optimization: I0 row inserts versus I1 COPY

**Result.** Loading the 19,998 canonical rows into the staging table with PostgreSQL `COPY`
(I1) instead of one `INSERT` per row (I0) makes staging 3.3× faster: 3.74 s → 1.13 s. The whole
import, from raw CSV to a promoted and analyzed catalogue, goes from 11.81 s to 9.26 s (−21.6%).
Both variants produce byte-identical normalized outputs.

This is an **owner-run measurement on one machine** (Harsh's laptop, 12 November 2026). It is not
the shared-runner evaluation (P9) and not the frozen `local4c8g` resource profile, and it has three
repetitions, so no confidence interval is claimed.

## Setup

| Item | Value |
|---|---|
| Code revision | `348ec3462f3cf65ab5313fcfd25d69bac0435ecc` (`main`, PR #20 merge), clean worktree (`dirty: false` in `summary.json`) |
| Input | `flipkart_com-ecommerce_sample.csv`, SHA-256 `56f8f699…93ad1`, 20,000 records, rules `flipkart-v1` |
| CPU | AMD Ryzen 7 7840HS, 8 cores / 16 threads |
| Memory | 15.4 GB (15,361,101,824 bytes) |
| Storage | PostgreSQL data directory on the internal NVMe SSD (Kingston SNV2S250G), ext4 |
| OS | Ubuntu 26.04.1, Linux 7.0.0-43 |
| Database | PostgreSQL 18.6 (conda-forge build), default settings: `fsync=on`, `shared_buffers=128MB` |
| Client | Python 3.11.15, psycopg 3, same host over TCP loopback, no resource limits |
| Repetitions | 3 paired; variant order shuffled per repetition with a fixed seed; each run in its own process and its own fresh schema (dropped afterwards) |

## What changed between the variants

Only the staging step (`pipelines/catalog/load.py`, `_stage_chunk`). Everything else (parsing,
normalization, Parquet artifacts, ledgers, promotion, `ANALYZE`) is the same code.

| | I0 (`--load-mode row`) | I1 (`--load-mode copy`) |
|---|---|---|
| Staging statement | `INSERT INTO catalog_stage … VALUES (…)`, executed once per row | `COPY catalog_stage … FROM STDIN`, one stream per chunk |
| Statements per 1,000-row chunk | 1,000 inserts + 1 checkpoint insert | 1 copy + 1 checkpoint insert |
| Transaction and restart unit | One chunk; rows and their checkpoint commit together | Same |

## Raw timings, every repetition

Seconds, from each run's `import_timings.json`:

| Rep | Variant | Raw → ready | Staging | Parse + normalize | Parquet artifacts | Promotion | Client CPU | WAL (MB) | Peak RSS (MiB) |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | I1 | 9.707 | 1.133 | 2.928 | 1.541 | 2.477 | 6.85 | 126.92 | 615 |
| 1 | I0 | 11.815 | 3.735 | 2.688 | 1.478 | 2.448 | 7.75 | 126.89 | 618 |
| 2 | I1 | 9.264 | 1.125 | 2.704 | 1.501 | 2.436 | 6.58 | 126.92 | 611 |
| 2 | I0 | 11.739 | 3.700 | 2.669 | 1.503 | 2.427 | 7.72 | 127.10 | 613 |
| 3 | I0 | 11.846 | 3.752 | 2.716 | 1.505 | 2.418 | 7.79 | 127.76 | 614 |
| 3 | I1 | 9.217 | 1.129 | 2.690 | 1.500 | 2.447 | 6.58 | 126.93 | 618 |

Rows are in execution order. The remaining stages (archive read, export, ledger) take
0.09–0.18 s each and are in the raw files.

## Summary (medians)

| Metric | I0 row | I1 COPY | Change |
|---|---:|---:|---:|
| Staging time | 3.735 s | 1.129 s | 3.31× faster |
| Staging throughput (canonical rows/s) | 5,354 | 17,719 | +231% |
| Import duration, raw CSV → ready | 11.815 s (11.74–11.85) | 9.264 s (9.22–9.71) | −21.6% |
| Import throughput (source rows/s) | 1,693 | 2,159 | +27.5% |
| Client CPU | 7.75 s | 6.58 s | −15% |
| WAL written | 127.10 MB | 126.92 MB | same |
| Client peak RSS (largest of 3) | 618 MiB | 618 MiB | same |

## Same output from both variants

| Check | I0 (3 runs) | I1 (3 runs) |
|---|---|---|
| Source rows / canonical / active | 20,000 / 19,998 / 19,920 | 20,000 / 19,998 / 19,920 |
| Catalogue business digest | `d87f57e638ee…2bba` | `d87f57e638ee…2bba` |
| Normalized manifest content hash | `0d214b4f88f9…e35b` | `0d214b4f88f9…e35b` |

All six runs report the same digest (`digests_equal: true`). The manifest hash is also the one
committed in `data/catalog/flipkart-v1-3a401f32ca99379f8298ce42/normalized_manifest.json`.

## Bottleneck and trade-off

**The bottleneck in I0 is per-row statement overhead, not data volume.** Both variants write the
same rows and the same WAL (~127 MB). I0 pays a client-to-server round trip and a statement
execution for each of the 19,998 rows, about 187 µs per row. COPY sends each 1,000-row chunk as one
stream, about 56 µs per row. The staging saving (2.61 s) is almost all of the total saving (2.55 s),
which confirms that nothing else changed.

**After I1, staging is no longer the bottleneck.** In an I1 run the time goes to Python parsing
and normalization (2.7 s), promotion into `products` with `ANALYZE` (2.4 s) and Parquet artifacts
(1.5 s), with staging fourth at 1.1 s. A further gain would have to come from parsing, not from
the database load.

**Trade-off.** With COPY, one bad row fails its whole chunk instead of a single statement. That costs
nothing here, because rows are validated before staging and a chunk already commits or rolls back
as a unit with its checkpoint. Restart behaviour is identical in both modes, and
`tests/catalog/test_import_live.py` covers it, not these timings. COPY uses psycopg's built-in copy
protocol, so no new dependency. Memory is unchanged because the client holds the parsed file in both
modes. **Decision: I1 is the default load mode**, and the prototype import uses `--load-mode copy`.

Earlier owner runs agree. On 2 November, on the same SSD at an earlier revision, staging went from
3.85 s to 1.17 s and the total from 12.52 s to 9.76 s ([experiments.md §2a](experiments.md)).

## Reproduce

```bash
git worktree add --detach /tmp/import-src 348ec34        # clean tree at the measured revision
ln -s "$PWD/data/raw/flipkart_com-ecommerce_sample.csv" /tmp/import-src/data/raw/
initdb -D ~/pg-import-ssd -U postgres --auth=trust -E UTF8   # data directory on the SSD
pg_ctl -D ~/pg-import-ssd -o "-p 55433 -h 127.0.0.1" start
psql -h 127.0.0.1 -p 55433 -U postgres -c "CREATE DATABASE catalog_db"
psql -h 127.0.0.1 -p 55433 -U postgres -d catalog_db -c "CREATE EXTENSION vector"
cd /tmp/import-src
CATALOG_DATABASE_URL=postgresql://postgres@127.0.0.1:55433/catalog_db \
  uv run --locked python -m pipelines.catalog.experiments import --out artifacts/import-comparison
```

Raw evidence (git-ignored): `artifacts/import-comparison-20261112/summary.json` with every run,
and `rep{1,2,3}-{row,copy}/` with each run's `import_timings.json`, `load_report.json` and
manifests. It is also included in the evidence bundle.
