# Catalogue data sheet: flipkart-v1

One page on the data behind the prototype. Every number below is read from the committed
manifests in [`data/catalog/flipkart-v1-3a401f32ca99379f8298ce42/`](../../data/catalog/flipkart-v1-3a401f32ca99379f8298ce42/)
or from the 12 November 2026 import of the prototype namespace `dev`. The rules are
[spec 08](../specs/08_DATASET_PROFILE_AND_RULES.md).

## Source

| Item | Value |
|---|---|
| File | `flipkart_com-ecommerce_sample.csv` (user upload, kept unchanged, not in git) |
| Size | 38,114,963 bytes, 20,000 data records, 15 columns |
| Source SHA-256 | `56f8f699c9e847356666c2eab3c3ab1244340f6a98ad08e39ea2199ebe993ad1` |
| Crawl timestamps | 2015-12-01 06:13 UTC to 2016-06-28 08:45 UTC (historical) |
| Licence, original URL | Not supplied; recorded as `null`, not invented |
| Currency | No currency column; INR is the declared project assumption |
| Rules version | `flipkart-v1` |
| Dictionary SHA-256 (LF identity) | `a7d381e90986b23f801eca537a689f2d3e056fa0b58040ecb7c182e2be2f9943` |
| Dataset revision | `flipkart-v1-3a401f32ca99379f8298ce42` = digest of source SHA-256, rules version and dictionary checksum |

## flipkart-v1 rules in short

- `pid` is the product identity and `uniq_id` the observation identity. SKU = `FK-` + `pid`.
- For a repeated `pid`, the latest `crawl_timestamp` wins. The older observation is kept as history
  (`superseded`), never as a second listing. Nothing is deduplicated by title or similarity.
- Prices are parsed as exact decimals into integer paise (minor units), with no float arithmetic.
  `discounted_price` is the selling price; a listing is active only if it is positive.
- Category is the first segment of the category tree, if it is one of the 32 frozen roots;
  otherwise `null` with `CATEGORY_UNCLASSIFIED`.
- Colour, material and apparel size come only from exact specification keys and only when
  one distinct value is present. Nothing is inferred from titles, images or an LLM.
- No generative step anywhere in the import.

## Counts

| Stage | Count |
|---|---:|
| Source observations | 20,000 |
| Canonical listings (unique `pid`) | 19,998 |
| Active listings (positive price, can be stocked and quoted) | 19,920 |
| Inactive listings (missing price, kept with `price_minor = null`) | 78 |
| Superseded observations (older duplicate `pid`) | 2 |
| Rejected rows | 0 |

19,920 + 78 = 19,998 canonical, and 19,998 + 2 = 20,000 observations. The two repeated pids are
`JEAEGE8Q8GXYFTGU` and `ACCEJ6TESY7AFT5W`.

## Manifests and hashes

Committed under `data/catalog/flipkart-v1-3a401f32ca99379f8298ce42/`:

| File | What it holds | Hash |
|---|---|---|
| `source_manifest.json` | Source identity, size, row count, archive descriptor | file SHA-256 `e1586a82…`; source `56f8f699…93ad1` |
| `normalized_manifest.json` | Counts above plus the four Parquet outputs and their hashes | content `0d214b4f88f928c9530f7f5838323c08fe2abfa5fc530c07020207c716a9e35b`; file bytes `6d9e8139…` |
| `sku_manifest.json` | The 19,920 active SKUs, sorted, with source identity (written for namespace `bench-catalog-v1`) | content `f432fd147a2211837c0ab3abb9216047fbdf51bd5a703bcd218e45fe9b1c76b3`; file bytes `609e0ea9…` |
| `facet_dictionary.json` | 32 roots, 3,370 brands, 644 colours, 815 materials, sizes, path prefixes | dictionary identity `a7d381e9…f9943` (LF); file bytes `f4237a2f…` |
| `profile.json` | Column blanks, issue counts, facet coverage | file `9fb6bc06…` |
| `dataset_checks.json` | 19 dataset assertions, all passed (`catalog verify` reruns them) | file `090112d8…` |

Business digest of the whole catalogue (sorted `(sku, normalized_business_hash)`):
`d87f57e638ee1ab75743338516c4cfc1a2acfcc68d8f5493f828e7cfeb9e2bba`. It excludes run IDs and
timestamps, so every import of this file has it. All six runs of the
[import comparison](IMPORT_COMPARISON.md) and the prototype import produced it.

The normalized Parquet files (`catalog`, `observations`, `dispositions`, `issues`) are not in git.
The import writes them next to its manifests, and their hashes are in `normalized_manifest.json`.
On the prototype they are in the `lakehouse_data` Docker volume under `prototype-data/`.

## Missing prices, nullable attributes and historical prices

**Missing prices.** 78 records have neither `discounted_price` nor `retail_price`. They stay in the
catalogue as inactive listings with `price_minor = null` and `inactive_reason = MISSING_PRICE`.
They can be looked up but never appear as purchasable hits, never get stock and never enter a
quote. No zero, average, retail fallback or invented price is used.

**Nullable attributes.** Missing values stay `null`. A `null` never satisfies a hard filter, so
asking for a colour or size the listing does not record excludes it instead of guessing.
Among the 19,920 active listings:

| Attribute | Known | Null |
|---|---:|---:|
| Category | 19,600 | 320 |
| Brand | 14,072 | 5,848 |
| Colour | 10,890 | 9,030 |
| Material | 10,399 | 9,521 |
| Apparel size | 4 | 19,916 |
| Description | 19,918 | 2 |

Only 4 listings have a usable apparel size, so size-filtered searches usually return no results.
That is the honest answer for this file; sizes are not invented.

**Historical prices.** Prices are the 2015–16 crawl values. They are shown in INR as historical
catalogue prices, not current Flipkart offers. Stock (10,000 units per active SKU) and payments
are simulated. Live price changes go through the catalogue price API with an outbox event; the
bulk import does not emit 20,000 fake price-change events.

## Inventory and projection use the same active SKU set

Checked on the prototype after projection readiness, comparing exact sorted SKU lists rather
than counts:

| Set | SKUs |
|---|---:|
| Active catalogue listings (`products`, namespace `dev`) | 19,920 |
| Inventory rows seeded from `sku_manifest.json` (`inventory`) | 19,920 |
| Catalogue stock projection (`stock_projection`) | 19,920 |

The three lists are identical, the Inventory outbox has 0 unpublished rows, and no stock event
was deferred. The SQL and its output are in the rehearsal evidence
(`artifacts/rehearsal-20261112/sku_sets.json`). The seed recorded `seeded_count 19920`,
`skipped_count 0`, manifest hash `4bc9dfd4…`, initial stock digest `79233ffa…`.
