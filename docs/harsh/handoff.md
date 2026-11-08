# M2 handoff

What each teammate needs from the catalogue module. Everything below is on `main`. The 8 November
relay, broker and Compose rows under Aditya and Vichitr were recorded by Vichitr.

## 9 November: answers to the evaluation handoff

This answers `docs/jaineel/HARSH_REVIEW_2026_11_09.md` and Vichitr's 9 November list.

### Inputs confirmed

The packet was generated and verified on Linux at clean commit `f971747`
(`python -m projectctl.evaluation_packet`): status `INPUTS_PINNED_REVIEW_PENDING`, content hash
`001d1180…`. **The revision `flipkart-v1-3a401f32ca99379f8298ce42`, the dictionary identity and every
SKU and business identity stay unchanged.** Jaineel's Windows hashes are the same files with CRLF line
endings: converting each committed file's LF to CRLF reproduces his four values exactly.

| File | Exact bytes on Linux (= published) | Same file with CRLF (Jaineel's Windows value) |
|---|---|---|
| Source CSV | `56f8f699…93ad1` | `56f8f699…93ad1`; the CSV is not in git, so no conversion |
| Dictionary | `a7d381e9…f9943` | `7de194b5…02a02` |
| Search queries | `89d89ac0…62410` | `14733547…cd63` |
| Normalized manifest | `6d9e8139…715dc` | `8fed5a44…8b0e` |
| SKU manifest | `609e0ea9…bc28c7` | `51632d83…fa75` |

So on the Linux execution machine, the exact-byte pins equal the published values. Regenerate the packet
there, as the runbook says.

### Provider review

Both catalogue surfaces are approved in `provider_review.json`, made from the proposal in the packet,
with the other owners' entries left pending. With it, `projectctl contracts check --all` reports
`contracts/data/catalog` and `contracts/dictionaries/catalog` as PASS. Two notes on the validators:

- The `contracts/data/catalog` validator only checks that each schema is a valid JSON Schema. As review
  evidence, the pinned source, normalized, SKU and facet manifests, the profile and a load report all
  validate against their schemas with 0 errors.
- The surface pins `.py`, `.sql` and `.json` files, so `embedding_requirements.txt` is not pinned. It
  matters only for the optional vector modes.

### Runner bindings

Set `PROJECTCTL_OWNER_RUNTIME_MODULES=pipelines.catalog.runtime` next to `projectctl.team_runtime`. It
merges beside M4's bindings without a duplicate, and starts nothing when registered.

| Workload | Callbacks |
|---|---|
| W-IMPORT | `fresh_namespace`: no catalogue rows in the namespace. Your lifecycle already runs the importer, drain and import audit |
| W-SEARCH | `fresh_namespace` (catalogue and Inventory), `seed_audit` (catalogue facts plus Inventory's SKU set, pending outbox and seed run ID; the Inventory SKU set must equal the active catalogue SKUs), `drain` (the catalogue outbox reaches 0 unpublished rows through the relay), `audit`, `observer_factory` |
| W-ANALYTICS | `fresh_namespace` (analytics), `layout_for` and `query_day` from a frozen layout file, `audit`, `observer_factory` |
| Reset | `ResetParticipant` for `catalog`: preflight refuses while the outbox holds unpublished rows; apply deletes one bench namespace in one transaction, FK-safe |

Migrations stay on your built-in `projectctl.setup.migrate_catalog`.

**Deployment inputs:**
- `CATALOG_AUDIT_DATABASE_URL`, `INVENTORY_AUDIT_DATABASE_URL` and `ANALYTICS_AUDIT_DATABASE_URL`:
  Vichitr's SELECT-only roles. Every check reads through them and refuses a role with write privileges.
- `CATALOG_METRICS_URL`.
- `PROJECTCTL_SUT_CONTAINERS`: every profile service must be mapped; nothing is guessed.
- `CATALOG_BINDING_REVIEW_PATH`.
- `ANALYTICS_FROZEN_LAYOUTS`.

**The W-SEARCH audit** compares the run against independent expectations frozen before it:
`contracts/fixtures/catalog/search_expectations.json`, made by `pipelines/catalog/search_oracle.py`.
The oracle re-applies the hard filters to `catalog.parquet` in plain Python and shares no code with the
search service. For each query the audit checks four things:
- the eligible count, which must be identical in every response;
- 0 hard-filter, stock, revision or count-invariant violations in any hit, read back through SQL;
- the same hits in every response;
- that no request is unresolved.

It writes `expected.json`, `observed.json`, `source_fixture.json`, `query_results.parquet`, `plans/`
(`EXPLAIN ANALYZE` of every query, after the window) and `manifests/`. Ranking quality is not judged:
the labels stay diagnostic.

**W-ANALYTICS** needs Vichitr's drained snapshot namespace and query day. Freeze them once, before any
run:

```bash
python -m analytics.queries.layouts freeze --namespace SNAPSHOT_NS --day YYYY-MM-DD --out FROZEN_JSON
```

- **What freezing records:** the exact file list, hashes and generations of each layout (small files,
  compacted, unpartitioned), plus each query's expected digest.
- **When it refuses:** if any layout gives a different result.
- **What the runs do:** measured runs only read these lists, and the audit refuses if any frozen file
  changed.
- **Limit:** the expected digests are the small-file results under DuckDB. They are independent of the
  layout under test, not of the engine.

### Checks on 9 November

| Check | Result |
|---|---|
| Your `benchmarks.import_audit.audit_import` on a real import of the 20,000-row file | **18 of 18 assertions passed**: 19,920 active, 78 inactive, 2 superseded |
| Oracle against the real `/v1/search` over HTTP | Eligible counts agree on all 50 frozen queries |
| W-SEARCH audit over 150 real searches (50 queries × 3) | Passed: complete, 0 violations, every query deterministic; 96 plans |
| `tests/catalog/test_runtime_live.py`, `tests/analytics/test_layouts_live.py` | 12 passed, including tampered responses and a changed Parquet file, which the audits catch |
| Contracts check with the review receipt | Both catalogue surfaces PASS; other owners' surfaces still UNREVIEWED |

The raw evidence (packet, review receipt, import audit, search audit with plans, and the owner
experiments' summaries, plans and query results) is git-ignored and sent separately as
`harsh-evidence-20261109.tar.gz`.

### Open points for you

1. **The P9 validator cannot accept a review frozen before the run.** For W-IMPORT, W-SEARCH and
   W-ANALYTICS, `benchmarks/performance.py` requires `binding_review.json`'s `fixture_sha256` to equal
   the hash of the run's `expected.json`. But `expected.json` must also carry the run's own namespace,
   so its bytes are new in every run. My audit writes the reviewed expectations unchanged as
   `source_fixture.json` and validates the review against that, as your integration cases do. Please
   make the P9 check do the same.
2. **Checkout and integrated templates are not the catalogue's to freeze.** The catalogue adds no
   template fields: every SKU in the pinned manifest can be quoted at its catalogue price, and your
   generator picks the hot-80 SKUs from that manifest. A template that names a SKU would bypass that
   selection.
3. **Relevance is unchanged.** `label_sha256` stays null and the rule-based scores stay diagnostic.

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
4. **Hash pin policy: settled on 9 November.** Evaluation pins use exact bytes, generated on the
   execution machine, and the dictionary keeps its LF identity, so `dataset_revision` is unchanged.
   This matches my proposal. On Linux the two are equal; see the 9 November section.

### Wiring the runner

For the shared runner, the 9 November bindings above compose these functions. The table stays as their
reference.

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
| Seed proof (review, please) | The W-SEARCH `seed_audit` reads your `inventory` table (SKU set) and `outbox` (unpublished rows and the seed `run_id` in the payload) for the run's namespace, through `INVENTORY_AUDIT_DATABASE_URL`. The Inventory SKU set must equal the active catalogue SKUs |
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
| Event contracts (reviewed 9 November) | Search writes `SEARCH_REQUESTED` and `PRODUCT_RETRIEVED`, and a price change writes `PRICE_UPDATED`. Each payload carries exactly the schema's required fields, and the codec validates them in `test_outbox_live.py`. The catalogue never emits `PRODUCT_COMPARED`. All three events carry `synthetic: true` with `scenario_source: simulation`, which is right while all traffic is simulated |
| Pinned snapshot for W-ANALYTICS | Give me your drained snapshot namespace and UTC query day, and freeze the layouts with `analytics.queries.layouts freeze` (see the 9 November section). Compaction publishes through your publisher, so the snapshot's generation advances; the small-file layout stays the earlier generation, whose files you retain |
| Stale-candidate case | T-12 `stale-compaction` is your `STALE_MANIFEST` path. A candidate for it is `compact_snapshot` on a pinned manifest, published after ingestion advances. `CompactionFaults` is the separate crash boundary |
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
