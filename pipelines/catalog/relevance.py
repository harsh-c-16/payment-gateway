"""Blinded candidate pool, rule-derived 0-3 relevance labels, and NDCG@5.

The specification asks for manual labels. The team chose rules instead, so every label file names
its source and every score repeats it; see docs/harsh/relevance_labels.md for what that limits.

    python -m pipelines.catalog.relevance pool --namespace NS --out pool.csv
    python -m pipelines.catalog.relevance label --pool pool.csv --out labels.csv
    python -m pipelines.catalog.relevance score --namespace NS --labels labels.csv --out ndcg.json
"""

import argparse
import csv
import hashlib
import json
import math
import os
import re
from pathlib import Path
from statistics import mean
from uuid import uuid4

import psycopg

from services.catalog.database import Database
from services.catalog.embedding import encoder_from_environment
from services.catalog.search import search_catalog
from shared.contracts.catalog import SearchRequest
from shared.contracts.common import RequestContext

FIXTURES = Path(__file__).resolve().parents[2] / "contracts/fixtures/catalog"
QUERIES = FIXTURES / "queries.json"
KEY = FIXTURES / "relevance_key.json"
LABELS = FIXTURES / "relevance_labels.csv"
POOL_COLUMNS = (
    "query_id",
    "split",
    "query_text",
    "constraints",
    "sku",
    "title",
    "category",
    "brand",
    "price_minor",
    "description",
    "label",
)
LABEL_COLUMNS = ("query_id", "sku", "label", "label_source", "label_reason")
POOL_DEPTH = 10


class NoEvents:
    def append(self, tx, **event):
        pass


def dcg(labels):
    return sum((2**label - 1) / math.log2(rank + 1) for rank, label in enumerate(labels, 1))


def ndcg_at_5(ranked, judged):
    """Unjudged results count 0 here and are reported separately as coverage gaps.

    Returns None when the query has no positive label, which is reported, not scored as zero.
    """
    ideal = dcg(sorted(judged.values(), reverse=True)[:5])
    if ideal == 0:
        return None
    return dcg([judged.get(sku, 0) for sku in ranked[:5]]) / ideal


def _context(namespace):
    return RequestContext(
        namespace=namespace,
        run_id=str(uuid4()),
        user_id="relevance",
        correlation_id=str(uuid4()),
        request_id=str(uuid4()),
        session_id=None,
    )


def run_query(db, spec, mode, namespace, top_k, encoder):
    request = SearchRequest(
        request_id=str(uuid4()),
        session_id=str(uuid4()),
        intent=spec["request"]["intent"],
        top_k=top_k,
        mode=mode,
    )
    return search_catalog(db, NoEvents(), request, _context(namespace), encoder=encoder)


def build_pool(db, namespace, out, *, modes, encoder=None, specs=None):
    """Union of each mode's top results, in a hash order that hides which mode found them."""
    specs = specs or json.loads(QUERIES.read_text(encoding="utf-8"))["queries"]
    rows = []
    for spec in specs:
        pooled = {}
        for mode in modes:
            response = run_query(db, spec, mode, namespace, POOL_DEPTH, encoder)
            pooled.update({hit.sku: hit for hit in response.hits})
        if not pooled:
            continue
        with db.transaction() as tx:
            descriptions = tx.execute(
                "SELECT sku,left(description,300) AS description FROM products "
                "WHERE namespace=%s AND sku = ANY(%s)",
                (namespace, list(pooled)),
            ).fetchall()
        text = {row["sku"]: row["description"] for row in descriptions}
        intent = spec["request"]["intent"]
        constraints = {k: v for k, v in intent.items() if k != "query_text" and v is not None}
        for sku in sorted(
            pooled, key=lambda s: hashlib.sha256(f"{spec['query_id']}{s}".encode()).hexdigest()
        ):
            hit = pooled[sku]
            rows.append(
                {
                    "query_id": spec["query_id"],
                    "split": spec["split"],
                    "query_text": intent["query_text"],
                    "constraints": json.dumps(constraints, sort_keys=True),
                    "sku": sku,
                    "title": hit.title,
                    "category": hit.category,
                    "brand": hit.brand,
                    "price_minor": hit.price_minor,
                    "description": text.get(sku),
                    "label": "",
                }
            )
    with Path(out).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=POOL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def has(phrases, text):
    """First phrase found as whole words, allowing a plural."""
    return next((p for p in phrases if re.search(rf"\b{re.escape(p)}s?\b", text)), None)


def rule_label(key, row):
    """(label, reason) for one pool row; the first matching rule decides.

    Product type comes from the title alone, which is what a shopper sees. Attributes may come from
    the description too, but a brand name is never an attribute. No key means the query has no text,
    so nothing separates its eligible products and the row stays unjudged.
    """
    if key is None:
        return None, "no query text: unjudged"
    title = row["title"].casefold()
    description = (row["description"] or "").casefold()
    hit = has(key.get("exclude", []), title)
    if hit:
        return 0, f"excluded: {hit}"
    bare = title
    for phrase in key.get("not_product", []):
        bare = re.sub(rf"\b{re.escape(phrase)}s?\b", " ", bare)
    if not has(key["product"], bare):
        hit = has(key.get("description_product", []), description)
        if hit:
            return 2, f"{hit} named only in the description"
        hit = has(key.get("related", []), title)
        return (1, f"related: {hit}") if hit else (0, "wanted product not in title")
    brand = (row["brand"] or "").casefold()
    named = title.replace(brand, " ") if brand else title
    groups = key.get("attributes", [])
    if all(has(group, named) for group in groups):
        value, reason = 3, "product and all attributes in title"
    else:
        hit = has(key.get("conflicts", []), named)
        if hit:
            return 1, f"product, but conflicts: {hit}"
        text = f"{named} {description.replace(brand, ' ') if brand else description}"
        missing = [group[0] for group in groups if not has(group, text)]
        value, reason = (
            (2, "product, but missing: " + ", ".join(missing))
            if missing
            else (3, "product in title, attributes in title or description")
        )
    hit = has(key.get("cap", []), title)
    return (2, f"close match only: {hit}") if hit and value > 2 else (value, reason)


def label_pool(pool, out, *, key_path=KEY):
    """Writes labels without any product text, so the file can live beside the query fixture."""
    raw = Path(key_path).read_bytes()
    document = json.loads(raw)
    source = f"{document['version']}:{hashlib.sha256(raw).hexdigest()[:12]}"
    with Path(pool).open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    with Path(out).open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=LABEL_COLUMNS)
        writer.writeheader()
        for row in rows:
            value, reason = rule_label(document["queries"].get(row["query_id"]), row)
            writer.writerow(
                {
                    "query_id": row["query_id"],
                    "sku": row["sku"],
                    "label": "" if value is None else value,
                    "label_source": source,
                    "label_reason": reason,
                }
            )
    return len(rows)


def read_labels(path):
    """Accepts only filled 0-3 labels; a blank cell stays unjudged, never zero."""
    labels = {}
    with Path(path).open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            value = row["label"].strip()
            if not value:
                continue
            if value not in {"0", "1", "2", "3"}:
                raise ValueError(f"label must be 0-3: {row['query_id']} {row['sku']}")
            labels.setdefault(row["query_id"], {})[row["sku"]] = int(value)
    return labels


def label_sources(path):
    with Path(path).open(encoding="utf-8", newline="") as stream:
        return sorted({row.get("label_source") or "unstated" for row in csv.DictReader(stream)})


def score(db, namespace, labels_path, *, modes, encoder=None, specs=None):
    specs = specs or json.loads(QUERIES.read_text(encoding="utf-8"))["queries"]
    labels = read_labels(labels_path)
    if not labels:
        return {"status": "NOT_RUN", "reason": "no human labels present", "modes": {}}
    uniform = sorted(
        query_id
        for query_id, judged in labels.items()
        if len(set(judged.values())) == 1 and max(judged.values()) > 0
    )
    result = {
        "status": "MEASURED",
        "label_sha256": hashlib.sha256(Path(labels_path).read_bytes()).hexdigest(),
        "label_sources": label_sources(labels_path),
        "judged_queries": len(labels),
        # One label throughout scores 1.0 under any ranking, so it says nothing about the ranker.
        "uniform_label_queries": uniform,
        "modes": {},
    }
    for mode in modes:
        scores, no_positive, seen, unjudged = {"dev": [], "held_out": []}, [], 0, 0
        for spec in specs:
            judged = labels.get(spec["query_id"])
            if judged is None:
                continue
            response = run_query(db, spec, mode, namespace, 5, encoder)
            ranked = [hit.sku for hit in response.hits]
            seen += len(ranked)
            unjudged += sum(sku not in judged for sku in ranked)
            value = ndcg_at_5(ranked, judged)
            if value is None:
                no_positive.append(spec["query_id"])
            else:
                scores[spec["split"]].append((spec["query_id"], value))
        result["modes"][mode] = {
            split: {
                "ndcg_at_5": mean(v for _, v in values) if values else None,
                "queries": len(values),
                "ndcg_at_5_excluding_uniform": mean(informative) if informative else None,
                "queries_excluding_uniform": len(informative),
            }
            for split, values in scores.items()
            for informative in [[v for q, v in values if q not in uniform]]
        } | {
            "no_positive_label_queries": no_positive,
            "returned_results": seen,
            "unjudged_results": unjudged,
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    pool = commands.add_parser("pool")
    pool.add_argument("--namespace", required=True)
    pool.add_argument("--out", required=True)
    labelling = commands.add_parser("label")
    labelling.add_argument("--pool", required=True)
    labelling.add_argument("--out", required=True)
    grade = commands.add_parser("score")
    grade.add_argument("--namespace", required=True)
    grade.add_argument("--labels", required=True)
    grade.add_argument("--out", required=True)
    grade.add_argument("--modes", help="comma-separated; hybrid_ann needs the r-ann index")
    arguments = parser.parse_args()
    if arguments.command == "label":
        print(label_pool(arguments.pool, arguments.out))
        return
    db = Database(os.environ["CATALOG_DATABASE_URL"])
    psycopg.connect(db.url).close()
    encoder = encoder_from_environment()
    modes = ("filter_only", "lexical") + (("hybrid_exact",) if encoder else ())
    if arguments.command == "pool":
        print(build_pool(db, arguments.namespace, arguments.out, modes=modes, encoder=encoder))
    else:
        if arguments.modes:
            modes = tuple(arguments.modes.split(","))
        report = score(db, arguments.namespace, arguments.labels, modes=modes, encoder=encoder)
        Path(arguments.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(report["status"])


if __name__ == "__main__":
    main()
