# Flipkart dataset: measured profile and import rules

Version 2.0 | 24 October 2026 | Catalogue owner: Harsh | Independent checks: Jaineel

This file reports an actual examination of the complete attached CSV. These are **data-profile observations**, not pipeline performance results. Implementation and performance evaluations remain NOT_RUN. Import rules below are normative extensions of the common specification.

## 1. Decision

**Use this dataset.** It is suitable for a historical, multi-category product catalogue and for evaluating ingestion, normalization, indexing, retrieval, data quality and lineage. Keep the original CSV unchanged and derive versioned normalized outputs.

It is not a transaction log or a live marketplace feed. It supplies no stock counts, trustworthy seller identity, customer sessions, orders, payments or verified sellable size/colour variant hierarchy. Aditya must generate explicitly simulated inventory/payment state; Jaineel must generate reproducible traffic. Vichitr processes the events produced by those services. A CSV catalogue import and a Kafka event stream are different ingestion jobs.

The principal limitation for the original shopping scenario is apparel sizing: the conservative rules in §5 produce only **4 canonical listings with an explicit usable clothing size**. Do not invent sizes or turn a listing into five fictional size variants. The default demo therefore searches the broad catalogue by text, category and price, with optional verified attributes. A size constraint is still enforced strictly, often producing no results. If comprehensive real size-aware shopping later becomes mandatory, add a separately sourced, verified variant dataset and rerun the contracts/evaluations; this CSV alone cannot establish that capability.

No replacement dataset is needed for the current data-engineering evaluation. A larger, explicitly synthetic extension may be used to test scale, with its results separated from the original catalogue.

## 2. File identity and complete-file observations

| Property | Observed value |
|---|---|
| Filename | flipkart_com-ecommerce_sample.csv |
| Size | 38,114,963 bytes, approximately 36.35 MiB |
| SHA-256 | 56f8f699c9e847356666c2eab3c3ab1244340f6a98ad08e39ea2199ebe993ad1 |
| CSV data records / columns | 20,000 / 15 |
| Encoding / parsing | UTF-8 decoded successfully; CSV-aware quoted-field parsing; no inconsistent row widths |
| Unique uniq_id / unique pid | 20,000 / 19,998 |
| Exact duplicate complete rows | 0 |
| Distinct product names | 12,676; repeated names are not a deduplication key |
| Crawl interval | 2015-12-01 06:13:00 UTC to 2016-06-28 08:45:50 UTC |
| Missing discounted_price / retail_price | 78 / 78; the same 78 rows lack both |
| Nonblank prices | All parse as positive whole rupees; none zero, negative, or discounted above retail |
| Observed price range | 35 to 571,230 rupees, for both price columns |
| Missing brand | 5,861 rows, 29.305% |
| Missing description / image | 2 / 3 rows |
| Ratings absent as “No rating available” | 18,151 rows, 90.755% |
| Rated rows | 1,849; product_rating and overall_rating match on every row |
| Category strings | All parse as one-element JSON string arrays; 328 paths contain one segment |
| Category roots | 265 distinct raw first segments; only 32 approved roots from multi-level paths |
| Unclassified rows under approved-root rule | 323; five single-segment rows have the known root Sunglasses |
| Specifications | 19,900 list forms; 33 singleton-object forms; 53 explicit nil forms; 14 blank cells |
| Unkeyed specification entries | 11,920 entries across 7,961 raw rows; preserve them without guessing a key |
| Repeated normalized specification keys | 41 rows; 6 contain conflicting values for a repeated key |
| Keyed specification without a value | 1 entry |

The specifications are Ruby-style hash strings using `=>`, not ordinary JSON. Treating every non-JSON specification as a corrupt product would discard useful data unnecessarily. The bounded normalization rule below handles the observed list, singleton and nil forms without executing source text.

The CSV has no explicit currency column. **INR is the declared project assumption**, supported by the dataset context and rupee wording in descriptions; persist `currency_source=project_assumption`. Prices and stock in the demo must be presented as historical/simulated, not current Flipkart offers. The upload supplies no verified licence record or original download URL; record those provenance fields as unknown rather than inventing them.

## 3. Canonical record selection and exact expected counts

Use `pid` as the source product identity. Use `uniq_id` as the immutable observation identity. Platform `sku` and `product_id` are both `FK-` followed by `pid`; this is a stable **listing-level simulation identifier**, not proof of a real retail variant or parent-product grouping.

For each pid, choose the observation with the latest parsed UTC crawl_timestamp. If timestamps tie and business content is identical, choose lexicographically greatest uniq_id. If equally recent observations conflict, retain both raw records, flag SOURCE_ID_CONFLICT and withhold that pid from promotion until resolved. No such tie conflict occurs in this upload. Never deduplicate by product name, description or embedding similarity.

| Repeated pid | Retain data-record number | Retained uniq_id | Superseded data-record number |
|---|---:|---|---:|
| JEAEGE8Q8GXYFTGU | 3,189 | f4e20863651ea54537388f1cd77a8776 | 9,420 |
| ACCEJ6TESY7AFT5W | 7,770 | 82f424a90d630acc188fcf267160a1fe | 7,723 |

Record numbering is 1-based after the header, using a CSV parser; it is not a physical text-line number. Preserve all 20,000 observations and a lineage link from each selected listing to its source record.

Expected mutually exclusive dispositions for this exact file and rules version flipkart-v1:

| Disposition | Count | Meaning |
|---|---:|---|
| canonical_active | 19,920 | Valid selected listing with a positive discounted price; eligible for simulated inventory seeding |
| canonical_inactive_missing_price | 78 | Selected listing retained with price_minor=null, active=false; cannot be quoted |
| superseded | 2 | Historical observations retained but not duplicated as catalogue listings |
| rejected_mandatory | 0 | No malformed mandatory identity/title/time or conflicting latest identity in the observed upload |
| Total | 20,000 | Sum of exclusive source dispositions |

Thus the catalogue contains **19,998 canonical rows**, of which **19,920 are priced candidates**. Actual availability additionally requires Aditya's inventory and Harsh's valid stock projection. The 78 missing-price rows must not receive zero, average or LLM-invented prices. Do not fall back to an older snapshot to hide a missing current price. A future retail-price fallback would be a separately versioned policy; it is not enabled in v1.

Soft issues can overlap and must not be summed as discarded rows. On the canonical rows: brand is missing for 5,861; category is unknown for 323; description is missing for 2. Under the exact conservative facet rules, 10,918 have usable colour, 10,439 material and 4 apparel size. Among the 19,920 priced candidates the corresponding counts are 10,890, 10,399 and 4; 19,600 have known category and 14,072 have brand.

## 4. Source-to-target mapping

| Source field | Target / transformation | Required failure or null behavior |
|---|---|---|
| uniq_id | source_observation_id; retain original string | Missing/invalid identity: source-row quarantine, no promotion for that observation |
| pid | source_pid; sku=product_id=`FK-<pid>` | Missing/non-ASCII/oversized ID: quarantine; do not allocate a random replacement |
| crawl_timestamp | source_crawled_at, parsed UTC | Invalid time: quarantine; never use import time as replacement |
| product_url | source_url | Preserve for lineage; no crawling or availability claim |
| product_name | title | Unicode NFC, trim/collapse whitespace; missing title: quarantine |
| product_category_tree | category_path_raw plus category_path_normalized and nullable category | JSON string-array parse; split observed path on `>>`; preserve all segments; unknown root is null plus flag |
| retail_price | retail_price_minor nullable | Decimal parse, exact ×100, int64 bounds; invalid value flagged; never float arithmetic |
| discounted_price | price_minor nullable | Same money conversion; positive value required for active=true; missing/invalid price retained inactive |
| image | image_urls[] | JSON array, retain HTTP(S) URLs; blank becomes []; malformed field flagged; no downloads in ingestion |
| is_FK_Advantage_product | is_fk_advantage boolean | Exact true/false parse; not a seller identity, stock signal or quality label |
| description | description nullable | Unicode/whitespace normalization; blank=null; no inferred replacement |
| product_rating / overall_rating | rating nullable; preserve both raw fields | Sentinel → null; numeric decimal must be in [1,5]; disagreement flagged; no rating-based core benchmark |
| brand | brand nullable plus brand_normalized (NFC/whitespace/casefold key) | Blank=null; do not infer from title. Current missing brands are not recovered by a keyed Brand specification |
| product_specifications | ordered specification entries, attributes multimap, unkeyed entries, issue flags; optional facets | Bounded parser in §5; retain raw cell and every duplicate entry |
| No source column | seller_id=null | Do not invent a seller from brand or FK Advantage |
| No source column | stock/payment/session/order state | Generated separately, with simulation provenance |

Price parsing accepts a finite decimal with at most two fractional rupee digits, converts exactly to minor units, and enforces the common unit-price bound. A positive recorded discounted price greater than a valid retail price receives PRICE_INCONSISTENT; retain that recorded sale price without claiming a discount. This anomaly does not occur in the supplied file. Raw source sentinel/invalid values remain in provenance. Import issue codes include MISSING_PRICE, INVALID_PRICE, MISSING_BRAND, MISSING_DESCRIPTION, CATEGORY_UNCLASSIFIED, SPEC_EMPTY, SPEC_NIL, SPEC_UNKEYED, SPEC_VALUE_MISSING, SPEC_PARSE_ERROR, ATTRIBUTE_CONFLICT, SOURCE_ID_CONFLICT and INPUT_BOUND_EXCEEDED; these are catalogue diagnostics, separate from Kafka DLQ dispositions.

Every normalized row additionally carries source_file_sha256, source_row_number, source_observation_id, source_pid, source_crawled_at, rules_version, dictionary_version, import_id, normalized_business_hash, quality_flags[], currency_source and dataset_revision. Store raw observations separately, not in every API hit or Kafka message.

`catalog_version` starts at 1 per newly promoted SKU. An identical import must not change it. Business-content changes increment it once; reprocessing with unchanged business fields updates provenance without fake PRICE_UPDATED events. Initial bulk import emits an import report, not 20,000 invented price-change events. Live price changes still use Harsh's existing atomic price/outbox API.

## 5. Deterministic normalization, with no LLM calls

1. Read with a CSV-aware UTF-8 parser, not line splitting. Verify checksum, header and row widths. A structurally unreadable CSV fails the import before promotion; do not silently skip records. Bound cells to 16 KiB and decoded records to 64 KiB for v1; all observed records fit. Record the limit in the manifest.
2. Archive the original CSV by SHA-256 using Vichitr's FileStore interface. Harsh owns invoking it and writing source-row provenance. Vichitr does not implement a second catalogue cleaner.
3. Parse category/image arrays as JSON. For specifications, scan string/escape boundaries and replace only outside-string `=>` tokens with `:` and the bare token `nil` with JSON `null`; then use a strict JSON parser. Never use eval, executable Ruby/Python, or global replacements inside quoted values. Accept product_specification as a list, singleton object (wrap once), or null (empty). Blank also means empty, with a distinct flag. Reject unsupported structure as an attribute-level diagnostic while preserving the product if its mandatory fields remain valid. Cap nesting at 8 and specification entries at 256.
4. Preserve ordered entries and raw strings. Build a multimap using NFC/whitespace-normalized, casefolded keys. Do not overwrite duplicate keys. Retain unkeyed values in unkeyed_specifications; retain missing-value entries as issues. An exact repeated value may collapse in a derived facet, while conflicting values make that facet unknown.
5. Category: freeze the 32 roots listed in §6. An unrecognized first segment becomes category=null and CATEGORY_UNCLASSIFIED; do not treat a product title as a new department or guess from its text. Store path segments regardless. Root IDs are lowercase ASCII slugs with non-alphanumeric runs replaced by `_`, stripped at ends; eBooks becomes ebooks. Category path filters are casefolded full-segment prefixes, never substring matches. The last segment can be a title/truncated label; do not automatically call it a product type.
6. Colour: take the first present key in color, colour, primary color. Require exactly one distinct nonempty value at that key; otherwise null plus ATTRIBUTE_CONFLICT. Casefold and map only the exact value gray to grey. Preserve compounds such as black, white or multicolor as a single value; do not claim a specific component colour is guaranteed. No image-based extraction.
7. Material: for Clothing use first present fabric, then material; for Furniture primary material, then material; other categories material only. Require one distinct value as above. Casefold whole value; do not equate cotton lycra, cotton blend or 100% cotton with cotton. Keep all source values in attributes. This conservative rule produces the measured coverage in §3.
8. Apparel size: only for root Clothing, use the exact Size key. Accept a single value from XXS, XS, S, M, L, XL, XXL, XXXL, Free Size, One Size; map Small/Medium/Large/Extra Large to S/M/L/XL and exact One Size Fits All / One Size Fit For All / One Size Fits To All to ONE_SIZE. Free Size maps FREE_SIZE. Case/whitespace normalize. The exact wrapper “This product is sold as X by the Brand” may be removed before the same lookup. Set size_kind=apparel_alpha. Other size keys, dimensions, shoe sizes without a scale, multi-value sizes and category-ambiguous sizes remain raw attributes, not an apparel size. This is why only four listings qualify.
9. Occasion remains optional semantic query text. Explicit occasion specifications can contribute to retrieval text, but do not become an invented universal classification. No generative attribute completion, brand inference, taxonomy generation or relevance labelling.
10. Select latest pid observations; create the exclusive disposition ledger; stage canonical rows; atomically promote after reconciliation. An interrupted import leaves catalogue readiness false for that target namespace until resumed and completed. Versioned raw/normalized outputs remain auditable.

Price/quantity filters use exact integers. An unknown attribute never satisfies a non-null hard filter. Unknown category is allowed for unrestricted text search if price/availability are valid. Inactive rows remain inspectable through product lookup but cannot appear as purchasable hits or quote lines.

## 6. Approved category roots

Automation & Robotics; Automotive; Baby Care; Bags, Wallets & Belts; Beauty and Personal Care; Cameras & Accessories; Clothing; Computers; Eyewear; Food & Nutrition; Footwear; Furniture; Gaming; Health & Personal Care Appliances; Home & Kitchen; Home Decor & Festive Needs; Home Entertainment; Home Furnishing; Home Improvement; Household Supplies; Jewellery; Kitchen & Dining; Mobiles & Accessories; Pens & Stationery; Pet Supplies; Sports & Fitness; Sunglasses; Tools & Hardware; Toys & School Supplies; Watches; Wearable Smart Devices; eBooks.

Canonical counts for the largest roots: Clothing 6,197; Jewellery 3,531; Footwear 1,227; Mobiles & Accessories 1,099; Automotive 1,012. The full inventory, per-category null/facet coverage and selected observation IDs are required machine-readable profile outputs when the team implements the importer. Do not hard-code observed counts into production transformation logic; use them as checks for this checksum only.

## 7. Import artifacts and black-box handoff

Harsh creates `data/catalog/<dataset_revision>/source_manifest.json`, `profile.json`, `normalized_manifest.json`, `observations.parquet`, `catalog.parquet`, `dispositions.parquet`, `issues.parquet`, `sku_manifest.json`, `facet_dictionary.json` and optional `embedding_manifest.json`. The raw original lives in immutable source storage; source_manifest points to it. Canonical Parquet contains all 19,998 rows, including 78 inactive rows. sku_manifest contains only the 19,920 active candidates, sorted by sku, with source identity and hashes, no invented stock.

dataset_revision is a digest of the source SHA-256, rules version and canonical dictionary checksum. Harsh's normalized_business_hash excludes run IDs/import timestamps but includes business values, nulls and activity. Define it over the canonical JSON representation of those fields; decimal ratings use canonical decimal strings, money uses integers, nullable fields remain explicit nulls, and ordered arrays retain their order. Catalogue business digest hashes the ordered list of (sku, normalized_business_hash) sorted by SKU. Jaineel independently recomputes sampled and aggregate expectations without importing production normalization code. Aditya consumes sku_manifest through its file contract, verifies its hash, and seeds inventory; he never re-parses this CSV.

For the required performance profile, each active SKU receives simulated on_hand=10,000, reserved=0, stock_version=1; Aditya emits one real simulator STOCK_UPDATED outbox event per seeded SKU. Seed completion includes outbox acknowledgement and Harsh's projection barrier. Test-specific one-unit/expiry fixtures override stock only in dedicated namespaces. Reapplying the same seed is a no-op, not a stock reset. Changing seed requires a fresh test namespace.

Source provenance records this as a user-supplied historical catalogue. Runtime events carry metadata.dataset_revision and metadata.synthetic=true, plus scenario_source=simulation where applicable. Live event_time/produced_at use current simulator operation time; source_crawled_at remains historical lineage. Never backdate new orders to 2016 or use crawl time as streaming latency origin.

## 8. Evaluation implications and scope control

- D-01–D-04 in the runbook verify the full profile, conservative normalization, import idempotency/recovery, and row-insert versus COPY-to-staging performance. Both loading variants preserve identical validation, chunk commits and final promotion.
- Search uses the original canonical catalogue. Queries include missing attributes, unclassified categories, inactive price rows, compound materials/colours, duplicate pid observations and strict size/no-result cases. No uniform fictional distribution is substituted for the real one.
- W-PIPE can use a fixed 10,000-key subset of the active SKU manifest to isolate streaming. Its events are synthetic benchmark facts; it must not mutate real simulator stock or be described as real Flipkart activity.
- The 20,000-row file is enough for correctness and initial index experiments; it may be too small to show a benefit from ANN, parallelism or compaction. Report neutral results. A separate 10×/50× listing clone fixture changes IDs deterministically, preserves lineage to the original pid and is labelled synthetic in every result. It demonstrates scale effects, not additional real product diversity.
- Optional vector embeddings are precomputed once on fixed normalized text/model. No LLM is needed to import, validate, normalize, deduplicate, simulate traffic, calculate Gold or evaluate metrics.
- Do not make rating prediction, recommendation-model training, image processing or model comparison a project workstream. They do not resolve the professor's requested pipeline optimization evidence.

The exact commands, fixtures, metric formulas and owner-specific execution requirements are in 03_EVALUATION_SPEC.md and 09_EVALUATION_RUNBOOK.md. This file supplies observed data expectations, not completed benchmark claims.
