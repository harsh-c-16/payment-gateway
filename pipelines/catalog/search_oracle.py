"""Independent W-SEARCH expectations from catalog.parquet, in plain Python.

Shares no SQL or code with services/catalog/search.py: the hard filters of common §5 are
re-applied to the canonical rows. At the frozen seed every active SKU has stock, so the
eligible pool is the hard-filter pool over active rows. Ranking is not predicted here; the
runner audit checks it for determinism and filter compliance instead.

python -m pipelines.catalog.search_oracle --catalog CATALOG_PARQUET --out EXPECTATIONS_JSON
"""

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path

import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[2]
DICTIONARY = ROOT / "contracts/dictionaries/catalog/flipkart-v1.json"
QUERIES = ROOT / "contracts/fixtures/catalog/queries.json"
COLUMNS = (
    "sku",
    "active",
    "category",
    "category_path",
    "brand_normalized",
    "size",
    "colour",
    "material",
    "price_minor",
    "dataset_revision",
)


def fold(value):
    return " ".join(unicodedata.normalize("NFC", value).split()).casefold()


def rejection(intent, dictionary):
    """The field a valid service must refuse with 422, or None."""
    # File 08 root ids: the lower-cased label with each non-alphanumeric run as one "_".
    roots = {re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") for label in dictionary["roots"]}
    if intent.get("category") is not None and intent["category"] not in roots:
        return "category"
    if intent.get("size") is not None and intent["size"] not in dictionary["allowed_apparel_sizes"]:
        return "size"
    prefix = intent.get("category_path_prefix")
    if prefix is not None and (not prefix or not all(fold(part) for part in prefix)):
        return "category_path_prefix"
    return None


def satisfies(row, intent):
    """Every hard constraint the intent states holds for this canonical row."""
    if intent.get("category") is not None and row["category"] != intent["category"]:
        return False
    if intent.get("size") is not None and row["size"] != intent["size"]:
        return False
    if intent.get("colour") is not None:
        colour = fold(intent["colour"])
        if row["colour"] != ("grey" if colour == "gray" else colour):
            return False
    if intent.get("material") is not None and row["material"] != fold(intent["material"]):
        return False
    if intent.get("brand") is not None and row["brand_normalized"] != fold(intent["brand"]):
        return False
    if intent.get("max_price_minor") is not None and (
        row["price_minor"] is None or row["price_minor"] > intent["max_price_minor"]
    ):
        return False
    prefix = intent.get("category_path_prefix")
    if prefix is not None:
        path = [fold(part) for part in row["category_path"] or []]
        if path[: len(prefix)] != [fold(part) for part in prefix]:
            return False
    return True


def expectations(catalog_path):
    dictionary = json.loads(DICTIONARY.read_text(encoding="utf-8"))
    queries = json.loads(QUERIES.read_text(encoding="utf-8"))["queries"]
    table = pq.read_table(catalog_path)
    rows = [
        row
        for row in table.select([c for c in COLUMNS if c in table.schema.names]).to_pylist()
        if row["active"]
    ]
    results = {}
    for query in queries:
        intent = query["request"]["intent"]
        field = rejection(intent, dictionary)
        results[query["query_id"]] = (
            {"status": "rejected", "field": field}
            if field
            else {
                "status": "ok",
                "eligible_count": sum(satisfies(row, intent) for row in rows),
                "hard_filter_violations": 0,
                "deterministic_hits": True,
            }
        )
    return {
        "schema_version": 1,
        "audit_kind": "W-SEARCH",
        "oracle": "pipelines/catalog/search_oracle.py",
        "seed": {"on_hand": 10000, "reserved": 0, "stock_version": 1},
        "queries_sha256": hashlib.sha256(QUERIES.read_bytes()).hexdigest(),
        "catalog_parquet_sha256": hashlib.sha256(Path(catalog_path).read_bytes()).hexdigest(),
        "active_rows": len(rows),
        "logical_results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--out", required=True)
    arguments = parser.parse_args()
    document = expectations(arguments.catalog)
    Path(arguments.out).write_text(json.dumps(document, indent=1, sort_keys=True) + "\n")
    print(json.dumps({k: document[k] for k in ("active_rows", "queries_sha256")}))


if __name__ == "__main__":
    main()
