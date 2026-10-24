# P3 independent expectations and oracle handoff

Authority: [P3 playbook](../specs/10_JAINEEL_CODEX_PLAYBOOK.md#p3--independent-fixtures-oracle-and-metric-math),
[dataset §§2–7](../specs/08_DATASET_PROFILE_AND_RULES.md),
[evaluation §§2/5/7/9](../specs/03_EVALUATION_SPEC.md), and
[runbook §§3/4/6/7](../specs/09_EVALUATION_RUNBOOK.md).

## Scope and truth of this checkpoint

This milestone implements independent expectations, read-only reconciliation
primitives and metric math. It does not implement CSV ingestion, a Kafka producer,
Gold reducers, Orders/Inventory/Payments, an assistant/extractor or a scheduler.
Provider code is never imported to calculate an expected answer. No API, database,
model or broker is called by the fixture builder or oracle.

The source checker uses the real local CSV when present, after verifying the
file08 SHA-256. It reads CSV records and independently checks identity/latest crawl,
positive Decimal prices, selected IDs, root classification and disposition counts.
It emits assertions only: no normalized catalogue, archive, load or SKU manifest.
No source file, source-derived catalogue or generated large fixture is committed.
It does not verify Harsh's normalized business digest, nested specification shapes
or the four usable apparel sizes. Those provider/facet checks remain `NOT_RUN`.
The 19,920 priced source candidates do not imply that any are currently in stock.

All clean/corrupt transaction and analytical snapshots in `tests/oracles` are
explicit evidence doubles. Passing them verifies the oracle, not a business
service. Real evidence mode currently returns `INCOMPLETE` pending owner-approved
audit, source-coordinate and active-file membership bindings. No caller can obtain
a P3 real integration pass by changing a fixture's mode label.

## Fixtures and hashes

[Dirty catalogue cases](../../contracts/fixtures/catalog/dirty_catalogue.json) are
authored partial-field expectations for all 13 runbook dirty-fixture families.
They include Decimal price examples, missing sale price with retail present,
latest/tied/conflicting pid observations, safe Ruby-shaped cells, duplicate/unkeyed
attributes, unknown categories, absent/compound facets, category-bound apparel
sizes, UTF-8/quoted multiline CSV, bounds and price-only API update expectations.
The expected fields are literals, not outputs learned from a normalizer. Comparing
them to an explicit output double does not establish D-02/D-03 provider acceptance.
The provider must review field/issue projections and supply a real adapter.

[Assistant scenarios](../../contracts/fixtures/assistant/scenarios.json) contain
60 synthetic scenarios across seven groups: explicit search, ambiguity, missing or
unknown attributes, malicious product descriptions, invalid/timeout model output,
cart/quote/confirmation and unavailable dependencies. Each carries the original six
intent labels, separate optional brand/path labels, explicit call budgets and
review metadata. Every original slot has at least ten positive draft labels.
Labels reflect the user's constraint even when the source cannot satisfy it.
Catalogue binding is null and relevance ground truth is null. All labels are
**machine-drafted, awaiting human review, unfrozen**. Do not report a real F1,
NDCG or assistant-quality result from this draft. No relevance labels were generated.
Harsh's frozen dictionary and the four real size bindings are still required.

`python -m projectctl fixtures build --config configs/evaluation.yaml --seed 42`
writes a fresh `benchmarks/results/fixtures/<run_id>/` bundle. Its CLI manifest and
null performance summary live separately in `benchmarks/results/<run_id>/`.
The bundle contains:

- Copies of the small authored fixtures and a `fixture_index.json` with artifact
  byte hashes, label review status and source-check status.
- `w_quality_expectations.jsonl`: 100,000 deterministic **logical expectations**,
  not EventEnvelope objects or accepted Kafka records. Exactly 98,500 unique valid
  logical IDs, 1,000 duplicates of preceding logical content and 500 invalid cases.
  The ten named 50-record subcases implement the five 100-record invalid groups.
  Identity/content collisions are in the separate adversarial fixture.
- `w_quality_manifest.json`: the P1 fixture schema, seed, expected counts, source
  fixture hashes and logical JSONL hash. `quality_recipe.json` records each invalid
  subcase/reason and keeps SDK wire materialization/Kafka execution `NOT_RUN`.
- `dataset_checks.json`: real independent assertions if the exact CSV is present;
  `NOT_RUN` with no observed counts when absent; `INCOMPLETE` with no count
  assertions when its checksum differs.

Canonical JSON sorts object keys, preserves array order, uses UTF-8 and rejects
nonfinite values. JSONL has LF line endings and is hashed over its exact bytes.
Manifest hashes exclude their own `content_sha256`. Rebuilding the same seed has
the same logical hash; a different seed changes duplicate targets. Execution IDs,
namespace, timestamps, schema IDs and actual SKU mapping must be instantiated by
the reviewed SDK/runner later. Duplicate **wire bytes** must then be preserved and
checked before emission; the logical-content hash is not mislabeled a wire hash.
No existing bundle is overwritten.

## Reconciliation projection and remaining bindings

`benchmarks.reconciliation.reconcile_run(expected, observed)` returns a common
ReconciliationResult inside a harness envelope with explicit test mode, status and
unresolved count. It reads in-memory evidence projections without modifying them.
The projection is a harness input, not another provider's canonical DTO.

Independent expectations contain immutable event/content hashes, exclusive source
dispositions, expected Gold business rows/totals, quote/order bindings, opening
stock, declared replenishments and input-manifest references. Observations contain
dispositions, Silver IDs/content hashes, active/query generation and manifest hashes,
active membership and visibility proofs, business rows/totals, order/reservation/
payment/guard snapshots, signed ledger entries and stock counts.

The oracle checks missing/unexpected IDs, duplicate source/Silver/Gold effects,
changed event content, stale query/source manifests, false receipt-only visibility,
wrong rows/totals, immutable quote prices and identities, duplicate debit effects
even after reversal, payment/ledger currencies and signs, overlapping attempts,
reservation quantities, confirmed/cancelled proofs and inventory conservation.
Reserved stock must equal ACTIVE holds; sold stock comes from COMMITTED items.
Replenishment comes from the independent fixture, never from an unexplained SUT
counter. Pending/MANUAL_REVIEW is unresolved, not success. Missing evidence fails
visibly; no corrective writes or synthetic repairs occur.

Before real integration, Aditya must provide reviewed namespace-scoped audit
exports, signed ledger/guard and reservation proof bindings. Vichitr must bind
source receipts, actual active-file membership/receipt references, manifest/query
generation and business-row exports. Harsh must bind normalized fields/digests and
dictionary/active-SKU manifests. Export provenance and file/hash verification must
be implemented against those canonical contracts before lifting the real-mode
incomplete gate. P3 does not claim that a supplied membership list proves actual
Parquet publication or crash recovery.

## Metrics

`benchmarks.metrics` uses nearest rank (`ceil(q*n)`, one indexed). No samples yields
null, not zero. Quantile output retains sample/completion counts, missing timing and
unresolved counts/percentage. Completed-only quantiles remain labelled; any
unresolved or missing sample leaves whole-cohort p99 unestablished, including the
required warning above 1% unresolved.

Rates use a declared `[start,end)` measurement window and separate drain deadline.
Physical offers and acknowledgements remain separate from unique valid Gold
goodput. Warm-up IDs and drain-only completions cannot inflate goodput. Missing
admission receipts make admission rate null/incomplete; explicit unknown admission
is counted separately. An active-membership proof is required for visibility input.
Clock domains must match. Lag uses next offsets without clamping an inconsistent
sample to zero. Percentage helpers require declared gain/reduction direction and
return null when the baseline is zero.

Six-slot F1 counts a wrong non-null value as FP+FN, missing as FN, unexpected as FP,
and null/null as TN. Slots with no positive labels are reported/excluded with a
reason. Their null matches cannot inflate macro F1. Optional brand/path values are
excluded from the original six and require a separate extension report.

## Manual checkpoint

From repository root, use the locked Python 3.11 environment:

```powershell
uv sync --locked
uv run --locked python -m pytest tests/oracles tests/benchmarks -q
uv run --locked python benchmarks/manual/verify_p3.py
```

The collector prints its fresh `artifacts/p3/<uuid>/` path. Inspect `checks.json`
and `pytest.xml`. Expected missing provider contracts still exit 4 inside this
checkpoint; a matched expected dependency failure is not an integration pass.
All four standalone test suites create their configured cache directory directly
before pytest initializes it, avoiding a reproduced Windows/OneDrive rename denial.
Explicit cache/temp overrides remain supported, and cache warnings remain errors.

1. Open `tiny_math.json`. Check p50/p95/p99 = **30/100/100**, lag **5**, latency
   reduction **20%**, throughput gain **25%**, and null incomplete missing latency.
   These are fixture calculations, not measured SUT timings.
2. Open `fixture_review.json`. Inspect raw/expected ordinary price, missing sale
   price, duplicate pid winner and absent size. The expected sale price is 37900;
   missing price remains null even when retail exists; absent size remains null.
3. Open `oracle_corruptions.json`. Every corruption must be detected for its named
   intended reason; inspect the reversed duplicate debit and false Gold cases.
4. Open `dataset_checks.json`. The exact local CSV should show its known SHA and
   conserved counts, selected rows 3189/7770 and superseded rows 9420/7723. On a
   clean checkout without the upload, expect explicit `NOT_RUN` instead.
5. Review representatives in `assistant_review_samples.json`, then review all 60
   source scenarios with Harsh before freezing labels or claiming quality. Check
   purchase controls remain zero-call and malicious listing text is treated as data.
6. The `fixtures build` command's saved JSON names its bundle. Inspect its hashes,
   logical W-QUALITY counts/subcases and `wire_materialization=NOT_RUN`. Repeat with
   seed 42 to compare the logical hash; seed 43 should change duplicate targets.

Stop before P4. Real D/T correctness cases, load generation, the evaluation runner,
full comparison/report commands and live model quality remain later work.
