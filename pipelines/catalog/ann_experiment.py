"""R-EXACT versus R-ANN (T-06): same frozen vectors, filters and queries; only the index changes.

    EMBEDDING_MODEL_DIR=... python -m pipelines.catalog.ann_experiment --out DIR

Owner-run on one host with no frozen resource limits and no outbox write. Raw HNSW runs without
exact fallback, so shortages stay visible. Reports recall@5 against the exact eligible top 5,
underfilled queries and filter violations by stratum, and database and full search latency apart.
"""

import argparse
import hashlib
import json
import os
import random
from pathlib import Path
from statistics import mean, median
from time import perf_counter
from uuid import uuid4

import psycopg
import pyarrow as pa
import pyarrow.parquet as pq

from pipelines.catalog.adapter import run_import
from pipelines.catalog.embeddings import build_embeddings
from pipelines.catalog.experiments import (
    QUERIES,
    REPETITIONS,
    SEED,
    SOURCE,
    WARMUPS,
    NoEvents,
    create_schema,
    drop_schema,
    hit_violations,
    host_facts,
    latency_summary,
    make_request,
    scoped_url,
    seed_stock,
    write_json,
)
from pipelines.catalog.migrate import apply_variant
from services.catalog import search
from services.catalog.database import Database
from services.catalog.embedding import Encoder, vector_text
from shared.contracts.catalog import ShoppingIntent
from shared.contracts.common import RequestContext

EF_SEARCH = (40, 100, 200)
K = 5
BRANCH_EXECUTIONS = 30
API_EXECUTIONS = 10


def query_text(spec):
    intent = spec["request"]["intent"]
    return " ".join(part for part in (intent["query_text"], intent["occasion"]) if part).strip()


def freeze_inputs(specs, source, encoder, out):
    """One embedding run and one set of query vectors, reused unchanged by every trial."""
    schema = create_schema()
    url = scoped_url(schema)
    namespace = "bench-ann-freeze"
    try:
        run_import(source, load_mode="copy", namespace=namespace, out=out / "import", url=url)
        with psycopg.connect(url, autocommit=True) as connection:
            manifest = build_embeddings(connection, namespace, encoder, out=out)
            rows = connection.execute(
                "SELECT sku,embedding::text,embedding_revision,embedding_text_hash FROM products "
                "WHERE namespace=%s ORDER BY sku",
                (namespace,),
            ).fetchall()
    finally:
        drop_schema(schema)
    names = ("sku", "embedding", "revision", "text_hash")
    pq.write_table(
        pa.Table.from_pylist([dict(zip(names, row, strict=True)) for row in rows]),
        out / "vectors.parquet",
        compression="zstd",
    )
    query_vectors = {}
    for spec in specs:
        text = query_text(spec)
        if text:
            vectors, _ = encoder.encode([text])
            query_vectors[spec["query_id"]] = vector_text(vectors[0])
    frozen = json.dumps(query_vectors, sort_keys=True)
    (out / "query_vectors.json").write_text(frozen, encoding="utf-8")
    return manifest, rows, query_vectors, hashlib.sha256(frozen.encode()).hexdigest()


def load_vectors(connection, namespace, rows):
    with connection.transaction():
        connection.execute(
            "CREATE TEMP TABLE frozen_vectors (sku text, embedding vector(384), revision text, "
            "text_hash char(64)) ON COMMIT DROP"
        )
        with connection.cursor().copy("COPY frozen_vectors FROM STDIN") as copy:
            for row in rows:
                copy.write_row(row)
        connection.execute(
            "UPDATE products p SET embedding=f.embedding,embedding_revision=f.revision,"
            "embedding_text_hash=f.text_hash FROM frozen_vectors f "
            "WHERE p.namespace=%s AND p.sku=f.sku",
            (namespace,),
        )


def timed_branch(db, branch, intent, namespace, vector, repeats, **options):
    """Database-only ranking time, with the shared filter statement outside the timer."""
    durations, result = [], []
    for _ in range(repeats):
        with db.transaction() as tx:
            where, parameters = search.hard_filters(intent, namespace)
            started = perf_counter()
            result = branch(tx, where, parameters, vector, K, **options)
            durations.append((perf_counter() - started) * 1000)
    return durations, [row["sku"] for row in result]


def facts_for(db, namespace, skus):
    with db.transaction() as tx:
        return tx.execute(
            "SELECT p.sku,p.category,p.size,p.colour,p.material,p.brand,p.price_minor,"
            "coalesce(s.available,0) AS stock_available,p.active FROM products p "
            "LEFT JOIN stock_projection s USING (namespace,sku) "
            "WHERE p.namespace=%s AND p.sku = ANY(%s)",
            (namespace, skus),
        ).fetchall()


def ann_plan_uses_index(db, intent, namespace, vector):
    with db.transaction() as tx:
        where, parameters = search.hard_filters(intent, namespace)
        for name in ("enable_seqscan", "enable_bitmapscan", "enable_sort"):
            tx.execute("SELECT set_config(%s,'off',true)", (name,))
        plan = tx.execute(
            f"EXPLAIN SELECT p.sku FROM {search.FROM_ELIGIBLE} WHERE {where} "
            "AND p.embedding IS NOT NULL ORDER BY p.embedding <=> %(vector)s::vector LIMIT 5",
            {**parameters, "vector": vector},
        ).fetchall()
    return any("products_r_ann_hnsw" in row["QUERY PLAN"] for row in plan)


def trial(variant, repetition, specs, source, out, vector_rows, query_vectors, encoder):
    schema = create_schema()
    url = scoped_url(schema)
    namespace = f"bench-ann-{variant.lower()}-{repetition}"
    db = Database(url)
    context = RequestContext(
        namespace=namespace,
        run_id=str(uuid4()),
        user_id="experiment",
        correlation_id=str(uuid4()),
        request_id=str(uuid4()),
        session_id=None,
    )
    records, api, top5 = [], [], {}
    try:
        run_import(
            source,
            load_mode="copy",
            namespace=namespace,
            out=out / "import" / f"{variant}-{repetition}",
            url=url,
        )
        build = {"seconds": None, "index_bytes": 0}
        with psycopg.connect(url, autocommit=True) as connection:
            seed_stock(connection, namespace)
            load_vectors(connection, namespace, vector_rows)
            if variant == "R-ANN":
                started = perf_counter()
                apply_variant(connection, "r-ann")
                build["seconds"] = perf_counter() - started
                build["index_bytes"] = connection.execute(
                    "SELECT pg_relation_size(to_regclass('products_r_ann_hnsw'))"
                ).fetchone()[0]
            else:
                connection.execute("ANALYZE products")
        hnsw_plans = 0
        for spec in specs:
            vector = query_vectors.get(spec["query_id"])
            if vector is None:
                continue
            intent = ShoppingIntent(**spec["request"]["intent"])
            with db.transaction() as tx:
                _, _, eligible = search.filter_catalog(tx, intent, namespace)
            timed_branch(db, search.exact_search, intent, namespace, vector, WARMUPS)
            times, exact = timed_branch(
                db, search.exact_search, intent, namespace, vector, BRANCH_EXECUTIONS
            )
            base = {
                "variant": variant,
                "repetition": repetition,
                "query_id": spec["query_id"],
                "stratum": spec["stratum"],
                "eligible": eligible,
            }
            records.append(
                {
                    **base,
                    "branch": "exact",
                    "ef_search": None,
                    "wall_ms": times,
                    "returned": len(exact),
                    "recall": None,
                    "violations": 0,
                }
            )
            if variant == "R-ANN":
                hnsw_plans += ann_plan_uses_index(db, intent, namespace, vector)
                for ef_search in EF_SEARCH:
                    config = {"ef_search": ef_search, "iterative_scan": "strict_order"}
                    timed_branch(
                        db,
                        search.ann_search,
                        intent,
                        namespace,
                        vector,
                        WARMUPS,
                        ann_config=config,
                    )
                    times, found = timed_branch(
                        db,
                        search.ann_search,
                        intent,
                        namespace,
                        vector,
                        BRANCH_EXECUTIONS,
                        ann_config=config,
                    )
                    wanted = min(K, len(exact))
                    bad = sum(
                        len(hit_violations(spec["request"]["intent"], row)) + (not row["active"])
                        for row in facts_for(db, namespace, found)
                    )
                    records.append(
                        {
                            **base,
                            "branch": "hnsw",
                            "ef_search": ef_search,
                            "wall_ms": times,
                            "returned": len(found),
                            "recall": len(set(found) & set(exact)) / wanted if wanted else None,
                            "underfilled": bool(wanted) and len(found) < wanted,
                            "violations": bad,
                        }
                    )
            # Full search path, including one query encoding per call.
            mode = "hybrid_ann" if variant == "R-ANN" else "hybrid_exact"
            for index in range(API_EXECUTIONS):
                started = perf_counter()
                response = search.search_catalog(
                    db, NoEvents(), make_request(spec, mode), context, encoder=encoder
                )
                api.append(
                    {
                        "variant": variant,
                        "repetition": repetition,
                        "query_id": spec["query_id"],
                        "client_ms": (perf_counter() - started) * 1000,
                        "embedding_ms": response.timings_ms.embedding,
                        "rank_ms": response.timings_ms.rank,
                    }
                )
                if index == 0:
                    top5[spec["query_id"]] = [hit.sku for hit in response.hits]
        return records, api, top5, {"build": build, "queries_with_hnsw_plan": hnsw_plans}
    finally:
        drop_schema(schema)


def summarize(records, api, top5_by_variant, facts, manifest, query_hash):
    series = {}
    for label, chosen in (
        ("exact", [r for r in records if r["branch"] == "exact"]),
        *((f"hnsw_ef{ef}", [r for r in records if r["ef_search"] == ef]) for ef in EF_SEARCH),
    ):
        for stratum in ("all", "broad", "selective", "few", "zero"):
            rows = [r for r in chosen if stratum == "all" or r["stratum"] == stratum]
            per_run = [
                latency_summary(
                    [ms for r in rows if r["repetition"] == repetition for ms in r["wall_ms"]]
                )
                for repetition in range(1, REPETITIONS + 1)
            ]
            scored = [r["recall"] for r in rows if r["recall"] is not None]
            with_results = [r for r in rows if min(K, r["eligible"]) > 0]
            series[f"{label}/{stratum}"] = {
                "db_p50_ms": median(run["p50"] for run in per_run if run["p50"] is not None),
                "db_p95_ms": median(run["p95"] for run in per_run if run["p95"] is not None),
                "db_p99_ms": median(run["p99"] for run in per_run if run["p99"] is not None),
                "recall_at_5_mean": mean(scored) if scored else None,
                "recall_queries": len(scored),
                "underfilled_rate": (
                    sum(bool(r.get("underfilled")) for r in with_results) / len(with_results)
                    if with_results and label != "exact"
                    else None
                ),
                "zero_eligible_queries": sum(r["eligible"] == 0 for r in rows),
                "hard_filter_violations": sum(r["violations"] for r in rows),
            }
    api_summary = {}
    for variant in ("R-EXACT", "R-ANN"):
        chosen = [row for row in api if row["variant"] == variant]
        api_summary[variant] = {
            name: latency_summary([row[name] for row in chosen])
            for name in ("client_ms", "embedding_ms", "rank_ms")
        }
    overlaps = []
    for repetition in range(1, REPETITIONS + 1):
        exact, ann = top5_by_variant["R-EXACT", repetition], top5_by_variant["R-ANN", repetition]
        for query_id, wanted in exact.items():
            if wanted:
                overlaps.append(len(set(wanted) & set(ann[query_id])) / len(wanted))
    return {
        "workload": "W-SEARCH R-EXACT/R-ANN",
        "profile": "owner-local closed-loop; no outbox write; not the P9 runner",
        "host": host_facts(),
        "embedding_manifest": manifest.model_dump(mode="json"),
        "query_vectors_sha256": query_hash,
        "hnsw": {"m": 16, "ef_construction": 64, "iterative_scan": "strict_order"},
        "trials": facts,
        "series": series,
        "full_search_api": api_summary,
        "hybrid_top5_overlap_mean": mean(overlaps) if overlaps else None,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--source", default=str(SOURCE))
    arguments = parser.parse_args()
    out = Path(arguments.out)
    out.mkdir(parents=True, exist_ok=True)
    specs = json.loads(QUERIES.read_text(encoding="utf-8"))["queries"]
    source = Path(arguments.source)
    encoder = Encoder(os.environ["EMBEDDING_MODEL_DIR"])
    manifest, vector_rows, query_vectors, query_hash = freeze_inputs(specs, source, encoder, out)
    print(f"frozen: {manifest.row_count} vectors in {manifest.encode_seconds:.1f}s", flush=True)
    rng = random.Random(SEED)
    records, api, facts, top5 = [], [], [], {}
    for repetition in range(1, REPETITIONS + 1):
        order = ["R-EXACT", "R-ANN"]
        rng.shuffle(order)
        for variant in order:
            found, calls, tops, info = trial(
                variant, repetition, specs, source, out, vector_rows, query_vectors, encoder
            )
            records += found
            api += calls
            top5[variant, repetition] = tops
            facts.append({"variant": variant, "repetition": repetition, **info})
            print(f"rep {repetition} {variant}: {info}", flush=True)
    pq.write_table(
        pa.Table.from_pylist(records), out / "branch_results.parquet", compression="zstd"
    )
    write_json(out / "summary.json", summarize(records, api, top5, facts, manifest, query_hash))


if __name__ == "__main__":
    main()
