# Evaluation implementation and execution runbook

Version 2.0 | Owner: Jaineel coordinates; module owners implement their adapters

**These are commands and tests to implement, not commands already available.** This pack contains no application code. A coding LLM must create the specified CLI, fixtures, collectors, oracle and output schemas before claiming it ran this runbook. 03_EVALUATION_SPEC.md defines metric formulas and experiment controls; 08_DATASET_PROFILE_AND_RULES.md defines the observed CSV expectations.

## 1. One CLI and reproducible configuration

Implement a Python package entry point `python -m projectctl`. Jaineel owns argument parsing and execution/report orchestration; it delegates environment actions to Vichitr, catalogue actions to Harsh and simulator seeding to Aditya. No four incompatible shell interfaces.

Required subcommands: `env up`, `env down`, `env verify`, `db migrate`, `contracts check`, `catalog profile`, `catalog import`, `catalog verify`, `inventory seed`, `projection wait`, `fixtures build`, `eval run`, `benchmark run`, `benchmark matrix`, `benchmark compare`, `benchmark reconcile`, `report build`. Every subcommand has `--help`; unknown options/config fields fail validation. Destructive namespace cleanup is a separate `env reset --namespace <bench-name>` action that rejects dev/live namespaces. No reset is implicit in a read-only report command.

All paths below are repository-relative. The user places the unchanged CSV at `data/raw/flipkart_com-ecommerce_sample.csv`. Do not commit the source CSV automatically. Config, fixture and result paths contain no secrets. Commands emit structured JSON summaries and an exit status: 0 completed/pass; 2 bad configuration/input; 3 correctness failure; 4 dependency failure or incomplete evidence; 5 completed measurement missing a declared performance target. Preserve artifacts for every failure. An optional unconfigured live-LLM evaluation has status NOT_RUN and is omitted from required-core success, never reported as passed.

Jaineel creates `contracts/evaluation/config.schema.json`, `run.schema.json`, `summary.schema.json` and `fixture.schema.json`. Harsh creates `contracts/data/catalog/*.schema.json`. JSON is canonicalized using sorted object keys, UTF-8, no insignificant whitespace and no nonfinite numbers. Hash manifests excluding their own content_sha256 field; raw-file hashes always cover exact bytes. Ordered arrays stay ordered.

Required `configs/evaluation.yaml` fields:

| Field | Type / required semantics |
|---|---|
| schema_version | Integer 1 |
| profile | Named enforceable SUT CPU/RAM/service/pool allocation and generator allocation; record actual host separately |
| dataset | source_path, expected_sha256, rules_version=flipkart-v1, dictionary_path, dictionary_sha256 after G0, canonical_manifest, sku_manifest |
| workloads | W-IMPORT, W-PIPE, W-QUALITY, W-SEARCH, W-CHECKOUT, W-INTEGRATED, W-ANALYTICS, W-AGENT parameters from file 03; explicit required/optional status |
| variants | B0/O1/O2/O3/P10/P30/P33/F-COMPACT/F-PARTITION/I0/I1 and optional R-EXACT/R-ANN and A-FIXED/A-ASSIST; complete resolved config plus permitted difference from baseline |
| timing | warmup_seconds=60, duration_seconds=600, drain_seconds=120, repetitions=3, sample_interval_seconds=1; finite-workload exceptions below |
| generator | seed=42, workload/template hash, rate, concurrency/queue limits, key distribution, payment scenario profile |
| retrieval | mode, query/label hashes, optional embedding/model hash, cache state, top_k, candidate_k, index inventory and parameters |
| assistant | mode=fixed, allow_intent_llm=false, llm_max_calls=1 only when enabled, timeout_ms=1500, turn_deadline_ms=3000, provider/model/prompt identifiers or null |
| faults | Named profile, exact barrier or measurement-second trigger, target, duration and recovery deadline |
| artifacts | root directory, schema versions, raw timing retention; no selective deletion of failed repetitions |

Variant selection overlays only registered fields. The CLI writes the complete resolved configuration into each run, validates the allowed diff and refuses a comparison with different input/rules/hardware/quality semantics. C-BEST is generated from measured choices, not hard-coded as the winner.

## 2. Setup and dataset gates

```bash
python -m projectctl env up --profile local4c8g
python -m projectctl env verify --profile local4c8g
python -m projectctl db migrate --namespace bench-smoke
python -m projectctl contracts check --all
python -m projectctl catalog profile --source data/raw/flipkart_com-ecommerce_sample.csv --rules flipkart-v1 --out artifacts/catalog/profile
python -m projectctl catalog import --source data/raw/flipkart_com-ecommerce_sample.csv --rules flipkart-v1 --load-mode row --namespace bench-smoke --out artifacts/catalog/bench-smoke
python -m projectctl catalog verify --manifest artifacts/catalog/bench-smoke/normalized_manifest.json --namespace bench-smoke
python -m projectctl inventory seed --sku-manifest artifacts/catalog/bench-smoke/sku_manifest.json --namespace bench-smoke --profile performance --seed 42
python -m projectctl projection wait --namespace bench-smoke --sku-manifest artifacts/catalog/bench-smoke/sku_manifest.json --timeout-seconds 120
python -m projectctl fixtures build --config configs/evaluation.yaml --seed 42
python -m projectctl eval run --suite contracts,data,smoke --config configs/evaluation.yaml
```

`local4c8g` is a planned profile. If the hardware cannot enforce it, create a documented feasible profile and use it for **every comparator**; do not claim the planned resources were supplied. The catalogue import completes before seeding, and projection wait verifies every active SKU's initial version/counts. It fails visibly on missing/deferred projections. Startup/seed/model-download time is not steady-state latency.

The generated `artifacts/catalog/bench-smoke/` directory contains the artifacts in file 08 §7. `catalog verify` checks source SHA, complete row-accounting, canonical uniqueness, price/activity rules, lineage and normalized digest. It must not use the same production normalizer as its only oracle.

## 3. Dataset-specific tests and exact expectations

| ID / owner | Inputs and action | Required assertions / artifacts |
|---|---|---|
| D-01 / Harsh; Jaineel review | Full untouched upload, checksum in file 08 | 20,000 ×15; 20,000 unique observations; 19,998 pid; 78 missing both prices; exact nested-shape counts; output profile.json, source_manifest.json and quality_by_category.csv |
| D-02 / Harsh; Jaineel independent fixtures | Full normalization plus dirty edge fixtures | 19,920 active +78 inactive +2 superseded +0 mandatory rejection=20,000; 19,998 unique canonical SKUs; 323 unknown categories; no imputed prices/sizes; 4 usable apparel sizes; exact selected duplicate-pid observations |
| D-03 / Harsh; Aditya seed review | Import twice; interrupt after staging chunk commit and before final promotion; seed twice | Same canonical business digest/versions/counts; no partial ready catalogue; resumed import reconciles; same seed leaves stock/outbox effects unchanged; missing-price SKUs never seeded or quoted |
| D-04 / Harsh; Jaineel runner | W-IMPORT, I0 row insertion versus I1 COPY into staging | Three paired finite imports on same source/rules and fresh namespaces; identical chunk transaction/promotion semantics; equal row hashes; stage and total times, rows/s, CPU/RSS, DB/WAL cost if measurable; no embeddings/LLMs |
| D-05 / Jaineel; Harsh review | 60 frozen assistant scenarios and provider spy | Fixed mode makes zero generative calls; enabled fallback at most one/turn; malformed/time-out response no repair call; all purchase actions zero calls; stage timing and truthful task/clarification outcomes |

Required independent dirty fixtures (stored in `contracts/fixtures/catalog/`, with expected normalized JSON and dispositions):

1. Ordinary row with discounted_price=379 and retail_price=999 → 37,900 and 99,900 minor units; current first upload row is a real reference.
2. Missing discounted price, including a synthetic case with retail present → inactive with null sale price; v1 does not use a retail fallback. Null is distinct from zero.
3. Missing pid/title or invalid crawl time → mandatory rejection; malformed CSV row structure fails the whole import before promotion.
4. Duplicate pid with later time → latest chosen regardless of file ordering; exact same input repeated → no new version. Equal-time conflicting content → SOURCE_ID_CONFLICT, no promoted listing for that pid.
5. Ruby-style specification list/singleton/nil/blank → accepted defined shapes; literal `=>` or `nil` **inside a quoted value** remains unchanged.
6. Executable-looking strings or unsupported nested objects → no execution, safe diagnostic; attribute failure cannot erase a valid price/title or create a guessed facet.
7. Repeated identical key/value → one derived facet and preserved entries; conflicting same-key values → null facet and issue; unkeyed value remains unkeyed.
8. Unknown one-segment category → null category and preserved raw path; known Sunglasses root remains valid. Neither is dropped for lack of subcategories.
9. Missing colour/material/size → null; a non-null hard filter cannot match it. Cotton Lycra does not satisfy exact cotton. Multicolor does not satisfy exact blue.
10. Size=Medium on a Clothing row → M; Size=Medium on Baby Care is not automatically an apparel size; shoe size without a scale remains a raw attribute. Source listing is not exploded into synthetic variants.
11. `No rating available` → null, not zero; no rating-based ground truth invented. Brand is not recovered from a product name.
12. UTF-8 punctuation, quoted commas/newlines, escaped quotes and a 16-KiB cell bound; CSV logical record numbers remain correct. Bound failure has a source locator/reason.
13. Price-only API update changes catalog_version once and emits one logical price event; it does not change embedding text/hash. An invalid price above limits cannot become active.

D-02 also compares shuffled input order, repeated execution and batch sizes against an independently derived expected business digest. Do not hash volatile import timestamps into the equality check. Fixture generation and production normalization must be separate implementations.

## 4. Functional and failure suites to implement

```bash
python -m projectctl eval run --suite T-01,T-03,T-07,T-08,T-09,T-12 --config configs/evaluation.yaml
python -m projectctl eval run --suite T-10,D-05 --config configs/evaluation.yaml
python -m projectctl eval run --suite T-11 --config configs/evaluation.yaml
```

Suite aliases are frozen: contracts=all provider/schema compatibility tests; data=D-01/02/03; smoke=one valid, one duplicate and one invalid record to active Gold plus one simulated successful and one declined checkout; correctness=contracts,data,T-01/03/07/08/09/12,D-05 fixed-mode cases. A comma-separated list runs exactly those registered tests. Performance tests T-02/04/05/06 use the benchmark runner below.

Each T-ID has its scenarios, expected invariant, owner and required evidence in file 03 §7. The CLI additionally saves one `tests.jsonl` record per case: case_id, input_fixture_hash, namespace, started_at, completed_at, status, assertions[{name,expected,observed,passed}], fault_receipt_refs[], artifact_refs[], failure_reason. Failure hooks must produce barrier acknowledgements before a process is killed; a kill without proof that the intended boundary was reached is an invalid trial.

The following scenario coverage is mandatory:

- T-07: before/after local commit; after broker publish/before outbox mark; after sink commit/before offset commit; duplicate relays; retained-volume restart.
- T-08: 100 distinct buyers/one unit; 100 retries/one key; multi-item all-or-nothing; commit/expiry serialization; late payment; reserve tombstone; response loss; crash after stock commit; compensation restart; no false final state while dependencies are unknown.
- T-09: v3,v2,duplicate-v3,conflicting-v3; deferred unknown SKU; bootstrap barrier; stock projections independent of Gold lag.
- T-12: every publication boundary in the common spec; stale compaction; older-than-120-second valid fact; out-of-order parent joins; isolated replay twice with no operational writes.
- T-11: separate analytics and Kafka outages, each 30 seconds starting at measurement second 180, while W-CHECKOUT runs. Record extra finality delay, accepted work and backlog; then reconcile after recovery.

Use real PostgreSQL/Kafka for concurrency, offset, crash and recovery claims. Stub tests prove contracts only. Unit-test the oracle itself using intentionally wrong totals, absent IDs, duplicate debits, illegal inventory and false Gold visibility.

## 5. Performance commands and matrix

```bash
python -m projectctl benchmark run --workload W-IMPORT --variants I0,I1 --repetitions 3 --config configs/evaluation.yaml
python -m projectctl benchmark run --workload W-PIPE --variants B0,O1 --repetitions 3 --config configs/evaluation.yaml
python -m projectctl benchmark run --workload W-SEARCH --variants B0,O2 --repetitions 3 --config configs/evaluation.yaml
python -m projectctl benchmark run --workload W-PIPE --variants P10,P30,P33 --repetitions 3 --config configs/evaluation.yaml
python -m projectctl benchmark run --workload W-ANALYTICS --variants B0,F-COMPACT,F-PARTITION --repetitions 3 --config configs/evaluation.yaml
python -m projectctl benchmark run --workload W-CHECKOUT --variants B0 --faults none,relay-publish-before-mark,saga-after-stock-commit --repetitions 3 --config configs/evaluation.yaml
python -m projectctl benchmark run --workload W-INTEGRATED --variants B0,O3 --repetitions 3 --config configs/evaluation.yaml
python -m projectctl benchmark matrix --matrix configs/core_matrix.yaml --config configs/evaluation.yaml
```

`benchmark run` defaults to the protocol in file 03, writes a unique run directory per repetition and never reuses mutable state. Multiple variants are scheduled in recorded randomized paired order. `--faults` selects registered fault definitions, not arbitrary commands. The no-fault transaction run is Aditya's recovery-cost comparator. For relay-publish-before-mark and saga-after-stock-commit, arm the named barrier at measurement second 180, stop the owning worker after the first matching barrier acknowledgement, keep it down for 10 seconds, then restart on the retained database/volume. Inject once per run; missing barrier acknowledgement invalidates that trial. The 120-second drain deadline still applies. Separate T-08 expiry cases use the explicitly configured 35-second payment delay, not this generic worker outage. `benchmark matrix` expands registered rows and skips already completed runs only after validating artifact hashes and matching the full resolved config; it must not execute both this example list and the same matrix blindly.

Required matrix rows and measurements:

| Workload | Variants / conditions | Primary outputs |
|---|---|---|
| W-IMPORT | I0/I1, original file, finite full import | Total/stage duration, raw/canonical rows/s with denominators, peak memory/CPU, equal digest, repeat/resume correctness |
| W-PIPE | B0/O1 at 500/s | Gold p50/p95/p99, goodput, source dispositions, lag, outbox/pending-export backlog, resources |
| W-SEARCH | B0/O2, mode=filter_only and mode=lexical as separate paired series | Query/request latency, eligible count, plans/buffers, index build/size/update cost, zero filter violations |
| W-PIPE | P10/P30/P33 at 500/s; uniform and 80% hot-key series | Per-partition lag, worker/publisher CPU, group total resources, throughput and skew effect |
| W-ANALYTICS | Before/after compaction; separate partition-layout comparison | Q1–Q6 equal results, per-query latency, file count/opens, selected/actual bytes distinguished, CPU/RSS, compaction build cost |
| W-CHECKOUT | No fault and named recovery faults | Acceptance/finality latency separately, retries, compensation/recovery, inventory/ledger reconciliation |
| W-INTEGRATED | B0/O3; then evidence-selected C-BEST | End-to-end workflow latency plus stream freshness and complete business invariants |
| W-PIPE stress | B0 and C-BEST at 500/1,000/2,000 events/s; 5,000 optional | All three repetitions, admission, lag slope, queues, SLO-qualified sustainable rate, loss/duplicates |
| W-PIPE recovery | Selected configuration, one consumer paused for 30 s at second 180 | Rebalance timeline, lag peak/drain, Gold freshness and final reconciliation |

F-PARTITION expands into two labelled child runs, unpartitioned and date/type-partitioned, each using the same 32-MiB target and codec. Compare those children for the partition-only claim; do not compare a compacted partitioned dataset to B0 small files and attribute the entire difference to partitioning. F-COMPACT alone compares original versus compacted files with partition semantics fixed.

I0/I1 are independent of B0/O1 streaming batches. W-IMPORT is a finite 20,000-observation job: measure from raw file open to completed catalogue/manifest readiness, with read/archive, parse/normalize/select, staging and promotion/export timers. Do three fresh-namespace repetitions, with equal declared OS cache state and source-archive reuse, no 600-second padding and no embeddings. Also report staging-only throughput to isolate COPY's effect. Both stage 1,000 canonical rows per transaction and use identical final promotion.

W-QUALITY is a finite 100,000-record correctness fixture; W-AGENT is a finite 60-scenario suite; their duration is actual completion time, not 600 seconds. W-ANALYTICS runs each Q1–Q6 with 3 unmeasured warmups and 30 measured executions per repetition, randomizing query order; use 3 paired repetitions. Remaining sustained workloads use 60/600/120 seconds. Never divide a finite-job count by the sustained measurement duration.

If the original data are too small to reveal an index/layout effect, preserve that finding. Optional 10× and 50× cloned catalogues must use new deterministic synthetic SKU IDs, original-pid lineage, an explicit scale factor and separate result tables. They do not add real product diversity. Do not clone only for the optimized comparator.

## 6. Search, labels and minimal-call evaluations

Harsh publishes 50 query specifications before tuning: 20 broad, 20 selective, 5 zero-result and 5 fewer-than-five-eligible cases. Record actual eligible fraction rather than forcing impossible 100%/10%/1% strata. Cover several real categories and missing/compound attributes; use the four known-size listings for real size cases and separately marked synthetic fixtures for size parser edge cases. Freeze 30 development and 20 held-out queries before any tuning. Label relevance 0–3 manually, using blinded candidate pools from all compared modes and known relevant matches; unjudged candidates are not automatically irrelevant. Freeze the pool/labels before the final comparison and report coverage/limitations.

Core B-tree trials keep ranking mode unchanged within each pair. Compare filter_only and lexical independently. Optional vector/ANN trials freeze model, vectors, candidate sets and exact-neighbour reference; show database-only ranking latency and full `/v1/search` latency including query encoding as different metrics. No pretrained-model download during timing. Report zero-eligible recall as not applicable, underfilled results and strict filter violations. No training/model sweep.

Jaineel creates 60 human-reviewed assistant scenarios covering explicit supported search, paraphrase/ambiguity, unknown/missing attributes, malicious product-text instructions, invalid model output/timeouts, cart/quote/confirmation and unavailable dependencies. Preserve original six-slot F1 reporting with at least 10 positive labels per slot across scenarios; report optional brand/path slots separately. Extraction labels describe what the user asked, not whether the catalogue contains a match. A correctly extracted unavailable size must produce honest no-results, not an altered intent.

`fixed` uses zero generative calls. Optional `assist` first uses the same rules, then at most one fallback on eligible ambiguous turns. Compare the same scenarios/backends and keep task success, correct clarification, unnecessary clarification, no-result and dependency failure separate. A fast clarification is not a successful product recommendation unless the scenario explicitly expects clarification. A provider spy counts all attempts, including failures/timeouts; no hidden retry or response-generation call is allowed.

Report total and mean calls per all turns, calls per eligible fallback turn, zero-call share, fallback share, timeout/error share, p50/p95/p99 turn latency, parse/LLM/search/compose durations, actual tokens if returned, and calls per successful task. Report actual local query-embedding calls separately. No token/cost numbers for rule-based stubs. Running a real generative provider is optional; without one, validate the budget with stubs and record live quality/latency NOT_RUN.

Optional commands, only after the core matrix and required correctness cases:

```bash
python -m projectctl benchmark run --workload W-SEARCH --variants R-EXACT,R-ANN --repetitions 3 --config configs/evaluation.yaml
python -m projectctl benchmark run --workload W-AGENT --variants A-FIXED,A-ASSIST --repetitions 3 --config configs/evaluation.yaml
```

A-ASSIST without a configured provider records live results NOT_RUN; provider-spy correctness still runs. Vector recall compares vector branches before fusion; final hybrid overlap and human relevance are separate outputs.

## 7. Required artifacts, collectors and final report

Implement the base artifacts in file 03 §9 plus:

| Artifact | Required fields / producer |
|---|---|
| dataset_checks.json | source/rules/dictionary hashes, observed/expected counts, assertion results, selected source IDs; Harsh + independent Jaineel checks |
| import_timings.json | stage elapsed milliseconds, source/canonical/active counts, load mode, chunk size/count, resumed/no-op status, peak resources, logical digest; Harsh |
| query_results.parquet | query_id, mode, variant, eligible_count, returned SKU/rank/score, filter verdict, stage/client durations, embedding calls, plan reference; Harsh |
| assistant_turns.jsonl | scenario/turn IDs, mode, expected/observed outcome, parsed slots, extractor_source, all call attempts, provider timings/usage or null, stage durations, confirmation evidence; Jaineel |
| tests.jsonl | Per-case assertions, actual outcome, barrier and artifact references; each owner through harness |
| audit/ | Read-only order/reservation/stock/ledger snapshots and quote totals; Aditya; namespace-scoped |
| quality_by_category.csv | Canonical/active count, known/missing facets, issues per category; Harsh; denominators explicit |
| hypothesis.md | Bottleneck evidence, single intended change, fixed controls, expected mechanism, correctness/cost risks, measured conclusion; optimization owner |

Per-run collectors: 1-second Kafka group/partition lag; source schedule/send/ack journal; stage timestamps keyed by immutable IDs; Gold visibility membership/generation; outbox/pending export age; CPU/RSS/cgroup memory; queue saturation; DB plans and index inventory; workload-specific business audits. Each collector must expose missing samples. Failed data collection means an affected metric is null/INCOMPLETE, not zero.

```bash
python -m projectctl benchmark reconcile --run-dir benchmarks/results/RUN_ID
python -m projectctl benchmark compare --baseline benchmarks/results/BASELINE_RUN --candidate benchmarks/results/CANDIDATE_RUN --out artifacts/comparisons/pair
python -m projectctl report build --matrix-results artifacts/core_matrix_results.json --out artifacts/final_report
```

RUN_ID/BASELINE_RUN/CANDIDATE_RUN are placeholders replaced with IDs emitted by the runner. Matrix output links all three paired repetitions; report generation refuses to present a single best run as the complete comparison. Summary rows include metric name/unit/value or null, sample count, numerator/denominator, cohort, quantile method, unresolved count, timing validity, run/config hashes, status and evidence path.

Required final tables: dataset quality/dispositions; I0/I1 import cost; B0/O1 streaming; B0/O2 index/query cost; partition/scaling and skew; compaction/pruning; fault/replay correctness and recovery; integrated B0/C-BEST. Optional assistant/ANN quality has separate tables. Required plots come from real artifacts only. The report states whether targets were met, negative results, cost increases, source limitations, hardware limits and what remains NOT_RUN.

## 8. Per-person definition of done

| Person | Must implement and run | Handoff |
|---|---|---|
| Harsh | D-01–D-04; T-04/06/09; source/data/API contracts; index/import/compaction evidence | Verified SKU/facet manifests, row-accounting, query evidence and immutable compaction candidates |
| Vichitr | T-01/02/03/05/12 and sink/publication T-07; setup/registry/transport/storage adapters | Real event receipts, durable manifests, replay/scaling evidence and source-to-Gold timings |
| Aditya | T-07 outbox, T-08, idempotent seeding and T-11 participant hooks | Auditable simulator state, invariant proofs and recovery-cost results |
| Jaineel | projectctl/config schemas, fixture generator, independent oracle, D-05/T-10/T-11, all-matrix integration/report | Reproducible commands, validated raw evidence, fair comparisons, dashboard and final report |

Each personal file gives the corresponding coding order. No person is assigned “just documentation”: everyone owns implementation, tests and a distinct measured engineering contribution.
