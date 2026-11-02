# M2 experiments: baseline versus optimized

Owner: Harsh Chaudhari (B24CM1027). Measured 2 November 2026.

Every result here is an **owner run on one host**, not the frozen P9 profile: 16 cores, 15 GB RAM,
no resource limits, PostgreSQL 18 with default settings (`shared_buffers=128MB`), closed-loop
clients and no outbox write, because Aditya's library is not available yet. Use these numbers to
compare variants on this machine, not as absolute service capacity. The official runs through
Jaineel's runner are still NOT_RUN.

Evidence commit is `deb084d`, except W-ANALYTICS, which ran at `fde1210`; nothing under `analytics/`,
`pipelines/curation/` or `pipelines/storage/` changed between them. Raw results stay in the ignored
`artifacts/experiments/` directory, and the commands at the end regenerate them. Expectations below
come from the design stage. A trial run had already shown rough import and index numbers, so they
were not blind predictions.

## Decisions

| Change | Decision | Main evidence | Cost |
|---|---|---|---|
| Statistics when a load becomes ready | **Keep** (bug fix) | First-minute search 133 → 29 ms | About 0.9 s per import, 33 ms on stock |
| I1, COPY into staging | **Adopt** | Staging 3.07 → 0.99 s, same digest | None measured |
| O2, category and price B-tree | **Adopt, for typical latency only** | Lexical p50 42.7 → 13.5 ms; p95 unchanged | 0.48 MB, 0.8 s build |
| P1, reused sessions | **Recommend**; needs Jaineel's decision because it is outside the frozen matrix | Capacity 111 → 370 searches/s with O2 | Idle sessions held open |
| F-COMPACT | **Adopt** | Q1 988 → 10 ms, 11,146 → 91 files, same results | 24 s per run |
| F-PARTITION, date and type partitions | **Keep existing layout**; no latency case for or against | Fewer bytes read, same warm latency | None measured |
| HNSW (R-ANN) | **Do not adopt** at this size | Full-search p50 level, p95 worse, recall 0.906 | 37 MB, 1.75 s build |

## 1. A bug found by the measurements: no statistics after a load

**What the numbers showed.** A query with 4 eligible products took 125 ms in the benchmark but
0.2 ms in its saved plan. Every statement lost about 60 ms for the first minute after a load, in
every variant.

**Cause.** Neither `catalog import` nor stock seeding ran `ANALYZE`, so statistics appeared only when
autovacuum ran about 55 seconds later. The planner expected 34 rows in `stock_projection` when there
were 19,920, and drove a nested loop from stock:

| Same query (U05, filter statement) | Execution | Buffers hit |
|---|---|---|
| Before `ANALYZE stock_projection` | 68.6 ms | 80,199 |
| After | 12.9 ms | 4,937 |

Full `filter_only` search over four test queries, timed as a timeline after a fresh load:

| Seconds after load | Before the fix, p50 | With `ANALYZE` straight after the load, p50 |
|---|---|---|
| 0–20 | 133 ms | 29 ms |
| 40–50 | 133 ms | 29 ms |
| After autovacuum | 29 ms | 29 ms |

**Fix (`deb084d`).** Import promotion now analyzes `products` in the same transaction. `projection wait`
analyzes `stock_projection` when it reports ready, and the experiment harness does the same when
seeding. Promotion went from about 1.4 s to 2.3 s, so an I1 import went from 7.9 s to 8.9 s; analyzing
stock took 33 ms.

**How much of the earlier results it had distorted:**

| Result | Before the fix | After the fix |
|---|---|---|
| `filter_only` B0 p95 | 119.6 ms | 40.6 ms |
| `filter_only` O2 p50 | 16.6 ms | 11.7 ms |
| `filter_only` 10× B0 p99 | 1,694 ms | 257 ms |
| Hybrid exact, full search p95 | 229.8 ms | 95.1 ms |
| Hybrid ANN, full search p50 | 80.4 ms | 64.8 ms |
| Queries that looked slower with O2 (1×, `filter_only`) | 3 | 0 |

Earlier evidence is kept in `artifacts/experiments-before-analyze-fix/`, with the diagnostic scripts.

## 2. W-IMPORT: I0 row inserts versus I1 COPY

**Expectation:** COPY cuts staging time; the total improves less because staging is one stage of many.

Three paired runs on the real 20,000-row file; medians:

| Metric | I0 | I1 |
|---|---|---|
| Staging | 3.07 s | 0.99 s |
| Raw file to ready (range) | 10.76 s (10.31–11.37) | 8.92 s (8.50–8.93) |
| Canonical rows per staging second | 6,504 | 20,117 |
| Raw rows per total second | 1,859 | 2,242 |
| WAL | 126.9 MB | 127.0 MB |
| Client peak memory | 637 MiB | 632 MiB |
| Client CPU | 7.4 s | 6.6 s |

Both produced the logical digest `d87f57e6…` with 19,998 canonical and 19,920 active rows.

**Conclusion.** Adopt I1: staging is 3.1× faster and the total 17% lower, with no measured cost.
Stages in one I1 run were parsing and normalizing 2.71 s, promotion 2.32 s, Parquet artifacts 1.50 s
and staging 0.99 s, so staging is no longer the bottleneck. Any further gain has to come from parsing.
Restart behaviour is covered by `tests/catalog/test_import_live.py`, not by these timings.

## 3. W-SEARCH: B0, O2 and P1 on the real catalogue

**Expectation:** O2 helps queries with a category filter and not those without one. P1 removes a
fixed cost per request.

50 fixed queries, 3 warm-ups and 30 executions per query, 3 paired repetitions, client time in ms.
Every run had **0 hard-filter violations and 0 result differences between variants**.

| Mode | Metric | B0 | O2 | P1 | O2+P1 |
|---|---|---|---|---|---|
| `filter_only` | p50 | 31.2 | 11.7 | 20.9 | **4.7** |
| | p95 | 40.6 | 40.8 | 28.6 | **26.4** |
| | p99 | 54.2 | 56.3 | 43.1 | 44.8 |
| `lexical` | p50 | 42.7 | 13.5 | 32.0 | **4.9** |
| | p95 | 54.9 | 54.8 | 42.9 | **41.6** |
| | p99 | 56.0 | 56.3 | 43.7 | 50.4 |

Lexical p50 by query group:

| Group | B0 | O2 | P1 | O2+P1 |
|---|---|---|---|---|
| Broad | 47.4 | 15.0 | 37.1 | 10.1 |
| Selective | 41.4 | 11.3 | 31.1 | 3.8 |
| Few results | 41.7 | 41.3 | 31.4 | 5.0 |
| Zero results | 40.8 | 13.3 | 30.6 | 2.4 |

Costs:

| Cost | B0 | O2 | P1 | O2+P1 |
|---|---|---|---|---|
| Index size | – | 483 KB (table 61.8 MB) | – | 483 KB |
| Index build | – | 0.80 s | – | 0.80 s |
| Price update p50, by repetition | 5.01–5.04 ms | 5.02–5.07 ms | 0.49–0.53 ms | 0.50–0.69 ms |

**O2.** p50 improves 2.7× for `filter_only` and 3.2× for `lexical`, and 35 of 50 queries are more than
10% faster in each mode, with none slower. **p95 and p99 do not improve.** The plans explain why: 10
`filter_only` and 15 `lexical` queries do not use the index. Some have no category filter (B16, B17,
B19, B20); others cover so much of the table that a scan is the sensible plan (B01, B02, B18 in
`lexical`). An update cost is not visible next to the 5 ms connection cost. With P1 it appears as up
to about 0.2 ms in two of three repetitions, so it is small rather than zero.

**P1.** Saves about 10 ms per search and makes price updates 10× faster, because each transaction no
longer opens a connection.

**O2+P1 is much better than the two added together, and the reason is not obvious.** On reused
sessions psycopg prepares a repeated statement, and PostgreSQL can then switch to a cached generic
plan. A separate check, run on O2 while the test suite was also running, so only the comparison
within each query is meaningful:

| Lexical p50, ms | U01 | U02 | U03 | Z02 | S01 | B01 |
|---|---|---|---|---|---|---|
| New session per transaction | 50.5 | 48.9 | 50.7 | 50.4 | 50.5 | 64.7 |
| Reused, prepared statements off | 37.1 | 36.3 | 36.9 | 36.1 | 36.7 | 50.2 |
| Reused, prepared statements on (default) | 9.6 | 8.8 | 9.7 | 5.5 | 6.4 | 58.9 |

So the plan PostgreSQL picks from the actual values is often worse than the generic plan that uses
O2. Two consequences:

- This gain depends on psycopg's default `prepare_threshold` and on PostgreSQL's `plan_cache_mode`.
  It is not a property of the index alone.
- A generic plan can also lose: B01 is about 17% slower with it. That fits lexical p99 rising from
  43.7 ms under P1 to 50.4 ms under O2+P1.

The planner's costing may be the underlying issue. Lowering `random_page_cost` for SSD storage might
get the same plan without prepared statements, but **that has not been tested**.

**The secondary target of full-search p95 below 200 ms** is met by every variant here, on this
unconstrained host and without the outbox write.

## 4. Synthetic 10× catalogue

**Expectation:** the index pays off more as the table grows.

The catalogue is cloned 10 times, so this is labelled synthetic and selectivity is unchanged. 10
executions per query, 3 repetitions, 0 violations, 0 result differences.

| Mode | Metric | B0 | O2 |
|---|---|---|---|
| `filter_only` | p50 | 107.0 | 67.5 |
| | p95 | 163.8 | **221.8** |
| | p99 | 256.6 | 264.3 |
| `lexical` | p50 | 163.2 | 78.3 |
| | p95 | 262.2 | 266.8 |
| | p99 | 274.0 | 278.0 |

Index 1.8 MB on a 618 MB table, 1.53 s to build. Price update p50 is 4.96–5.08 ms for B0 and
5.02–5.10 ms for O2.

**Conclusion: the expectation was wrong on this data.** The p50 gain shrinks (lexical 3.2× → 2.1×,
`filter_only` 2.7× → 1.6×), `filter_only` p95 gets 35% worse, and three cases are real regressions:
S02 goes 133 → 223 ms in `filter_only` and 137 → 219 ms in `lexical`, and S10 goes 147 → 169 ms in
`lexical`. S02 matches 32,640 rows, so the index is a poor choice there. 32 of 50 queries are still
more than 10% faster in each mode. The 200 ms target is not met at this size for `lexical` under
either variant, or for `filter_only` under O2.

## 5. Stress: concurrent clients

**Expectation:** P1 keeps its benefit under contention, and B0 saturates first.

The specification's stress protocol covers W-PIPE, not catalogue search, so this is an additional
owner check. Threads share one `Database`, as handler threads do in one service process. The cap is
4 connections as in the frozen profile, on an alternating `filter_only` and `lexical` workload, 30 s
per level, 3 repetitions. Medians, with rejections summed across repetitions:

| Clients | Variant | Searches/s | p50 ms | p95 ms | p99 ms | Rejected (503) | Violations |
|---|---|---|---|---|---|---|---|
| 1 | B0 | 25.4 | 39.1 | 56.1 | 59.1 | 0 | 0 |
| 1 | O2+P1 | 91.8 | 6.2 | 43.3 | 53.3 | 0 | 0 |
| 8 | B0 | 111.3 | 57.9 | 174.2 | 249.5 | 0 | 0 |
| 8 | O2+P1 | 363.3 | 15.6 | 62.3 | 92.5 | 0 | 0 |
| 32 | B0 | 111.1 | 261.7 | 1,012.2 | 1,533.5 | **39** | 0 |
| 32 | O2+P1 | 370.1 | 62.2 | 300.2 | 486.8 | 0 | 0 |

**Conclusion.** O2+P1 handles 3.3× the load at saturation. At the W-SEARCH concurrency cap of 32, B0
queues past the 2 s wait for a connection and rejects requests, while O2+P1 rejects none. Results stay
correct under load in both. Limits: this is a closed loop with no HTTP layer, the client shares
Python's GIL with the work it measures, and the host has 16 cores where the frozen profile gives the
catalogue 0.5. Treat 3.3× as the comparison, and do not read 370/s as capacity.

## 6. T-06: exact versus HNSW

**Expectation:** HNSW is much faster for some loss of recall.

Same frozen vectors (`all-MiniLM-L6-v2`, 19,998 rows, 183 s to encode), same filters and same query
vectors, raw HNSW with no exact fallback, `m=16`, `ef_construction=64`, `iterative_scan=strict_order`.
Recall@5 is against the exact eligible top 5. 0 hard-filter violations throughout; 46 of 46 queries
used the index.

Vector branch only, database time:

| Group | Exact p50 / p95 | ef=40 p50 / p95, recall | ef=100 p50 / p95, recall | ef=200 p50 / p95, recall |
|---|---|---|---|---|
| All | 19.4 / 32.2 | 2.8 / 56.1, 0.852 | 3.2 / 55.1, 0.906 | 3.8 / 54.8, 0.913 |
| Broad | 21.1 / 58.9 | 2.3 / 3.3, 0.930 | 2.7 / 3.7, 0.947 | 3.2 / 4.6, 0.947 |
| Selective | 18.7 / 25.2 | 3.0 / 36.3, 0.800 | 3.2 / 35.0, 0.871 | 3.8 / 34.5, 0.875 |
| Few | 17.3 / 19.6 | 55.9 / 60.9, 0.733 | 54.8 / 59.1, 0.867 | 54.6 / 60.4, 0.911 |
| Zero | 16.7 / 18.0 | 53.2 / 55.9, – | 52.7 / 55.3, – | 52.1 / 54.5, – |

Underfilled queries, meaning fewer results than exist: 4.9%, 2.4% and 1.6% overall; 33%, 20% and 13%
for the few-results group.

Full search including query encoding, at the service default `ef=100`:

| Metric | R-EXACT | R-ANN |
|---|---|---|
| Client p50 | 66.3 | 64.8 |
| Client p95 | 95.1 | 110.3 |
| Client p99 | 130.6 | 116.7 |
| Rank p50 / p95 | 42.3 / 68.3 | 38.6 / 84.7 |
| Query encoding p50 | 2.3 | 2.3 |

Hybrid top-5 overlap with exact: 0.945. HNSW index: 36.9 MB against a 61.8 MB table, 1.75 s to build.

**Conclusion: the expectation holds for the branch but not for the service.** The branch is 6× faster
at p50, but few-results and zero-results queries are 3× *slower*, at about 53 ms against 17 ms, because
a filtered scan keeps walking the graph looking for matches. In full search the lexical branch and the
filter still run, so p50 is level and p95 is 16% worse, while recall drops and 60% more storage is
used. **Keep exact retrieval at this catalogue size.** If R-ANN runs officially, use `ef_search=100`;
`ef=200` adds only 0.007 recall. This does not rule out HNSW on a much larger catalogue: the 10×
fixture has no vectors, so that was not measured.

## 7. W-ANALYTICS: F-COMPACT and F-PARTITION

**Expectation:** compaction helps queries that touch many Silver files. Partitioning helps only
queries with a date or type filter.

**Synthetic fixture:** seed 42, 300 publications, 60,218 events, built through the real Bronze, Silver,
Gold and publisher code. Warm cache, 3 warm-ups and 30 executions per query, 3 repetitions. All three
layouts returned **identical results for every query**. The candidate was published through Vichitr's
`publish_candidate` as generation 301.

| Layout | Files | Bytes | Median file |
|---|---|---|---|
| Small files | 11,146 | 314.3 MB | 28.2 KB |
| Compacted, partitioned | 91 | 21.2 MB | 86.1 KB |
| Compacted, unpartitioned | 7 | 15.2 MB | 6.6 KB |

| Query | Small files p50 ms | Compacted p50 ms | Unpartitioned p50 ms | Files opened (small / compacted / unpartitioned) |
|---|---|---|---|---|
| Q1 | 988.1 | 10.1 | 7.5 | 11,090 / 49 / 1 |
| Q2 | 3.1 | 1.7 | 1.1 | 7 / 7 / 1 |
| Q3 | 3.7 | 2.0 | 1.8 | 7 / 7 / 1 |
| Q4 | 3.8 | 2.0 | 1.8 | 7 / 7 / 1 |
| Q5 | 188.9 | 8.2 | 8.5 | 1,585 / 7 / 1 |
| Q6 | 1,082.0 | 45.9 | 42.3 | 11,090 / 49 / 1 |

**F-COMPACT.** Adopt: Q1 is 98× faster and Q6 24× faster, with 93% less storage, in 24 s of compaction
for Silver. Q2–Q4 read the same 7 files and the same bytes in the small-file and compacted layouts, so
their roughly 1.5 ms difference does not come from those files and is **not claimed as a gain**.

**F-PARTITION.** On Q5, partitioning selects 2.7 MB of files against 13.5 MB and reads 0.36 MB against
2.07 MB, yet warm latency is the same (8.2 ms against 8.5 ms). Unpartitioned is slightly faster on Q1
and Q6. So partitioning saves I/O and gives no warm latency benefit at this size. A cold-cache series
is where it could matter, and that is **NOT_RUN**.

**Limit.** The 32 MiB target file size was never reached, because this fixture holds only 21 MB. This
tests small-file overhead, not behaviour at the target size.

## 8. Search quality (NDCG@5)

The labels are **rule-derived, not manual**, so read
[relevance_labels.md](relevance_labels.md) before quoting these.

| Mode | Dev (23) | Dev without same-label queries (21) | Held-out (13) | Held-out without same-label queries (10) |
|---|---|---|---|---|
| `filter_only` | 0.237 | 0.165 | 0.342 | 0.145 |
| `lexical` | 0.924 | 0.917 | 0.754 | 0.680 |
| `hybrid_exact` | 0.913 | 0.904 | 0.811 | 0.755 |
| `hybrid_ann` | 0.848 | 0.834 | 0.852 | 0.807 |

`filter_only` has no relevance ordering, so it shows what an arbitrary order scores. `lexical` and
`hybrid_exact` clearly beat it. **No ranking between `lexical`, `hybrid_exact` and `hybrid_ann` is
claimed:** they swap places between dev and held-out, with only 10 to 23 queries in each column, and
7 of `hybrid_ann`'s 192 results are unjudged and count as 0.

## Reproducing

```bash
export CATALOG_DATABASE_URL=postgresql://...  ANALYTICS_DATABASE_URL=postgresql://...
export EMBEDDING_MODEL_DIR=artifacts/models/all-MiniLM-L6-v2
python -m pipelines.catalog.experiments import --out artifacts/experiments/w-import
python -m pipelines.catalog.experiments search --out artifacts/experiments/w-search
python -m pipelines.catalog.experiments stress --out artifacts/experiments/w-search-stress
python -m pipelines.catalog.experiments search --out artifacts/experiments/w-search-10x \
    --scale 10 --variants B0,O2 --executions 10
python -m pipelines.catalog.ann_experiment --out artifacts/experiments/w-ann
python -m analytics.queries.experiment --out artifacts/experiments/w-analytics
```

Each `summary.json` records the commit and whether the tree was clean. `query_results.parquet` holds
the raw timings and returned SKUs, and `plans/` holds `EXPLAIN (ANALYZE, BUFFERS)` per query.
