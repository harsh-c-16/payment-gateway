"""Blinded candidate pool for manual 0-3 relevance labels, and NDCG@5 once they exist.

No labels are generated here: runbook §6 forbids unreviewed model labels, so a person fills the
CSV. Until then every NDCG result stays NOT_RUN.

    python -m pipelines.catalog.relevance pool --namespace NS --out pool.csv
    python -m pipelines.catalog.relevance score --namespace NS --labels pool.csv --out ndcg.json
"""

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
from uuid import uuid4

import psycopg

from services.catalog.database import Database
from services.catalog.embedding import encoder_from_environment
from services.catalog.search import search_catalog
from shared.contracts.catalog import SearchRequest
from shared.contracts.common import RequestContext

QUERIES = Path(__file__).resolve().parents[2] / "contracts/fixtures/catalog/queries.json"
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


def score(db, namespace, labels_path, *, modes, encoder=None, specs=None):
    specs = specs or json.loads(QUERIES.read_text(encoding="utf-8"))["queries"]
    labels = read_labels(labels_path)
    if not labels:
        return {"status": "NOT_RUN", "reason": "no human labels present", "modes": {}}
    result = {
        "status": "MEASURED",
        "label_sha256": hashlib.sha256(Path(labels_path).read_bytes()).hexdigest(),
        "judged_queries": len(labels),
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
                scores[spec["split"]].append(value)
        result["modes"][mode] = {
            split: {
                "ndcg_at_5": sum(values) / len(values) if values else None,
                "queries": len(values),
            }
            for split, values in scores.items()
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
    grade = commands.add_parser("score")
    grade.add_argument("--namespace", required=True)
    grade.add_argument("--labels", required=True)
    grade.add_argument("--out", required=True)
    arguments = parser.parse_args()
    db = Database(os.environ["CATALOG_DATABASE_URL"])
    psycopg.connect(db.url).close()
    encoder = encoder_from_environment()
    modes = ("filter_only", "lexical") + (("hybrid_exact",) if encoder else ())
    if arguments.command == "pool":
        print(build_pool(db, arguments.namespace, arguments.out, modes=modes, encoder=encoder))
    else:
        report = score(db, arguments.namespace, arguments.labels, modes=modes, encoder=encoder)
        Path(arguments.out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(report["status"])


if __name__ == "__main__":
    main()
