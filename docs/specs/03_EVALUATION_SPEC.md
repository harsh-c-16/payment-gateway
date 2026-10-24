# Evaluation and evidence specification

Version 2.0 | Performance values below are planned inputs or targets; measured CSV observations are identified in file 08

Read 02_COMMON_SPEC.md for system semantics. Jaineel owns the runner and independent oracle. Each experiment has a named implementation owner and a second-person reviewer. 09_EVALUATION_RUNBOOK.md defines the exact CLI, fixture/test matrix, output schemas and commands to implement/run. 08_DATASET_PROFILE_AND_RULES.md defines source expectations and import contracts.

## 1. What the project must demonstrate

A correct B0 baseline; evidence of its bottleneck; at least three independently evaluated data-engineering changes; a combined candidate chosen using those results; and stress/failure tests showing the correctness retained and the costs incurred.

Required engineering axes are CSV loading/normalization, sink batching, catalogue indexing, partition/consumer scaling and Parquet layout/compaction. ANN is a retrieval-system extension with a recall constraint. Model comparison is not required.

A neutral or negative result is valid. For example, “three partitions did not help because one hot SKU carried 80% of events” is a useful engineering result when backed by per-partition lag and CPU evidence.

## 2. Workloads: do not mix their conclusions

| ID | Purpose | Fixed workload |
|---|---|---|
| W-IMPORT | Measure finite catalogue ingestion | Original 20,000-row CSV, rules flipkart-v1; expected 19,998 canonical rows and 19,920 active candidates; I0/I1, same 1,000-row staging commits and atomic promotion; no LLM/embedding job |
| W-PIPE | Isolate ingestion/Silver/Gold | 500 unique valid STOCK_UPDATED events/s, uniform over a frozen 10,000-key subset selected from the sorted active SKU manifest using seed 42; about 1 KiB/event, source_service=benchmark, metadata.synthetic=true. No live model/catalogue/transaction service required during the timed run |
| W-QUALITY | Verify mutually exclusive dispositions | 100,000 new Kafka records: 98,500 unique valid events, 1,000 byte-identical duplicates of earlier valid events at new offsets, 500 invalid records |
| W-SEARCH | Isolate retrieval/indexing | Original 19,998-listing catalogue, 19,920 active candidates with seeded stock; 50 fixed queries at 20 requests/s, concurrency cap 32. filter_only and lexical are separate B0/O2 series; optional hybrid/ANN uses frozen embeddings and separate results |
| W-CHECKOUT | Measure transaction path | 10 accepted checkout submissions/s after quote preparation; fixed cart templates; 95% deterministic payment success and 5% definitive decline; initial stock high enough to avoid accidental exhaustion |
| W-INTEGRATED | Verify application effects under shared resources | 10 fixed-workflow sessions/s: search, add one line, quote, explicit confirmation, checkout, observe final status; 95/5 payment outcome rule; all generated events flow to Gold |
| W-ANALYTICS | Compare file layouts | Frozen Silver/Gold snapshot, exact same rows and query suite before/after layout change; larger labelled fixture if the normal run produces too little data |
| W-AGENT | Secondary minimal-call comparison | Same 60 human-reviewed scenarios and backend snapshot; fixed (0 generative calls) versus optional assist (at most 1 fallback call/turn); all core DE runs use fixed; live model results optional, never part of streaming throughput |

W-PIPE measures a synthetic event-processing path, not 500 complete checkouts per second. It produces no real payment or conversion measurements. W-INTEGRATED supplies realistic mixed-domain events and business reconciliation.

At G0, Harsh gives Jaineel/Aditya the catalogue, active-SKU and facet manifests; Aditya owns simulated stock seeding and its manifest. Harsh does not assign actual stock from the CSV. Jaineel makes canonical workload templates with stable scenario IDs. Each trial instantiates fresh UUIDs, namespace and timestamps, but preserves the same logical template and schedule. Save both the logical fixture checksum and the exact emitted record/request journal. Pair baseline/variant repetitions using the same template seed, not uncontrolled new traffic.

W-QUALITY invalid rows: 100 invalid JSON/UTF-8, 100 missing required fields, 100 wrong types/negative quantity, 100 unsupported schema/version, 100 key/timestamp mismatch. Record exact subcases in its manifest. Same-ID/different-payload collisions are a separate adversarial fixture so they do not invalidate the 98,500/1,000/500 arithmetic.

For W-SEARCH, use the 50-query/30-development/20-held-out fixture in runbook §6 and label relevance 0–3 manually before final comparisons. Use 20 broad, 20 selective, 5 zero-result and 5 under-five-eligible queries; record actual eligible fractions on this nonuniform real catalogue. Include nulls, inactive prices, unclassified categories and the four verified apparel-size cases. Never invent attributes to fit a desired selectivity. Rotate query order reproducibly. Freeze candidate pools and report unjudged-result coverage; no unreviewed LLM relevance labels.

For W-CHECKOUT and W-INTEGRATED, payment outcome/delay is determined from the stable scenario ID and seed, not runtime UUID or wall time. Core provider delay is 100 ms; failure/expiry tests deliberately override it. Cart quantity=1 in performance trials. Initial stock=10,000 per participating SKU, reset each repetition.

## 3. Baseline and independent variants

**B0** retains all validation, primary keys, integrity indexes, outboxes, retries, ledger rules, raw preservation and instrumentation.

| Variant | Only intended change | Workload | Owner |
|---|---|---|---|
| B0 | One partition per domain topic; one analytics consumer; sink transaction batch size=1; filter_only/lexical exact baseline (mode fixed within pair); no optional catalogue B-tree/HNSW; small-file output | All relevant suites | All; Jaineel runs |
| I0 / I1 | Parameterized row INSERT vs COPY into the same catalogue staging table; same 1,000-row commit chunks, normalized rows, constraints and promotion | W-IMPORT | Harsh |
| O1 | Sink batch max=100 rows or 50 ms from first pending row, whichever first | W-PIPE, then W-INTEGRATED | Vichitr |
| O2 | Add products(namespace,category,price_minor) B-tree with namespace fixed; analyze statistics; all other retrieval logic unchanged | W-SEARCH, then W-INTEGRATED | Harsh |
| O3 | O1+O2; historical label retained, not assumed best | W-INTEGRATED | Jaineel coordinates |
| P10 | 1 partition, 1 consumer | W-PIPE | Vichitr |
| P30 | 3 partitions, 1 consumer | W-PIPE | Vichitr |
| P33 | 3 partitions, 3 consumers in the same group | W-PIPE | Vichitr |
| F-COMPACT | Same pinned snapshot reorganized toward 32 MiB compressed files; same logical partition keys and codec | W-ANALYTICS | Harsh |
| F-PARTITION | Same logical facts, same target file size/codec; unpartitioned vs date/type-partitioned files | W-ANALYTICS | Harsh |
| R-EXACT / R-ANN | Optional paired hybrid_exact vs hybrid_ann; same embedding/lexical/filter/RRF logic, only vector index/search changes | W-SEARCH | Harsh |
| A-FIXED / A-ASSIST | Rules-only vs same rules with optional one-call ambiguous-intent fallback; template responses/backends unchanged | W-AGENT | Jaineel |
| C-BEST | Combine only improvements justified by independent results and their interaction tests | W-INTEGRATED plus applicable stress suites | All |

P10/P30/P33 are separate deployments with new topics; do not increase partitions midstream and assume per-key history stayed ordered. Keep total consumer CPU/memory budget equal across P10 and P33, splitting it between workers. Run a separately labelled “more resources” experiment only if needed.

O1 changes sink transaction size, not raw capture chunking, producer compression, Gold publication interval, validation, polling cadence or durability. Keep those fixed. O2 need not improve W-PIPE; if measured there as a negative control, predict no direct benefit.

Suggested small tuning extension after O1: batch sizes 10/100/500 with max waits 10/50 ms. Use a bounded subset chosen after bottleneck inspection; do not run a huge parameter grid before establishing the baseline.

ANN defaults for the first comparison: HNSW m=16, ef_construction=64, ef_search in 40/100/200, explicit iterative scan setting. Record installed-version support at G0. Report raw ANN without exact fallback first; report fallback-enabled retrieval separately. Never change embeddings while comparing indexes.

## 4. Reproducible run protocol

1. Freeze code commit, application lock, image digests, model revision, event/dictionary schemas, fixture checksum and exact configuration.
2. Use the proposed local profile of **4 total SUT CPU cores and 8 GiB total SUT RAM** on SSD. This is a proposed experimental budget, not a claim about the user’s machine. Set enforceable container/cgroup limits, not just a note in a report. Record host CPU model, physical cores, RAM, OS/WSL2 version, storage and available limits.
3. Place generator/observer outside the SUT limit when possible and record its resource use separately. If the host cannot reserve this budget, select and freeze a smaller feasible profile, label it honestly, and rerun every comparator on that profile.
4. Declare all running services, workers, connection pools and allocations. The pipeline-only profile differs from the integrated profile; results cannot be compared as if hardware interference were identical.
5. Start a fresh run namespace, migrate, seed and verify initial checksum/stock. Create topics and consumer groups with known initial offsets. Reset only that run’s data. Do not reset the user’s working data.
6. Warm up for 60 seconds, then measure for 600 seconds. Keep both phases tagged. Do not include setup, image download, model download or embedding construction in steady-state latency.
7. Generate work on an open-loop schedule independent of response time. Record scheduled_at, actual_send_at, broker/API acknowledgement, admission failure and scheduling delay. Bounded client queues must expose missed emissions; they may not silently lower the requested rate.
8. Stop new emissions after the measurement window, then drain for at most 120 seconds. Save both measurements at the cutoff and final reconciliation after drain. A longer recovery experiment has its own declared deadline.
9. Reconcile every planned request/record, every source disposition and every logical effect. Incomplete events are failures/unresolved items, not discarded latency samples.
10. Repeat three times per required variant using paired logical fixtures. Randomize variant execution order with a recorded seed to reduce machine/cache/order bias. Retain all three runs.
11. Report each run and the median plus min–max of per-run summaries. Three repetitions are descriptive evidence, not strong statistical significance.
12. Warm-cache timings are the main query series. A cold-start/cache series, if run, is separate. Do not flush caches for one variant and not its comparator. Never silently mix warm and cold measurements.

No performance “pass” may be claimed from a 10-second smoke test. Smoke tests verify setup only. W-IMPORT, W-QUALITY and W-AGENT are finite-job exceptions; W-ANALYTICS uses fixed repeated queries. Their exact repetition/timing rules are in runbook §5; do not pad finite work to 600 seconds or use a false duration denominator.

## 5. Metric dictionary

### 5.1 Pipeline and loading

| Metric | Exact definition | Measurement / caveat |
|---|---|---|
| Import end-to-end time | Completed catalogue/manifest readiness minus first raw-file open | Include read/archive, parse/normalize/select, staging and promotion/export; exclude inventory and optional embeddings; equal cache/archive state |
| Import throughput | Raw observations / total seconds; canonical rows / staging seconds separately | Label numerator/boundary; duplicates/inactive rows are not silent losses |
| Dataset completeness | Known values per field / canonical rows, also by category | Do not equate missing optional facets with rejected products; report raw and canonical counts separately |
| Import disposition conservation | raw = canonical_active + canonical_inactive + superseded + mandatory_rejected | For this file: 20000=19920+78+2+0; issues overlap and are separate |
| Offered rate | Planned emissions during measurement / 600 s | Based on the schedule, not successful sends |
| Admitted rate | Kafka delivery acknowledgements or accepted HTTP operations / 600 s | Declare which boundary; count timeouts/unknown admissions separately |
| Gold goodput | Unique valid measurement-cohort event IDs made visible in active Gold during the measurement window / 600 s | No duplicates, quarantine, or post-window drain completions in numerator |
| Cohort completion | Unique valid cohort IDs visible by drain deadline / expected unique valid cohort IDs | Report missing IDs and completions after cutoff |
| Producer-to-Gold latency | gold_visible_at - produced_at for each unique valid event | Includes outbox waiting when that path is used; excludes no slow completed events |
| Schedule-to-Gold latency | gold_visible_at - scheduled_at | Exposes generator-side queueing/coordinated omission |
| Broker-to-Silver latency | silver_committed_observed_at - broker_ack_at where correlated | Diagnostic; source records retain broker coordinates |
| Outbox delay | broker_ack_at - produced_at for outbox-produced events | Includes relay/publishing delay; no timestamp reset |
| Gold publication delay | gold_visible_at - silver_committed_observed_at | Detects exporter bottleneck hidden by low Kafka lag |
| Kafka lag | For a consumer group, sum over its partitions of log-end next offset minus committed next offset | Sample every 1 s; report time series, peak, mean, end, per-partition values |
| Peak pending export | Maximum unique events durable in staging but not in active Gold | Required because committed offsets do not prove Gold freshness |
| Outbox backlog | Pending rows and age of oldest pending row per service | Separate from Kafka lag |
| Drain time | After a fault is removed, time until lag <= pre-fault baseline+max(10,1% of offered rate), and pending export/outbox return to baseline, continuously for 5 s | Timeout is reported, not censored |
| Late correction latency | Corrected manifest visibility - late record ingress | Separate from original event’s age |
| Projection freshness | post-commit projection observation - stock event produced_at, for each applied newer version | Final source/projection versions must reconcile |
| Replay throughput | Unique valid records reconstructed / total replay elapsed seconds | Includes transform and publication; excludes no failures |

Calculate p50, p95 and p99 from raw event/request durations using one recorded quantile method (nearest-rank: ceil(q×n), 1-indexed). Keep sample count. Report completed-only quantiles **alongside** unresolved count/percentage; if more than 1% remain unresolved, the complete-cohort p99 is not established. Never report completed-only p99 as an unconditional SLO result.

Do not use historical event_time as the live producer latency origin. Do not subtract monotonic timestamps from different machines. The required profile uses one host clock; multi-host trials require clock-offset measurement and a reported error bound.

Commit-observation times are conservative upper-bound measurements including acknowledgement overhead. Missing timing samples invalidate the associated latency claim until explained; they cannot be replaced with zeros.

### 5.2 Resources and storage

| Metric | Definition |
|---|---|
| CPU utilization | Delta process/container CPU seconds / (elapsed wall seconds × allocated cores) ×100; specify worker, database, broker or full SUT |
| Memory | Peak RSS MiB per process; sum at the same sampled timestamp for aggregate process RSS; additionally report cgroup memory peak including its different accounting |
| Queue memory | Pending record count and byte size; report bounded limit and saturation |
| Disk/write cost | Bytes written, index bytes and outbox/WAL growth if measured; use matching counters per variant |
| Selected file bytes | Sum of sizes of files selected by the manifest/query plan; this is an estimate of candidate scan volume |
| Actual read bytes | Reader/I/O counter bytes, only when measured; cache and compression affect interpretation |
| File count/opens | Active files and opened files for each query |
| Index build/update cost | Build time, size, and price-update throughput/latency at the same mutation workload |
| Query latency | Client wall time for a fixed query/result, with generation, cache state and row count |

Compaction may not reduce actual bytes read. Report the outcome rather than assuming it. A 32 MiB target is a chosen experiment parameter, not an industry-optimal constant.

### 5.3 Transaction and retrieval correctness

| Metric | Formula / condition |
|---|---|
| Duplicate debit effects | More than one debit entry for the same logical payment attempt or order; required 0 in this one-purchase-per-order simulator. Reversing a duplicate does not erase the duplicate-effect failure |
| Oversell | Any negative available/on_hand, reserved>on_hand, or sold quantity exceeding opening+replenished stock; required 0 |
| Cancellation reconciliation | Every terminal cancelled order has no committed sale and net debit 0 |
| Confirmation reconciliation | Every confirmed order has committed stock and exactly one net successful debit equal to total |
| Hard-filter violation rate | Hits violating any specified hard constraint / returned hits; required 0 |
| Vector recall@k | Intersection of vector ANN top-k with exact eligible vector top-k / min(k,eligible count); exclude zero-eligible queries and report them separately. Compare branches before RRF; final hybrid top-5 overlap with hybrid_exact is a separate metric |
| Underfilled rate | Queries returning fewer than min(k,eligible count) / queries with eligible results |
| NDCG@5 | DCG=sum((2^relevance-1)/log2(rank+1)); divide by ideal DCG for same labels; no-positive-label queries reported separately |
| Intent macro slot F1 | Per-slot F1 across category,size,colour,material,max_price_minor,occasion, then unweighted mean across the original six slots; brand/path extension reported separately; no eligibility-based alteration of user labels |
| Retry amplification | Total physical command calls / logical operations |
| Compensation completion | Cancelled-and-reconciled outcomes / compensation-required scenarios, plus latency and unresolved cases |

For slot F1, a wrong non-null value is one FP and one FN for that slot; missing expected value is FN; unexpected supplied value is FP. True-null matches are TN and do not inflate F1. A slot with no positive labels must be reported and excluded with explanation or the label set fixed beforehand.

Secondary targets from the labs: full retrieval API p95 <200 ms for the declared mode (including query embedding when used), NDCG@5 >=0.70 and intent macro slot F1 >=0.90. Database-only ranking latency is a separate metric, never substituted for full API latency. State measured confidence/coverage and labelled sample sizes. An F1 failure does not justify changing event/pipeline correctness.

### 5.4 Assistant and inference cost

Generative calls per turn = total actual provider attempts / all attempted turns; also report per eligible fallback turn and per successful task. Count timed-out/failed calls and hidden SDK retries. Fixed mode and every structured cart/quote/checkout/status action require exactly zero generative calls; assist allows at most one for ambiguous intent, no repair/retry/response-composition call. A budget violation fails correctness even when latency is low.

Report zero-call share, fallback share, valid intent rate, correct/unnecessary clarification rates, task success, dependency failures, actual tokens if returned, and separate parse/LLM/search/compose/total p50/p95/p99 from raw per-turn durations. A fast clarification does not count as a successful recommendation unless expected. Missing provider usage is null, not invented zero. Local document/query embedding counts and latency are separate from generative LLM usage. Primary pipeline and index comparisons run with no generative provider and no result/intent/query cache.

### 5.5 Provisional engineering targets

At 500 valid events/s: p95 producer-to-active-Gold <=1,000 ms; projection p95 <=1,000 ms under the separately declared update workload; no unresolved valid data after drain; no unexpected invalid data in the clean fixture; zero duplicate logical effects.

These are targets to test. A controlled invalid fixture intentionally has 0.5% quarantine; “DLQ below 1%” is not a meaningful correctness rule for arbitrary dirty input. In W-QUALITY, all 500 invalid records must be quarantined, all 98,500 unique valid events accepted, and all 1,000 duplicate deliveries suppressed.

## 6. Bottleneck diagnosis before tuning

Record an initial B0 trace and answer:

- Is backlog before Kafka (outbox), in the consumer (lag), in sink transactions, or after offset commits (pending Gold publication)?
- Does a database plan scan many rows, spend time waiting for locks, or write too many tiny transactions?
- Is one hot partition saturated while others are idle?
- Do queries spend time opening small files, reading columns/row groups, or sorting?
- Is the generator itself late or CPU-bound?

Use stage timers, database plans, per-partition lag, CPU/RSS and file-open evidence to select the next hypothesis. Do not infer the bottleneck from end-to-end p95 alone.

For each experiment, write before running: hypothesis, changed parameter, fixed controls, expected mechanism, correctness constraints, and trade-off metrics. After running, record whether the evidence supports the hypothesis.

## 7. Test register mapped to the tracker

| ID | Scenario and assertion | Lead / reviewer | Required evidence |
|---|---|---|---|
| T-01 | Event contract and measured ingress: valid wire format, registry/key rules, stage timings and load accounting | Vichitr / Jaineel | Schema fixtures, actual admitted/offered rates, receipts |
| T-02 | B0 vs O1 batching; identical accepted IDs and Gold totals; bounded 50-ms flush timer | Vichitr / Jaineel | Three paired runs, batch-size/timer logs, reconciliation |
| T-03 | 100,000-record cleaning fixture; duplicate conflicts, nulls, unknown version and UTC boundaries as separate cases | Vichitr / Jaineel | Disposition ledger, independent expected counts and hashes |
| T-04 | Lineage and analytical scans/compaction; Q1–Q6 return identical logical results | Harsh / Vichitr | Plans, file manifests, before/after digests, query timings |
| T-05 | P10/P30/P33, load escalation, 80% hot key and consumer pause/rebalance | Vichitr / Jaineel | Per-partition lag, resource profiles, drain/capacity result |
| T-06 | B-tree and exact/ANN comparison; selectivity, hard-filter checks, recall and index cost | Harsh / Jaineel | Fixed query/label hashes, plans, raw ranks/times |
| T-07 | Relay crash after publish before mark; sink crash after commit before offset; duplicate restart delivery | Aditya + Vichitr / Jaineel | Hook barrier logs, broker records, one final logical effect |
| T-08 | 100 concurrent buyers for one unit; multi-SKU partial failure; commit-vs-expiry race; late payment and response loss | Aditya / Jaineel | Stock/reservation/ledger audit; no oversell or duplicate debit |
| T-09 | Projection receives v3 then v2 then duplicate v3; conflicting v3; restart and bootstrap | Harsh / Aditya | Applied/stale/conflict counters; final authoritative comparison |
| T-10 | Zero-call fixed vs optional one-call assist; validated slots, honest no-results, explicit checkout confirmation, same backend | Jaineel / Harsh | Scenario outcomes, model/prompt revisions, tool/token/latency logs |
| T-11 | Stop analytics for 30 s while checkout continues; separately stop Kafka for 30 s | Jaineel / Aditya + Vichitr | Checkout outcomes/latency, outbox accumulation, later reconciliation |
| T-12 | Isolated replay twice, late-data corrections and publication/compaction crashes | Vichitr / Harsh + Jaineel | Equal logical totals, original operational state unchanged, manifest history |

Additional D-01–D-05 tests in runbook §3 cover this actual CSV, deterministic normalization, import resume/idempotency, I0/I1 loading and LLM call-budget enforcement. They are required where marked, not optional documentation.

T-08 detailed cases:

1. Start on_hand=1,reserved=0. Submit 100 distinct order reservations for that SKU concurrently. At most one reservation succeeds; every other response is a declared stock conflict. If the winner pays and commits, final on_hand=0,reserved=0.
2. Send 100 copies of the **same** reservation key. Exactly one logical hold exists; this differs from 100 distinct buyers.
3. Multi-SKU cart with one unavailable SKU must reserve nothing.
4. Force payment success after the reservation expires. Final order is cancelled and net debit=0, or payment was cancelled before success. Never confirmed.
5. Crash after committed stock but before order confirmation. Recovery confirms forward once; does not release committed stock.
6. Lose payment/commit HTTP responses. Retry same keys; no second effect.
7. Race delayed reserve against release tombstone, and delayed success against payment quiescence.
8. Crash during compensation. Resume to reconciled cancellation or explicit unresolved state; no false terminal success.

T-12 publication cases: crash before file rename, after durable file before manifest, before pointer commit, after pointer commit; stale compaction candidate while ingestion publishes; replay of a raw invalid record; late fact >120 seconds; arrival of payment facts before order-created facts.

## 8. Stress and capacity protocol

After B0 and candidate correctness passes, run W-PIPE at 500, 1,000 and 2,000 events/s. Attempt 5,000 only if the generator and previous tiers remain valid. A failure at 500 is a result to diagnose, not permission to skip to larger traffic.

A sustainable tier must, for all three repetitions:

- Admit the planned load without unreported losses; actual admission >=99% of requested load and scheduling lateness is reported.
- Have zero unexpected loss/duplicate effects and all valid cohort records reconciled after drain.
- Meet the declared latency SLO, or be explicitly labelled a capacity-without-SLO result.
- Show final-five-minute lag slope <=1 record/s and end lag <=max(100,2×offered_rate), with no rising pending-export/outbox backlog.
- Remain within fixed memory/CPU budgets without OOM or continually growing queues.

“Maximum sustainable rate” is the largest **tested** tier meeting those rules, not an interpolated universal maximum.

Hot-key test: 80% of events use one SKU key, remaining 20% uniformly use others. Never salt an inventory key just to improve the graph; doing so changes its ordering/state model. Explain idle consumers and skew concentration.

Pause one consumer process for 30 seconds at measurement second 180, allow normal rebalance behavior, then restore it. Also test a worker kill/restart at a named durable boundary. Keep input running. Save fault timestamps and lag-drain times.

Analytics stall test: stopping downstream analytics should not cause immediate checkout failure while local databases/outboxes have capacity. Compare latency degradation and shared-resource interference. “Decoupled” does not imply no CPU/disk interference or unlimited outage tolerance.

## 9. Independent oracle and run artifacts

The oracle uses fixture manifests and public read-only audit snapshots, not the production Gold reducers. For synthetic stream facts it can calculate expected counts and version maxima in a simple offline implementation. For transaction tests it independently reconciles quotes, order status, reservation state, inventory conservation and signed ledger entries.

Required run directory: benchmarks/results/<run_id>/.

| Artifact | Required content |
|---|---|
| manifest.json | run_id, workload_id, variant, repetition, seed, git commit, dirty flag, exact locks/digests, hardware/resources, namespace, topics/partitions/groups, start/end, source SHA, dataset/rules/dictionary/query hashes, selected SKU manifest, simulation/scale flags, search/assistant mode, parameters, fault schedule |
| emissions.jsonl | stable scenario ID, event/request ID, scheduled/send/ack times, outcome/error, source coordinates if acknowledged |
| timings.parquet | per-ID stage timestamps/durations, visibility generation, cohort tag, timing validity and recovery-upper-bound flag |
| lag.csv | UTC timestamp, group, topic, partition, log-end next offset, committed next offset, lag |
| resources.csv | time, component, CPU seconds/allocation, RSS, cgroup memory, disk counters if available |
| correctness.json | expected/observed counts, missing/conflicting/unexpected IDs, stock/ledger/Gold checks, passed boolean and reasons |
| plans/ | Relevant EXPLAIN ANALYZE/BUFFERS outputs and index inventory |
| manifests/ | Input, Bronze, active Silver/Gold and compaction manifests |
| faults.jsonl | barrier name, target, namespace, injected_at, recovered_at, observed state |
| summary.json | Metric names, units, values or null, sample counts, status=MEASURED/INCOMPLETE/NOT_RUN, artifact references |
| comparison.md | One paired comparison’s hypothesis, results, uncertainty, costs and conclusion |

Do not embed secrets in manifests. An “actual result” may only be generated from these artifacts. Before runs, summary values are null with NOT_RUN.

Proposed runner contract: run_experiment(workload_id, variant_id, repetition, seed, namespace, duration_seconds, warmup_seconds, fault_profile) → RunArtifactManifest. compare_runs(baseline_run_ids, candidate_run_ids) → ComparisonReport. Both validate matching controls and refuse silently incomparable runs.

## 10. Reporting rules and final tables

For a lower-is-better metric, improvement percent = (baseline - candidate)/baseline ×100. For throughput, gain percent = (candidate - baseline)/baseline ×100. For baseline zero, percentage change is undefined; report absolute change. A memory increase is a cost even when latency improves.

Final comparison columns: workload, variant, actual offered/admitted rate, goodput, p50/p95/p99 Gold latency, peak/end lag, pending-export peak, CPU, peak memory, correctness outcome, repeated-run spread and evidence path. Search and file-layout tables have their own recall/selectivity/read-byte columns rather than unrelated blank pipeline metrics.

Additional dataset/import/query/assistant/test/audit artifacts are specified in runbook §7. Null/NOT_RUN values are mandatory until the corresponding benchmark actually executes. The measured CSV profile does not satisfy a performance test.

Required plots once actual data exist: latency versus offered rate; lag over time with fault markers; throughput versus CPU/memory; query latency/file opens before/after compaction; ANN recall versus latency. Do not create plots containing the sample lab numbers.

Each person writes a short engineering conclusion: what bottleneck existed, which change addressed it, what evidence shows causation, what cost increased, and what workload/hardware limits the conclusion. Jaineel combines them without claiming all optimizations improve all metrics.

