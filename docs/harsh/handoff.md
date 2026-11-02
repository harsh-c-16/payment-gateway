# M2 handoff

What each teammate needs from the catalogue module. Everything below is on `main`.

## Jaineel

### Values for `configs/evaluation.yaml`

| Key | Value |
|---|---|
| `dataset.dictionary_path` | `contracts/dictionaries/catalog/flipkart-v1.json` |
| `dataset.dictionary_sha256` | `a7d381e90986b23f801eca537a689f2d3e056fa0b58040ecb7c182e2be2f9943` |
| `dataset.canonical_manifest` | `normalized_manifest.json` from `catalog import` (hash `0d214b4f88f928c9530f7f5838323c08fe2abfa5fc530c07020207c716a9e35b`) |
| `dataset.sku_manifest` | `sku_manifest.json` from `catalog import`; its hash includes the namespace, so it differs per run |
| `retrieval.query_sha256` | `89d89ac030f10d23e85d6e5084caa125017b5f927a1ed94854aadc3be4762410` (`contracts/fixtures/catalog/queries.json`) |
| `retrieval.label_sha256` | `acb1a6e490cb309b298e8768a5f77fe0aff5f457a7cc6f0703922572694be928`; **see the decision below** |
| `retrieval.embedding_sha256` | `fd698508d96cb547595af48c42c1b1359ef5c95bef310b2284fcb7ae9a12acf9` (`output_hash` of the embedding manifest) |
| `retrieval.model_sha256` | `8c0399989cc92c22b1ead78d0ef7b21d4bc4e33ab0bc1d97d3d907f794399093` (`contracts/data/catalog/embedding_model.lock.json`) |
| `retrieval.index_inventory` | `[products_o2_category_price]` for O2 variants; `[products_r_ann_hnsw]` for R-ANN |

### Decisions needed from you

1. **Relevance labels.** The spec asks for manual labels; these are rule-derived and were approved
   without row-level review. Please confirm the runner may accept this `label_sha256`. The preflight
   only checks a hash, so it will not catch this. Details: [relevance_labels.md](relevance_labels.md).
2. **P1 (session reuse) is outside the frozen matrix.** It gave most of the search gain
   ([experiments.md](experiments.md) §§3, 5). Decide whether C-BEST may set
   `CATALOG_REUSE_CONNECTIONS=true`. If not, the expected gain drops to O2 alone.
3. **Review one change in your test.** One assertion in `tests/contracts/test_contracts.py` now
   expects `catalog.yaml` to PASS, since the contract exists.

### Wiring the runner

| Need | What to use |
|---|---|
| CLI commands | `pipelines.catalog.adapter.register(registry)`. It registers `catalog profile`, `catalog import`, `catalog verify` and `projection wait`. `PROJECTCTL_ADAPTER_MODULE` takes one module, so your composition module must call this alongside the other owners' `register` |
| W-IMPORT | `pipelines.catalog.adapter.runner_importer(source, out_root, url=...)` |
| W-ANALYTICS | `analytics.queries.suite.runner_query_adapter(layout_for, store_root, day)` |
| `active_skus` for W-PIPE | Your workloads read `active_skus`; the common-spec manifest has `sorted_skus`. Map with `[entry["sku"] for entry in manifest["sorted_skus"]]` |
| Connection cap | The frozen profile gives catalogue 4 connections; the service default is the common cap of 10. Set `CATALOG_MAX_CONNECTIONS=4` |

**Run `projection wait` after seeding stock, before any search measurement.** It now runs
`ANALYZE stock_projection`. If the seed bypasses it, the first minute of searches runs on a bad plan and
inflates p95 about threefold ([experiments.md](experiments.md) §1).

### `.env.example`

These are for you to change, because the file is outside my paths:

- `CATALOG_DATASET_REVISION=rev-2026-10-24` does not match the real revision,
  `flipkart-v1-3a401f32ca99379f8298ce42`.
- Add `CATALOG_REUSE_CONNECTIONS`, `CATALOG_MAX_CONNECTIONS`, `EMBEDDING_MODEL_DIR`, `QUOTE_TTL_SECONDS`
  and `LAKEHOUSE_ROOT`.

### Results for the G5 gate

The recommendation is I1, O2 and exact retrieval, plus P1 if you allow it, plus compaction. HNSW is
not recommended; if R-ANN runs, use `ef_search=100` with `iterative_scan=strict_order`. These are
owner-run numbers, so the official runs still need your runner.

## Aditya

| Need | Detail |
|---|---|
| `shared.outbox.append_outbox(tx, event)` | Search and price changes write events in the same transaction through it. Until it exists, those endpoints return 503 and `/health/ready` is not ready, by design |
| Outbox table in `catalog_db` | Your migration, applied alongside `migrations/catalog/` |
| Stock events | Absolute snapshots with a stable SKU and increasing `stock_version`. Stale and identical events are no-ops; unknown SKUs wait in `stock_deferred` |
| Seeding | Run `python -m projectctl projection wait` after your seed so statistics are collected |

I never read Inventory's tables. The catalogue's only stock source is its own consumer group.

## Vichitr

| Need | Detail |
|---|---|
| Compaction | `analytics.compaction.compact.compact_snapshot` builds a candidate from a pinned manifest and hands it to your `publish_candidate`. It never writes `active_datasets` or deletes files, and a stale base generation stays your `STALE_MANIFEST` path |
| **T-09 on a real broker, please** | This machine has no broker: `CATALOG_TEST_KAFKA_BOOTSTRAP=127.0.0.1:9092 CATALOG_TEST_DATABASE_URL=... pytest tests/catalog/test_projection_kafka_live.py`, with the streaming-local profile running. It is the one required real-broker check I could not run |
| Running the service | `infra/compose.catalog.yaml` adds to your streaming stack with `-f`. **It has only been statically checked**, because this machine has no Docker |

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
