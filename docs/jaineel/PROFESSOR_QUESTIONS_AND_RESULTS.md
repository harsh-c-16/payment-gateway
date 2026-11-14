# Professor demo: questions, tests and measured evidence

Generated from retained raw observations on 2026-11-14T16:31:36.725085+00:00.

## What we can defend

- Keep summaries **alongside** audit/replay data. The new experiment tests the space/query trade-off, not a production deletion policy.
- Index choice depends on predicates and physical layout. B-tree, hash, BRIN and GIN were measured separately; no single index wins every workload.
- The seven previously executed real pipeline cases were rechecked from saved evidence. Existing transaction recovery cases and the new refund attempt are listed separately below.
- Current focused correctness suite: **234 passed, 0 failed, 0 errors, 0 skipped**. These counts establish correctness coverage, not throughput.

## Measurement scope and controls

Evidence: `artifacts/defense/20261114-professor-final`. Seed 42; three randomized repetitions, three warmups and 10 timed calls per query/method/repetition. Tables show the median of three repetition medians; raw samples, p95, all repetition medians, plans and hashes are in defense-report.json.

Original CSV: 20,000 observations, 19,998 canonical listings, 19,920 active. The probe reuses production normalization/selection and preserves unknown categories. It measures a **title/category/price projection**, not the production search API, stock joins, hybrid ranking or embedding inference.

PostgreSQL: pinned image, 1 CPU, 512 MiB limit, 256 MiB tmpfs; durability settings enabled. DuckDB: one thread, 64 MiB query memory. Host: 13th Gen Intel(R) Core(TM) i5-13420H, Windows, 15.6 GiB RAM. Pre-existing Docker containers: 0. Host background activity and warm RAM-backed SQL timings limit generalization. **Not formal P9, SSD, cold-cache, stress-capacity or end-to-end latency evidence.** No production index changed.

## Q1. Why retain summaries instead of simply deleting old entries?

Controlled DuckDB example: 20,000 synthetic immutable events became 1,336 minute/type summaries. Same Zstandard codec: raw **93,828 bytes**, summaries **3,009 bytes** (96.79% fewer bytes). Counts and integer monetary sums match an independent Python oracle in every trial.

| Aggregate query | Rep 1 median ms | Rep 2 | Rep 3 | Median ms |
|---|---:|---:|---:|---:|
| raw | 2.585 | 2.265 | 3.119 | 2.585 |
| summary | 2.805 | 3.083 | 2.061 | 2.805 |

One-off rollup construction: 34.701 ms. Rollup query latency was 8.51% higher in this small warm experiment. Do not infer latency from the space saving alone. Compression, workload and scale matter.

Counterexample: histories `(E1=100,E2=200)` and `(E1=200,E2=100)` both have count 2 and sum 300, but disagree on each event's amount. A rollup cannot recover exact lineage, diagnose a wrong debit or reconstruct arbitrary new queries. Compaction preserves rows; aggregation deliberately loses detail.

**Current policy:** Kafka/published outbox default 7 days; Bronze, dedup keys, manifests and evidence at least 30 days and until evaluation acceptance, whichever is later; replay references block deletion. Cleanup is explicit and disabled during experiments. FileStore.list_orphans inventories files; it does not delete them. No summary-only purge or production TTL was introduced by these tests.

## Q2. Can we delete old deduplication IDs once totals are summarized?

Actual isolated DuckDB policy probe: replaying E1 twice with retained IDs created **1** logical contribution. Deleting its seen-ID before replay created **2**. The second policy is an intentionally unsafe counterexample, not production behavior. Dedup lifetime must cover supported redelivery/replay horizons; old totals alone do not establish whether a replayed ID was already counted.

## Q3-Q5. Why B-tree? Did hash, BRIN or GIN do better?

The integrity primary key remains in every variant. `none` means no additional candidate index. B-tree uses (namespace, category, price); hash uses category equality; BRIN uses category/price with pages_per_range=4; GIN uses a title tsvector. The lexical comparator keeps the same SQL and title vector on both sides. This is a separately labelled extension, not a change to frozen B0/O2 semantics.

| Shuffled physical layout / client query ms | No optional index | B-tree | Hash | BRIN | GIN |
|---|---:|---:|---:|---:|---:|
| category_price | 4.160 | 1.295 | 2.610 | 4.069 | 3.215 |
| category_broad | 3.664 | 1.358 | 2.940 | 3.204 | 2.995 |
| category_rare | 2.650 | 1.071 | 1.028 | 1.374 | 3.211 |
| price_range | 2.733 | 1.426 | 2.771 | 2.472 | 2.680 |
| lexical_shirt | 4.756 | 5.108 | 5.171 | 5.386 | 3.303 |
| lexical_wristwatch | 4.468 | 3.713 | 3.890 | 4.241 | 1.208 |

**Interpretation:** B-tree suits category equality plus price range/order. Hash is an equality comparator, not a range/order replacement. GIN addresses text membership, not price ordering. BRIN summarizes block ranges and depends on correlation. Planner choices were not forced; saved plans show where it chose a sequential scan. The lexical wristwatch query is a zero-hit case (see plan Actual Rows), so its speed does not establish positive-hit ranking quality. All response digests are identical across variants and layouts.

[PostgreSQL index capabilities](https://www.postgresql.org/docs/18/indexes-types.html) and [multicolumn ordering](https://www.postgresql.org/docs/18/indexes-multicolumn.html) explain the mechanisms; the numbers above come from our own experiment.

### Does sorting the data change the BRIN result?

| Price-range count / client query ms | No optional index | B-tree | BRIN |
|---|---:|---:|---:|
| shuffled | 2.733 | 1.426 | 2.472 |
| price_sorted | 2.536 | 1.387 | 0.748 |

Sorting/rewriting cost is not included in these read times. Do not claim a free BRIN improvement or cluster the live catalogue based on this probe.

## Q6. What do the indexes cost to build and maintain?

Median of three shuffled-layout trials. The write probe updates the same 100 prices inside a rollback-only transaction; WAL is still generated. It measures the UPDATE statement, not commit/fsync latency. Vacuum/analyze follows every variant; write probes and rollback can affect physical pages, another exploratory limitation.

| Additional index | KiB | Build ms | Build WAL KiB | 100-price UPDATE ms | UPDATE WAL KiB |
|---|---:|---:|---:|---:|---:|
| none | 0.000 | 0.000 | 0.000 | 3.875 | 35.562 |
| btree | 424.000 | 25.502 | 376.016 | 3.530 | 45.578 |
| hash | 840.000 | 20.599 | 1393.203 | 3.595 | 41.172 |
| brin | 24.000 | 5.917 | 42.039 | 4.078 | 35.242 |
| gin | 1184.000 | 45.609 | 614.211 | 4.715 | 55.398 |

GIN's text-maintenance cost is **not** established by a price-only update. The experiment neither changes descriptions nor measures mixed write throughput.

## Q7. Why batching, COPY and compaction? Are those comparisons already done?

Existing implementation and tests were reused, not replaced: benchmarks/windows/measure.py compares row INSERT/COPY, batch 1/100, B0/O2 and small-file/compacted Q1-Q6 outputs. Its raw observation journal has **276 observations**, verified against the original manifest hash. The original run status is **FAILED**. Its resource collector failed; the diagnostic report explicitly says NOT QUALIFIED. No percentages from it are promoted into a claim that an optimization is proven.

[Existing Windows protocol](WINDOWS_MEASUREMENTS.md) defines the timed boundaries. The sink comparison excludes Kafka transport/accumulation waiting; SQL indexing excludes HTTP. The existing end_to_end.py runner measures real HTTP/Kafka/active Gold, but a complete newly qualified run is NOT_RUN here. Partition/consumer scaling, stress saturation and full integrated B0/C-BEST also remain NOT_RUN in this report.

[Harsh's owner-run experiments](../harsh/experiments.md) already cover COPY, statistics, B-tree, compaction and exact/HNSW. They are attributed owner results on another host; their raw bundles are absent here. The owner reported ANN recall 0.906 and did not adopt HNSW at this size. This is not a new independently verified ANN result. Do not imply that all alternatives were reproduced locally.

## Q8-Q10. What happens to duplicates, bad data, late events and the last unit?

Retained **real Kafka + owner services + active Gold** runs, originally exercised through the guided browser. Revalidated now from saved checks and observed values; this is evidence reuse, not a claim that seven fresh transactions were executed. Fixture elapsed time includes setup/waits and is not service or end-to-end latency.

| Case | Verified result | Checks | Fixture elapsed s |
|---|---|---:|---:|
| duplicate | 3 deliveries, 2 logical valid IDs, 1 duplicate; one contribution per ID | 4 | 2.937 |
| conflict | Changed contents under same ID rejected as EVENT_ID_CONFLICT | 5 | 2.878 |
| malformed | 1 invalid JSON quarantined; both valid neighbors reach Gold | 5 | 3.862 |
| out_of_order | v2/4 units survives later v1/9 units; stale projection rejected | 6 | 8.959 |
| late_event | Earlier window revised from 1 to 2 events in a newer Gold generation | 7 | 3.874 |
| replay | Original/replay business equality; repeat replay preserves logical effect | 7 | 3.097 |
| race | 2 checkouts, 1 sale, 1 cancellation, 1 matching debit; both orders in Gold | 6 | 11.951 |

The race's debit identity/amount and the stock-version result were additionally recomputed from saved order/ledger/projection facts. Download paths, hashes and run IDs are indexed in defense-report.json. Exactly-once **logical effects** do not mean exactly-once Kafka delivery. Search stock is advisory; Inventory owns reservations.

## Q11-Q12. What if a response is lost, a service crashes, or payment arrives late?

Selected existing real controller evidence is reused below. These are owner API audits, not acceptance based only on HTTP status. Evidence dates and hashes are retained.

| Scenario / mode | Reconciled checks | Original completion UTC |
|---|---:|---|
| analytics/automated | 14 | 2026-11-13T20:22:13.858055+00:00 |
| analytics/manual | 14 | 2026-11-13T20:23:34.481138+00:00 |
| crash/automated | 14 | 2026-11-13T20:22:39.050600+00:00 |
| decline/automated | 13 | 2026-11-13T20:22:24.617287+00:00 |
| late/automated | 16 | 2026-11-13T20:23:18.961319+00:00 |
| retry/automated | 14 | 2026-11-13T20:22:19.449070+00:00 |

**Fresh refund rehearsal: NOT_RUN.** Preparation failed with catalogue HTTP 503 before a checkout was submitted. The existing debit/reversal unit/oracle tests are not substituted for a real refund demonstration.

An uncertain checkout response is retried with the identical request/key/body, not a new purchase. A saga restores stock on cancellation. The ordinary 35-second late-payment case quiesces before debit; it is not evidence that a paid amount was refunded. A refund claim needs one real debit, exactly one matching reversal, cancelled order, restored stock and matching Gold.

Analytics pause/catch-up verifies that checkout can complete independently, then reconciles the exact final order after recovery. Lag=0 alone is insufficient: pending Gold/outboxes and exact active membership are checked separately. This single-broker, single-host prototype does not demonstrate broker replication, host disaster recovery, Byzantine faults or a multi-host network partition.

## Q13-Q14. Can we trust the metrics and the independent checker?

Fresh tests cover hand-computed quantiles/lag/goodput, unfinished denominators, clock qualification, preservation of send identities, changed-control rejection, and deliberate oracle corruptions (duplicate debit, wrong money/state, missing events). Fault doubles are labelled; passing them proves a guard detects a case, not a real outage performance measurement. Unknown/missing timings stay null.

| Probable question | Existing/new executable test coverage |
|---|---|
| What does a summary lose? What if seen IDs expire? | benchmarks.defense.summary_trials; tests/benchmarks/test_defense.py |
| Why B-tree/hash/BRIN/GIN and which bottleneck? | benchmarks.defense.index_trials; raw EXPLAIN ANALYZE BUFFERS plans and update/WAL probe |
| Are all repetitions and negative results retained? | test_defense.py; test_comparison.py; test_windows_measurements.py |
| How are dirty/missing CSV values handled? | tests/catalog/test_normalize.py; original-source conservation in catalogue() |
| Duplicate ID versus conflicting payload? | retained duplicate/conflict runs; test_journey.py; tests/pipelines/test_replay.py |
| Out-of-order/late/replayed events? | retained real runs; test_journey.py; test_replay.py |
| Can two shoppers buy the last unit? | retained race run plus independent saved-ledger checks in defense_report.edge_evidence |
| Lost response, expiry, compensation or refund? | retained owner API audits; test_failure_demo.py; tests/oracles/test_reconciliation.py |
| Why not report low lag as completion? | test_journey.py; test_performance_metrics.py |
| Does the generator hide slow/unfinished requests? | test_scheduler.py; test_metrics.py |
| Can the checker detect deliberately wrong answers? | tests/oracles/test_reconciliation.py; test_failure_demo.py; test_defense.py |
| Does compaction delete history or switch a stale snapshot? | existing test_compaction_live.py/test_publication_live.py; no new Linux durability pass claimed here |

## Commands, evidence and remaining limits

```powershell
.venv\Scripts\python.exe -m benchmarks.defense --out artifacts/defense/20261114-professor-final-new --samples 10
.venv\Scripts\python.exe -m benchmarks.defense_report --run artifacts/defense/20261114-professor-final --junit artifacts/defense/correctness-20261114.xml --refund artifacts/defense/refund-20261114 --out docs/jaineel/PROFESSOR_QUESTIONS_AND_RESULTS.md
```

The first command requires Windows Desktop, the existing pinned image and a fresh output directory. It creates one labelled disposable PostgreSQL container and removes it plus anonymous volumes in finally; its actual removal is verified. No retained prototype database is reset. Raw timings/plans/Parquet stay local under artifacts; reports do not include credentials.

A complete formal comparison still needs quiet fixed resources, the full workload matrix, complete resource/clock evidence and owner review gates. This report intentionally preserves the earlier failed benchmark status and the fresh refund attempt's dependency failure. It does not turn exploratory timings or correctness tests into a production capacity claim. The measurement/report commands do not run CI/CD or change Git history.
