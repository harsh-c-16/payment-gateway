# M2 handoff

What each teammate needs from the catalogue module. The M2 implementation is on
`main`; M4's 8 November relay/broker/Compose follow-up below is on `vichitr` until
its PR is merged. These follow-up observations were recorded by Vichitr.

## Jaineel

### Values for `configs/evaluation.yaml`

| Key | Value |
|---|---|
| `dataset.dictionary_path` | `contracts/dictionaries/catalog/flipkart-v1.json` |
| `dataset.dictionary_sha256` | `a7d381e90986b23f801eca537a689f2d3e056fa0b58040ecb7c182e2be2f9943`; **see the pin policy below** |
| `dataset.canonical_manifest` | `data/catalog/flipkart-v1-3a401f32ca99379f8298ce42/normalized_manifest.json` (content hash `0d214b4f88f928c9530f7f5838323c08fe2abfa5fc530c07020207c716a9e35b`) |
| `dataset.sku_manifest` | `data/catalog/flipkart-v1-3a401f32ca99379f8298ce42/sku_manifest.json` (content hash `f432fd147a2211837c0ab3abb9216047fbdf51bd5a703bcd218e45fe9b1c76b3`). Its hash includes its namespace, `bench-catalog-v1`. Search, checkout and integrated runs make their own per namespace, as your `Lifecycle` already does |
| `retrieval.query_sha256` | `89d89ac030f10d23e85d6e5084caa125017b5f927a1ed94854aadc3be4762410` (`contracts/fixtures/catalog/queries.json`); **see the pin policy below** |
| `retrieval.label_sha256` | Leave unset. The rule-derived labels are diagnostic only, by your decision |
| `retrieval.embedding_sha256` | `fd698508d96cb547595af48c42c1b1359ef5c95bef310b2284fcb7ae9a12acf9` (`output_hash` of the embedding manifest) |
| `retrieval.model_sha256` | `8c0399989cc92c22b1ead78d0ef7b21d4bc4e33ab0bc1d97d3d907f794399093` (`contracts/data/catalog/embedding_model.lock.json`) |
| `retrieval.index_inventory` | `[products_o2_category_price]` for O2 variants; `[products_r_ann_hnsw]` for R-ANN |

### Manifests and projection evidence

`data/catalog/flipkart-v1-3a401f32ca99379f8298ce42/` holds the pinned outputs of one real import of the 20,000-row file, at the path file 08 names:
the source, normalized, SKU and facet manifests, plus `profile.json`, `quality_by_category.csv` and
`dataset_checks.json`. The Parquet files (14 MB) are left out; the normalized manifest pins each by
SHA-256, and an import regenerates them.

Checked on 8 November 2026 on real PostgreSQL 18, namespace `bench-catalog-v1`:

| Check | Result |
|---|---|
| `db migrate` (catalogue participant), `catalog import`, the same import again, `catalog verify` | Completed; promoted, then no-op; 19 of 19 assertions passed |
| Rows | 19,998 canonical, 19,920 active, 78 inactive; digest `d87f57e6…` |
| Your `benchmarks.composition.catalog_projection` on these manifests | Passed: 19,920 sorted `FK-` SKUs, source hash, rules version, revision and digest all agree |
| Reproducible | The committed source, normalized and facet manifests, profile and quality CSV are byte-identical to the outputs of about 80 earlier local imports of the real file. Only the SKU manifest differs between runs, through its namespace |
| Brand keys, using your `canonical_text` | 0 of 14,072 branded active products and 0 of 3,370 dictionary brands differ from their key |
| `projection wait` after seeding | 19,920 expected, 19,920 projected, 0 deferred |
| `runner_seed_audit` | `active_sku_count` 19,920, `projected_sku_count` 19,920, `initial_on_hand` 10,000, `reserved` 0, `stock_version` 1, `deferred` 0 |

**The seed here was direct SQL**, because this machine has no broker. The real path, Inventory → Kafka →
this projection, is Vichitr's 6 November run: 19,920 SKUs at version 1. Coverage of colour, material,
size, brand and category is in `facet_dictionary.json` under `coverage_by_category`, and file 08's totals
are among `catalog verify`'s assertions.

### Decisions

1. **Relevance labels: decided by you.** The rule-derived scores stay diagnostic, and no
   human-relevance claim is made. `label_sha256` stays unset. Claiming NDCG@5 ≥ 0.70 would need a
   hand-reviewed label file; the team has not made one. Details: [relevance_labels.md](relevance_labels.md).
2. **P1 (session reuse): decided by your runner.** W-SEARCH requires `CATALOG_MAX_CONNECTIONS=4` and
   `CATALOG_REUSE_CONNECTIONS=false`, so C-BEST gets O2 alone. P1 stays an owner-run finding
   ([experiments.md](experiments.md) §§3, 5).
3. **Review one change in your test.** One assertion in `tests/contracts/test_contracts.py` now
   expects `catalog.yaml` to PASS, since the contract exists.
4. **Hash pin policy: please agree it with Aditya.**
   - **Facts:** git stores the dictionary and query file with LF line endings. So on any LF checkout
     the published value is both the raw-file hash and the LF-text hash; `review_input_pins` shows
     both match on Linux. A Windows checkout with `core.autocrlf=true` rewrites them as CRLF, and only
     then does the raw hash differ.
   - **My proposal:** pin the exact raw bytes, as file 09 §1 requires, with the values above.
     Windows runs check out with `git config core.autocrlf false` (or `input`) before running. No file
     or hash changes, and `dataset_revision` is unaffected: the catalogue reads the dictionary as
     newline-normalized text, which for these files equals the raw bytes.

### Wiring the runner

| Need | What to use |
|---|---|
| CLI commands | `pipelines.catalog.adapter.register(registry)`. It registers `catalog profile`, `catalog import`, `catalog verify` and `projection wait` |
| `db migrate` participant | `pipelines.catalog.adapter.migrate_action`, as `MigrationCoordinator({"catalog": migrate_action, ...})`. It changes only `catalog_db`, is idempotent and refuses a changed applied migration |
| `seed_audit` | `pipelines.catalog.adapter.runner_seed_audit(url=None)` returns the async `(context) -> facts` catalogue half. Each of `initial_on_hand`, `reserved` and `stock_version` is `None` unless uniform across the active SKUs, so your check fails rather than passing on a mixed state. Add `run_id` and Aditya's `pending_outbox` when combining |
| W-IMPORT | `pipelines.catalog.adapter.runner_importer(source, out_root, url=...)` |
| W-ANALYTICS `layout_for` | `analytics.queries.suite.build_layouts(pipeline, namespace)` once, before measuring; it compacts through Vichitr's publisher. Then `runner_layout_for(layouts)`. It maps `(file_layout, partitioning)`: `(small, date_type)` to the small files, `(compact, date_type)` to the compacted files, `(compact, unpartitioned)` to the unpartitioned rewrite. Any other pair raises |
| W-ANALYTICS `query_day` | The frozen snapshot's UTC day. It comes with Vichitr's snapshot, not from me |
| W-ANALYTICS adapter | `analytics.queries.suite.runner_query_adapter(layout_for, store_root, day)` |
| `active_skus` for W-PIPE and W-QUALITY | `pipelines.catalog.adapter.runner_catalog_manifest(path)`, with the pinned SKU manifest above |
| Compaction faults | `analytics.compaction.faults.CompactionFaults` is the **crash** boundary: barrier `after_candidate_files_before_publish`, target `compaction`. T-12 `stale-compaction` (`before_manifest_swap`, `compaction-publisher`) is a different case, the publisher's `STALE_MANIFEST` rejection, which is Vichitr's. A stale candidate for it comes from `compact_snapshot` on a pinned manifest. The crash boundary still needs a case ID from you |
| Expired quotes for `g3_recovery` | Start the catalogue with a short `QUOTE_TTL_SECONDS` and wait it out. No clock change or database write is needed |

**Run `projection wait` after seeding stock, before any search measurement.** It runs
`ANALYZE stock_projection`. If the seed bypasses it, the first minute of searches runs on a bad plan and
inflates p95 about threefold ([experiments.md](experiments.md) §1).

### Review of your workflow against the real service

Rerun on 8 November with your merged workflow over real HTTP: **43 of the 50 frozen queries pass, and the
same 7 are rejected**. W-SEARCH posts to `/v1/search` directly, so these rejections do not affect it.

| Finding | Status |
|---|---|
| `candidate_count` below `eligible_count` broke your funnel check | Fixed in my service on 2 November |
| Brand key compared with the displayed brand | **Fixed by you.** My strict-xfail test now passes as a normal test, and the brand check above finds no mismatch on the real data |
| Any dictionary word bound as a filter ("blue cotton shirt" → `brand=blue`) | Your parser now needs a cue for a brand. I have not re-tested it |
| S11, S12, S13, U04 and U05 use the brand label, which `validate_constraints` rejects | Left frozen; `/v1/search` accepts both. Tell me if you want keys, which changes `query_sha256` |
| Z03 and Z05 ask for values that do not exist | Correct rejection |

## Aditya

| Need | Detail |
|---|---|
| `shared.outbox.append_outbox(tx, event)` | Search and price changes write events in the same transaction through it. `tests/catalog/test_outbox_live.py` checks this with your real library |
| Outbox table in `catalog_db` | `migrations/catalog/005_outbox.sql`, a copy of your `shared/outbox/schema.sql`, as your template asks |
| A relay for `catalog_db` | M4 now supplies `infra.catalog_relay` and the `catalog-relay` Compose service, using the real shared `OutboxRelay` at 25 ms /100 rows. The isolated 8 November Compose smoke verified actual search/price outbox delivery to Kafka. Use the same migrated database/schema as the API; see Vichitr's handoff for evidence and limits |
| Stock events | Absolute snapshots with a stable SKU and increasing `stock_version`. Stale and identical events are no-ops; unknown SKUs wait in `stock_deferred` |
| Seeding | Run `python -m projectctl projection wait` after your seed so statistics are collected |

I never read Inventory's tables. The catalogue's only stock source is its own consumer group.

Found while reviewing Orders against the catalogue (your code; I changed nothing):

| Finding | Detail |
|---|---|
| Quote validity is not checked | Common §5 says Orders checks quote binding and validity. `create_order` uses the quote without comparing `expires_at` with now or `user_id` with the caller. The catalogue returns an expired quote as expired rather than refusing it, by design |
| The real catalogue is not in the live test | `tests/transactions/test_checkout_live.py` replaces `_fetch_quote`, so Orders has never called the real `/internal/v1/quotes/{id}` |
| Setting name | Orders reads `CATALOG_URL`. Fixed: Jaineel added it to `.env.example` on 8 November |

## Vichitr

| Need | Detail |
|---|---|
| Compaction | `analytics.compaction.compact.compact_snapshot` builds a candidate from a pinned manifest and hands it to your `publish_candidate`. It never writes `active_datasets` or deletes files, and a stale base generation stays your `STALE_MANIFEST` path |
| T-09 edge cases on a real broker | M4's 8 November run passed all four cases in `tests/catalog/test_projection_kafka_live.py`: ordering/duplicates/restart, conflicting versions with a real diagnostic outbox, actual two-member partition rebalance, and child-process death after SQL COMMIT before offset commit followed by idempotent redelivery. The earlier named test also passed in `broker-focus.xml` on 6 November; that alone did not cover these extra faults. Run with `CATALOG_TEST_KAFKA_BOOTSTRAP` and `CATALOG_TEST_DATABASE_URL` against isolated test schemas on Linux. The broker fault fixtures use explicit schema-cache doubles; the separate Compose smoke uses the actual registered cache |
| Cold-cache series without `/proc/self/io` | `--cold` now records `cold_series: NOT_RUN` with the reason and keeps the warm series. It never substitutes zeros or warm timings |
| Running the service | `infra/compose.catalog.yaml` adds API, stock consumer and shared outbox relay with `-f`. M4 started all three on 8 November and passed `tests/catalog/test_compose_live.py` with real HTTP, SQL and Kafka in an isolated synthetic namespace. The test processes were stopped afterward; no production-data or benchmark acceptance is implied |

## Everyone: running it

```bash
# Service
CATALOG_DATABASE_URL=... INTERNAL_API_TOKEN=... uvicorn --factory services.catalog.app:create_app --port 8002
python -m services.catalog.worker --namespace NS

# Optional variants
python -m pipelines.catalog.migrate --variant o2      # or r-ann
```

Provider stub for consumers before the service runs: `tests/catalog/stub_provider.py`. Example manifest:
`contracts/data/catalog/sku_manifest.example.json`. Vector modes need the locked model in
`EMBEDDING_MODEL_DIR`, and dependencies from `contracts/data/catalog/embedding_requirements.txt`.
