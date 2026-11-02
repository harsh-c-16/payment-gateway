# Catalogue ingestion and normalization (M2)

Owner: Harsh Chaudhari. Authority: [file 08](../../docs/specs/08_DATASET_PROFILE_AND_RULES.md),
[common §10](../../docs/specs/02_COMMON_SPEC.md) and [runbook §§2-3](../../docs/specs/09_EVALUATION_RUNBOOK.md).

Turns the unchanged Flipkart CSV into a promoted catalogue plus hashed manifests. Rules are
deterministic and make no model or network calls.

```bash
export PROJECTCTL_ADAPTER_MODULE=pipelines.catalog.adapter
export CATALOG_DATABASE_URL=postgresql://...   # otherwise the infra.postgres local credentials
export LAKEHOUSE_ROOT=/lakehouse               # the source is archived here by SHA-256
S=data/raw/flipkart_com-ecommerce_sample.csv
python -m projectctl catalog profile --source $S --rules flipkart-v1 --out artifacts/catalog/profile
python -m projectctl catalog import --source $S --rules flipkart-v1 --load-mode copy \
    --namespace bench-smoke --out artifacts/catalog/bench-smoke
python -m projectctl catalog verify --manifest artifacts/catalog/bench-smoke/normalized_manifest.json \
    --namespace bench-smoke
```

`--load-mode` selects I0 (`row`, one INSERT per row) or I1 (`copy`). Both use the same stage table,
1,000-row chunks with a checkpoint in the same transaction, and one promotion transaction.

| Stage | Module | Behaviour |
|---|---|---|
| Read, validate, normalize, select | `normalize.py` | Pure functions; a soft issue never drops a row |
| Parquet and manifests | `artifacts.py` | Observations, dispositions, issues, canonical rows; hashes in the manifest |
| Stage and promote | `load.py` | Advisory lock, resume by chunk hash, reconcile, then promote atomically |
| Independent checks | `verify.py` | Re-derives prices and counts with Jaineel's checker, writes `dataset_checks.json` |
| CLI binding | `adapter.py` | `catalog profile/import/verify`, `projection wait` |

`catalog import` applies catalogue migrations itself (`migrate.migrate_catalog`); it holds no other
service's tables. A repeated import of the same source and rules is a no-op, and a killed import
resumes without partial readiness.

Output directory: `source_manifest.json`, `normalized_manifest.json`, `observations.parquet`,
`catalog.parquet`, `dispositions.parquet`, `issues.parquet`, `sku_manifest.json`,
`facet_dictionary.json`, `profile.json`, `quality_by_category.csv`, `import_timings.json`,
`load_report.json`, and `dataset_checks.json` after verify.

Experiments: `python -m pipelines.catalog.experiments import|search --out DIR`. Results and how to
read them are in [docs/harsh/progress.md](../../docs/harsh/progress.md).
