# Harsh Chaudhari: personal coding brief

Module owner: M2 catalogue/retrieval + analytical compaction/query performance  
Version 2.0. Read first: 01_PROJECT_CONTEXT.md, 02_COMMON_SPEC.md, 03_EVALUATION_SPEC.md, 08_DATASET_PROFILE_AND_RULES.md and 09_EVALUATION_RUNBOOK.md. The dataset rules and evaluation commands are required implementation inputs, not optional background.

## 1. Your final responsibility

**You own data ingestion and normalization for the source CSV.** Own full-file profiling, safe nested-field parsing, latest-pid selection, provenance, staging/promotion, catalogue load/reload, authoritative prices, quotes, search and the stock read model. Vichitr owns Kafka event ingestion, not a second CSV cleaner. Optional embeddings are offline and fixed-model. Evaluate B-tree indexing and exact/ANN retrieval without violating hard constraints.

**Change from tracker:** also own immutable Parquet compaction candidates and analytical query benchmarks. This fits your DBMS/indexing role and removes file-layout experimentation from Vichitr’s already large ingestion workload. Vichitr still owns publication and recovery; do not implement a second manifest mechanism.

## 2. Files and interfaces you own

- services/catalog/, pipelines/catalog/, migrations/catalog/, catalogue/quote/search DTOs.
- contracts/data/catalog/, contracts/dictionaries/catalog/, source/canonical/SKU/facet schemas and importer/profile/verification CLI adapters.
- contracts/http/catalog.yaml and catalogue/retrieval fixtures.
- analytics/compaction/, analytics/queries/ and their tests.
- Catalogue/embedding/source manifests and labelled query sets.
- D-01–D-04 source/normalization/import evidence; T-04 file-layout, T-06 retrieval and T-09 projection evidence.

Expose /v1/search, /v1/products/{sku}, /v1/quotes, catalogue facets, internal quote lookup and internal price update exactly as common §5 defines.

Local functions: profile_catalog, normalize_catalog_row, select_latest_listings, export_sku_manifest, get_facet_dictionary, load_catalog, build_embeddings, filter_catalog, exact_search, ann_search, fuse_rrf, search_catalog, create_quote, apply_stock_event and compact_snapshot. Return the common DTOs; do not create a second ShoppingIntent with different field names.

## 3. What you require from other people as black boxes

| Provider | Interface/data | Behavior you rely on |
|---|---|---|
| Jaineel | SearchRequest and ShoppingIntent | Nullable slots with explicit units; top_k bounded; identity/correlation/run context |
| Jaineel | Frozen query/load manifest and oracle | Same inputs, rates and result calculation across variants |
| Aditya | Inventory event snapshots | Full counts, stable SKU, increasing stock_version, occurrence time |
| Aditya | append_outbox(tx,event) | Price changes and retrieval event persistence share your local transaction |
| Vichitr | Event schemas, consumer adapter, commit_offsets | Manual contiguous offset commits and schema/key validation |
| Vichitr | Shared diagnostic helper | Durable local quarantine/reference for projection errors without cross-service DB writes |
| Vichitr | DatasetManifest, FileStore and publish_candidate | Read a pinned generation; only Vichitr activates an equivalent candidate |

Do not read Inventory’s tables from your catalogue application. Do not use Gold to obtain current availability. Your separate Kafka consumer group receives stock directly.

## 4. Ordered coding tasks

### H01 — Real CSV ingestion, normalization and manifests

Create executable nullable Product/Search/Quote/Facet and data-manifest schemas first. Read the entire dataset profile/rules file. Build raw observations, exclusive disposition ledger, issue records, import/checkpoint/staging tables and canonical products; use the shared FileStore to archive the original source. No LLM calls for data preparation.

Implement the safe quote-aware `=>`/nil parser, list/singleton/null handling, duplicate-key preservation, conservative category/facet rules and exact Decimal-to-minor-unit conversion. latest crawl per pid determines the selected listing; sku=product_id=FK-<pid>. Do not group variants by name or expand fictional sizes. Missing sale price makes a canonical row inactive, not a zero-price product or a dropped source record.

The exact observed file must account for 20,000 source rows =19,920 active +78 inactive +2 superseded, yielding 19,998 canonical listings. Preserve 323 unclassified categories and missing optional attributes. Only four listings have usable apparel sizes under the frozen rule. Do not hard-code these counts into production logic; validate them only for the supplied checksum.

Implement I0 row inserts and I1 COPY into the same staging schema with identical 1,000-row commit/checkpoint boundaries and final atomic promotion. Same import is a no-op; interrupted imports resume without partial readiness or extra versions. Publish source/profile/observations/catalogue/disposition/issue/SKU manifests. Give Aditya the active-SKU manifest without stock quantities; give Jaineel the facets and expected-null coverage. Feed Vichitr source hashes for lineage.

Acceptance: D-01/02/03 pass, no invented data, repeat/resume business digests identical, consumers work from manifests/stubs without re-reading CSV.

### H02 — Authoritative pricing and quotes

Implement quote creation from one consistent catalogue snapshot. Multiply integer unit price by quantity, validate int64 bounds, persist immutable quote and lines, bind to user/cart version, expire after 60 seconds.

Implement internal quote lookup for Orders. Honour the documented price-promise semantics: a valid quote locks prices at acceptance even if the catalogue later changes. Stock remains advisory at quote time.

Implement price update with expected_catalog_version and a local PRICE_UPDATED outbox event. Changing only price or stock must not regenerate product embeddings.

Acceptance: different client-supplied display price cannot alter quote total; expired quote is visible as expired; wrong user cannot retrieve/use it; simultaneous updates do not produce a mixed-price snapshot.

### H03 — Exact retrieval baseline

Implement filter_only and lexical first; lexical is the operational default with no model inference. Build fixed-revision 384-dimensional normalized embeddings offline only for the semantic branch, using common §10 text/truncation rules. Save text/model hashes and inference cost; prewarm once per worker. No catalogue embedding job or download during requests.

Implement filter_only, vector_exact, lexical and hybrid_exact precisely. Hard constraints are applied to both lexical and vector branches before RRF. Use RRF k=60, rank starting at 1, candidate limit 100 and deterministic SKU ties.

Keep the baseline free of the optional B-tree/HNSW indexes while retaining integrity indexes. Capture actual query plans to verify exact mode did not accidentally use an ANN index left from another run.

Acceptance: inactive/no-price rows and unknown requested facets cannot satisfy a sale query; no-result is valid even for a known size. Every returned hit satisfies filters and availability; empty results are honest; output ranks are reproducible under frozen data; product facts are grounded.

### H04 — Stock consumer and freshness

Bootstrap stock through seeded STOCK_UPDATED events. Until a SKU has a valid projection, do not recommend it as available. Apply version comparison and event-ID conflict detection in a local transaction, then commit Kafka offsets.

Stock events are absolute snapshots. Handle v3 before v2, duplicate v3, conflicting v3, missing intermediate versions, rebalance and crash-after-projection-before-offset. Retain a local durable diagnostic for malformed/conflicting input; analytical processing can proceed independently.

Expose timing and version receipts for the freshness oracle. Measure freshness by observation after your projection transaction commits, not by how quickly a Kafka callback started.

Acceptance: source and projection agree after drain; stale events never replace newer counts; your group’s offsets do not interfere with Vichitr’s analytics group.

### H05 — Import loading, B-tree and secondary ANN experiments

First run W-IMPORT I0/I1 under D-04, recording identical row digests, finite-job end-to-end and stage times, rows/s, CPU/RSS and restart behavior. Then compare B0 versus O2 on the original catalogue and fixed queries, separately for filter_only and lexical. Record EXPLAIN ANALYZE/BUFFERS, actual eligible rows, p50/p95/p99, index size, build cost and mutation overhead. A sequential scan may be appropriate on a small/high-selectivity dataset; do not force an index just to demonstrate its existence.

After the core DE gates, compare exact and HNSW with fixed embeddings and filters as a secondary retrieval-system study. No model selection or per-row LLM enrichment. Report recall@5, underfilled rate and hard-filter violations by selectivity stratum. Use the configured ef_search/iterative settings from the evaluation spec. Separate any exact-fallback variant from raw ANN results.

Collect manually labelled relevance before tuning. Do not tune against the same final held-out labels without reporting that limitation. The exact neighbour set provides ANN recall ground truth; relevance labels provide NDCG. They are different comparisons.

Acceptance: no optimization can pass with wrong-price/size/stock hits. A latency gain with poor recall is reported as a trade-off, not an unconditional win.

### H06 — Parquet compaction and query suite

Consume a pinned manifest through Vichitr’s FileStore. Build a candidate preserving exact logical rows/types. For revisioned Gold, resolve the active logical key set from the manifest; do not combine retired snapshots.

Produce before/after sorted logical digests, counts and exact monetary totals by currency. Target 32 MiB compressed files with the same codec; keep date/type partition semantics fixed in the compaction-only variant. Test partition pruning in a separate variant.

Submit ManifestCandidate to Vichitr; never write active_datasets or delete original files. STALE_MANIFEST means the input changed; rerun/rebase rather than overwriting current data.

Implement Q1–Q6 using fixed SQL/parameters and explicit file lists. Record file opens, candidate file bytes and actual read bytes only if instrumentation supports them. Warm and cold series are separate. Include a labelled larger fixture if small output cannot exercise compaction.

Acceptance: identical logical query results and monetary totals; crash before publication leaves original queryability intact; no claim that compaction must reduce scanned bytes.

## 5. Function-level acceptance examples

| Function | Required edge case |
|---|---|
| profile/normalize/select/load_catalog | Full-file accounting, latest pid, Ruby-like nested forms, null facets, missing price retained inactive, source-row provenance, import no-op/resume and I0/I1 digest equality |
| build_embeddings | Same text/model yields same stored version metadata; changed price does not alter embedding input |
| filter_catalog | Null bound vs zero bound, unavailable/unknown stock, exact size/material |
| fuse_rrf | Duplicate candidate across lists counted once as a product, both rank contributions retained |
| create_quote | Concurrent price update, stale cart binding, integer overflow and idempotent response |
| apply_stock_event | Duplicate same event, same ID changed payload, lower/same/higher version |
| compact_snapshot | Tail file, empty partition, repeated Gold key revision, stale base generation |
| query benchmark | Identical output with unpartitioned/partitioned/compacted layouts |

## 6. Outputs you hand to teammates

| Milestone | Deliverable | Consumer |
|---|---|---|
| G0 | Catalogue/search/quote contract, deterministic stubs, SKU/dictionary manifest | Jaineel, Aditya, Vichitr |
| G2 | Real quote, lexical/filter APIs and dataset/SKU/facet manifests; embedding manifest only for optional vector mode | Jaineel and Orders |
| G3 | Live stock projection with freshness/version evidence | Aditya and Jaineel |
| G5 | I0/I1 and O2 results; optional ANN results and chosen parameters | Jaineel |
| G5/G6 | Equivalent compaction candidate and query evidence | Vichitr publishes; Jaineel compares |

Your code is complete when other owners can integrate without knowing your SQL/ranking internals, and your performance claims include query plans, quality constraints and update/storage costs.

## 7. Evals you must code and run

Implement projectctl catalogue adapters and D-01–D-04 in runbook §§2–3. Run profile/import/verify, repeat import and interrupted-chunk recovery before downstream seeding. Your required artifacts are profile.json, quality_by_category.csv, dataset_checks.json, import_timings.json, canonical/disposition/issue Parquet and hashed SkuManifest/FacetDictionary.

Run W-IMPORT I0/I1 and W-SEARCH B0/O2 with three paired repetitions. Supply raw query_results.parquet, actual plans/buffers/index inventory, selectivity, build/storage cost and equal-result/filter assertions. Run T-09 real projection tests and T-04/Q1–Q6 compaction/equality tests. Optional ANN follows core ingestion/index/layout evidence and includes recall plus full-query embedding latency. Use the exact commands in runbook §5 through Jaineel's shared runner.

The workload balance is deliberate: CSV ingestion/indexing/layout are your primary contributions; embeddings/ANN are secondary. Do not create a second stock service, generic event pipeline or manifest publisher.

## 8. Prompt for your coding LLM

> I am Harsh, owner of catalogue/retrieval and compaction candidates. Read the shared context/spec/evaluation and this brief. Start H01 with real-CSV ingestion, nullable contracts, safe deterministic normalization, migrations and hashed catalogue manifests; implement D-01–D-04 and the CLI adapters from the runbook. No per-row LLM calls, imputed prices or fictional size variants. Import shared DTOs and outbox/transport interfaces; do not implement inventory or a second publisher. Keep exact retrieval as the baseline, enforce every hard constraint, and do not activate candidate Parquet files yourself. Report the tests run and exact handoffs produced.

