"""Owner-run I0/I1 and B0/O2 comparisons on one host, each trial in a fresh schema.

This is not the P9 runner: it has no frozen resource limits, no outbox write (Aditya's library
is absent) and runs searches closed-loop. Results are labelled accordingly. Usage:

    python -m pipelines.catalog.experiments import --out DIR
    python -m pipelines.catalog.experiments search --out DIR [--scale 10] [--variants B0,O2]
    python -m pipelines.catalog.experiments stress --out DIR [--seconds 30] [--max-connections 4]
"""

import argparse
import json
import math
import os
import platform
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from time import perf_counter
from uuid import uuid4

import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
from psycopg import sql
from psycopg.conninfo import make_conninfo

from pipelines.catalog.adapter import database_url, run_import
from pipelines.catalog.migrate import apply_variant
from services.catalog import products, search
from services.catalog.database import Database
from services.catalog.errors import ServiceError
from shared.contracts.catalog import PriceUpdateRequest, SearchRequest
from shared.contracts.common import RequestContext

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/raw/flipkart_com-ecommerce_sample.csv"
QUERIES = ROOT / "contracts/fixtures/catalog/queries.json"
WARMUPS, EXECUTIONS, REPETITIONS, SEED = 3, 30, 3, 42
PRICE_UPDATES = 2000
# W-SEARCH caps concurrency at 32; the frozen profile gives the catalogue four connections.
STRESS_CLIENTS, STRESS_VARIANTS = (1, 8, 32), ("B0", "O2+P1")


class NoEvents:
    """Skips the outbox write until the shared library exists; declared in every result."""

    mode = "outbox-absent"

    def ready(self):
        pass

    def append(self, tx, **event):
        pass


def nearest_rank(values, quantile):
    ordered = sorted(values)
    return ordered[max(math.ceil(quantile * len(ordered)), 1) - 1] if ordered else None


def latency_summary(values):
    return {
        "count": len(values),
        "p50": nearest_rank(values, 0.50),
        "p95": nearest_rank(values, 0.95),
        "p99": nearest_rank(values, 0.99),
    }


def git_state():
    def git(*arguments):
        return subprocess.run(
            ["git", *arguments], capture_output=True, text=True, cwd=ROOT, check=False
        ).stdout.strip()

    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}


def host_facts():
    memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    return {
        "git": git_state(),
        "cpu_count": os.cpu_count(),
        "total_memory_bytes": memory,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "resource_limits": "none enforced; not the frozen local4c8g profile",
    }


def scoped_url(schema):
    return make_conninfo(database_url(), options=f"-c search_path={schema},public")


def create_schema():
    schema = "exp_" + uuid4().hex
    with psycopg.connect(database_url(), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    return schema


def drop_schema(schema):
    assert schema.startswith("exp_")
    with psycopg.connect(database_url(), autocommit=True) as admin:
        admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def write_json(path, document):
    Path(path).write_text(json.dumps(document, indent=2, default=str) + "\n", encoding="utf-8")


def import_one(arguments):
    """Runs in its own process so CPU time and peak RSS belong to this repetition alone."""
    _, timings = run_import(
        Path(arguments.source),
        load_mode=arguments.mode,
        namespace=arguments.namespace,
        out=arguments.out,
        url=make_conninfo(database_url(), options=f"-c search_path={arguments.schema},public"),
    )
    print(json.dumps(timings))


def run_import_experiment(arguments):
    out = Path(arguments.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    runs = []
    for repetition in range(1, REPETITIONS + 1):
        order = ["row", "copy"]
        rng.shuffle(order)
        for mode in order:
            schema = create_schema()
            namespace = f"bench-import-{mode}-{repetition}"
            try:
                child = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pipelines.catalog.experiments",
                        "import-one",
                        "--source",
                        str(arguments.source),
                        "--mode",
                        mode,
                        "--namespace",
                        namespace,
                        "--schema",
                        schema,
                        "--out",
                        str(out / f"rep{repetition}-{mode}"),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                    cwd=ROOT,
                )
                timings = json.loads(child.stdout.strip().splitlines()[-1])
            finally:
                drop_schema(schema)
            timings["repetition"] = repetition
            runs.append(timings)
            print(
                f"rep {repetition} {mode}: total {timings['raw_to_ready_seconds']:.2f}s, "
                f"staging {timings['stages']['staging_seconds']:.3f}s",
                flush=True,
            )
    digests = {run["logical_digest"] for run in runs}
    summary = {
        "workload": "W-IMPORT",
        "profile": "owner-local; not the frozen profile or the P9 runner",
        "host": host_facts(),
        "repetitions": REPETITIONS,
        "digests_equal": len(digests) == 1,
        "logical_digest": sorted(digests),
        "variants": {},
        "runs": runs,
    }
    for mode, variant in (("row", "I0"), ("copy", "I1")):
        chosen = [run for run in runs if run["load_mode"] == mode]
        staging = [run["stages"]["staging_seconds"] for run in chosen]
        total = [run["raw_to_ready_seconds"] for run in chosen]
        summary["variants"][variant] = {
            "load_mode": mode,
            "staging_seconds": {
                "median": median(staging),
                "min": min(staging),
                "max": max(staging),
            },
            "total_seconds": {"median": median(total), "min": min(total), "max": max(total)},
            "canonical_rows_per_staging_second": 19998 / median(staging),
            "raw_rows_per_total_second": 20000 / median(total),
            "wal_bytes": median(run["wal_bytes"] for run in chosen),
            "client_peak_rss_kib": max(run["client_peak_rss_kib"] for run in chosen),
            "client_cpu_seconds": median(run["client_cpu_seconds"] for run in chosen),
        }
    write_json(out / "summary.json", summary)
    print(json.dumps(summary["variants"], indent=2))


def seed_stock(connection, namespace):
    """File 08 performance profile. Direct SQL only because Aditya's seed is not available."""
    connection.execute(
        "INSERT INTO stock_projection (namespace,sku,on_hand,reserved,stock_version,changed_at,"
        "event_id) SELECT namespace,sku,10000,0,1,clock_timestamp(),gen_random_uuid() "
        "FROM products WHERE namespace=%s AND active",
        (namespace,),
    )


def clone_catalogue(connection, namespace, scale):
    """Synthetic scale fixture: new deterministic SKUs, same content, explicit factor in IDs."""
    columns = [
        row[0]
        for row in connection.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema() AND table_name='products' "
            "AND column_name NOT IN ('sku','product_id') ORDER BY ordinal_position"
        ).fetchall()
    ]
    names = sql.SQL(",").join(map(sql.Identifier, columns))
    for copy in range(1, scale):
        connection.execute(
            sql.SQL(
                "INSERT INTO products (sku,product_id,{names}) "
                "SELECT left(sku,57)||'-X'||%(copy)s,left(sku,57)||'-X'||%(copy)s,{names} "
                "FROM products WHERE namespace=%(namespace)s AND sku NOT LIKE '%%-X%%'"
            ).format(names=names),
            {"copy": copy, "namespace": namespace},
        )


def hit_violations(intent, hit):
    """Independent re-check of each returned hit against the requested constraints."""
    violations = []
    if hit["stock_available"] <= 0:
        violations.append("stock")
    if intent.get("category") and hit["category"] != intent["category"]:
        violations.append("category")
    if intent.get("size") and hit["size"] != intent["size"]:
        violations.append("size")
    if intent.get("colour") and hit["colour"] != intent["colour"]:
        violations.append("colour")
    if intent.get("material") and hit["material"] != intent["material"]:
        violations.append("material")
    if intent.get("brand") and (hit["brand"] or "").casefold() != intent["brand"].casefold():
        violations.append("brand")
    bound = intent.get("max_price_minor")
    if bound is not None and hit["price_minor"] > bound:
        violations.append("price")
    return violations


def make_request(spec, mode):
    return SearchRequest(
        request_id=str(uuid4()),
        session_id=str(uuid4()),
        intent=spec["request"]["intent"],
        top_k=spec["request"]["top_k"],
        mode=mode,
    )


def explain(connection, spec, namespace, mode, directory, variant):
    """Plans for the two statements a search runs, kept as raw text."""
    variant = variant.replace("+", "-")
    request = make_request(spec, mode)
    where, parameters = search.hard_filters(request.intent, namespace)
    statements = {
        "filter": (
            f"SELECT count(*) FROM {search.FROM_ELIGIBLE} WHERE {where}",
            parameters,
        )
    }
    if mode == "filter_only":
        statements["rank"] = (
            f"SELECT {search.HIT_COLUMNS} FROM {search.FROM_ELIGIBLE} WHERE {where} "
            "ORDER BY p.price_minor, p.sku LIMIT 5",
            parameters,
        )
    elif request.intent.query_text.strip():
        statements["rank"] = (
            f"SELECT {search.HIT_COLUMNS}, ts_rank(p.search_vector, {search.TSQUERY}) AS score "
            f"FROM {search.FROM_ELIGIBLE} WHERE {where} AND p.search_vector @@ {search.TSQUERY} "
            "ORDER BY score DESC, p.sku LIMIT 5",
            {**parameters, "text": request.intent.query_text},
        )
    used_index = False
    for name, (statement, values) in statements.items():
        lines = connection.execute("EXPLAIN (ANALYZE, BUFFERS) " + statement, values).fetchall()
        text = "\n".join(line[0] for line in lines)
        used_index = used_index or "products_o2_category_price" in text
        path = directory / variant / mode
        path.mkdir(parents=True, exist_ok=True)
        (path / f"{spec['query_id']}-{name}.txt").write_text(text + "\n", encoding="utf-8")
    return used_index


def price_update_costs(db, namespace, seed):
    """Mutation overhead of the index: identical updates on both variants."""
    context = RequestContext(
        namespace=namespace,
        run_id=str(uuid4()),
        user_id="experiment",
        correlation_id=str(uuid4()),
        request_id=str(uuid4()),
        session_id=None,
    )
    with db.transaction() as tx:
        rows = tx.execute(
            "SELECT sku,price_minor,catalog_version FROM products "
            "WHERE namespace=%s AND active AND sku NOT LIKE '%%-X%%' ORDER BY sku",
            (namespace,),
        ).fetchall()
    random.Random(seed).shuffle(rows)
    durations = []
    for row in rows[:PRICE_UPDATES]:
        started = perf_counter()
        products.update_price(
            db,
            NoEvents(),
            row["sku"],
            PriceUpdateRequest(
                price_minor=max(row["price_minor"] + 100, 1),
                expected_catalog_version=row["catalog_version"],
            ),
            context,
            str(uuid4()),
        )
        durations.append((perf_counter() - started) * 1000)
    return latency_summary(durations)


def experiment_context(namespace):
    return RequestContext(
        namespace=namespace,
        run_id=str(uuid4()),
        user_id="experiment",
        correlation_id=str(uuid4()),
        request_id=str(uuid4()),
        session_id=None,
    )


def prepare_variant(url, namespace, variant, source, import_out, scale=1):
    """Fresh import and seeded stock; an O2 variant then builds its index on the loaded table."""
    run_import(source, load_mode="copy", namespace=namespace, out=import_out, url=url)
    with psycopg.connect(url, autocommit=True) as connection:
        if scale > 1:
            clone_catalogue(connection, namespace, scale)
        seed_stock(connection, namespace)
        build = {"seconds": None, "index_bytes": 0}
        if "O2" in variant:
            started = perf_counter()
            apply_variant(connection, "o2")
            build["seconds"] = perf_counter() - started
            build["index_bytes"] = connection.execute(
                "SELECT pg_relation_size(to_regclass('products_o2_category_price'))"
            ).fetchone()[0]
        else:
            connection.execute("ANALYZE products")
        return build, connection.execute("SELECT pg_table_size('products')").fetchone()[0]


def search_trial(variant, repetition, specs, out, source, scale, executions):
    schema = create_schema()
    url = scoped_url(schema)
    namespace = f"bench-search-{variant.lower().replace('+', '-')}-{repetition}"
    db = Database(url, reuse_connections="P1" in variant)
    rows, plans_used = [], {}
    context = experiment_context(namespace)
    try:
        build, table_bytes = prepare_variant(
            url, namespace, variant, source, out / "import" / f"{variant}-{repetition}", scale
        )
        rng = random.Random(f"{SEED}-{repetition}")
        for mode in ("filter_only", "lexical"):
            order = specs[:]
            rng.shuffle(order)
            for spec in order:
                for _ in range(WARMUPS):
                    search.search_catalog(db, NoEvents(), make_request(spec, mode), context)
                for _ in range(executions):
                    started = perf_counter()
                    response = search.search_catalog(
                        db, NoEvents(), make_request(spec, mode), context
                    )
                    client_ms = (perf_counter() - started) * 1000
                    hits = [hit.model_dump(mode="json") for hit in response.hits]
                    rows.append(
                        {
                            "variant": variant,
                            "repetition": repetition,
                            "mode": mode,
                            "query_id": spec["query_id"],
                            "stratum": spec["stratum"],
                            "eligible_count": response.eligible_count,
                            "candidate_count": response.candidate_count,
                            "returned_skus": [hit["sku"] for hit in hits],
                            "scores": [hit["score"] for hit in hits],
                            "violations": sum(
                                len(hit_violations(spec["request"]["intent"], hit)) for hit in hits
                            ),
                            "filter_ms": response.timings_ms.filter,
                            "rank_ms": response.timings_ms.rank,
                            "server_total_ms": response.timings_ms.total,
                            "client_ms": client_ms,
                        }
                    )
            with psycopg.connect(url, autocommit=True) as connection:
                plans_used[mode] = sum(
                    explain(connection, spec, namespace, mode, out / "plans", variant)
                    for spec in specs
                )
        updates = price_update_costs(db, namespace, SEED + repetition)
        return rows, {
            "variant": variant,
            "repetition": repetition,
            "index_build": build,
            "table_bytes": table_bytes,
            "queries_whose_plans_used_index": plans_used,
            "price_update_ms": updates,
        }
    finally:
        drop_schema(schema)


def run_search_experiment(arguments):
    out = Path(arguments.out)
    out.mkdir(parents=True, exist_ok=True)
    specs = json.loads(QUERIES.read_text(encoding="utf-8"))["queries"]
    rng = random.Random(SEED)
    rows, trials = [], []
    variants = arguments.variants.split(",")
    for repetition in range(1, REPETITIONS + 1):
        order = variants[:]
        rng.shuffle(order)
        for variant in order:
            trial_rows, facts = search_trial(
                variant,
                repetition,
                specs,
                out,
                Path(arguments.source),
                arguments.scale,
                arguments.executions,
            )
            rows += trial_rows
            trials.append(facts)
            print(f"rep {repetition} {variant}: {len(trial_rows)} searches", flush=True)
    pq.write_table(pa.Table.from_pylist(rows), out / "query_results.parquet", compression="zstd")
    write_json(
        out / "summary.json",
        summarize_search(rows, trials, arguments.scale, variants, arguments.executions),
    )


def summarize_search(rows, trials, scale, variants, executions):
    summary = {
        "workload": "W-SEARCH",
        "profile": "owner-local closed-loop; no outbox write; not the P9 open-loop runner",
        "scale_factor": scale,
        "synthetic_scale_fixture": scale > 1,
        "host": host_facts(),
        "generated_at": datetime.now(UTC).isoformat(),
        "executions_per_query": executions,
        "variants": {
            "B0": "no optional index, new connection per transaction",
            "O2": "products(namespace,category,price_minor) B-tree",
            "P1": "reused database sessions, an owner extension outside the core matrix",
            "O2+P1": "both changes",
        },
        "repetitions": REPETITIONS,
        "hard_filter_violations": sum(row["violations"] for row in rows),
        "trials": trials,
        "series": {},
    }
    # Same query, mode and repetition must return the same results with and without the index.
    answers = {}
    for row in rows:
        key = (row["mode"], row["query_id"], row["repetition"])
        answers.setdefault(key, {})[row["variant"]] = row["returned_skus"]
    summary["result_mismatches_between_variants"] = sum(
        1 for value in answers.values() if len({tuple(v) for v in value.values()}) > 1
    )
    summary["eligible_counts"] = {row["query_id"]: row["eligible_count"] for row in rows}
    for mode in ("filter_only", "lexical"):
        for stratum in ("all", "broad", "selective", "zero", "few"):
            for variant in variants:
                per_run = []
                for repetition in range(1, REPETITIONS + 1):
                    chosen = [
                        row
                        for row in rows
                        if row["mode"] == mode
                        and row["variant"] == variant
                        and row["repetition"] == repetition
                        and (stratum == "all" or row["stratum"] == stratum)
                    ]
                    per_run.append(
                        {
                            "client_ms": latency_summary([r["client_ms"] for r in chosen]),
                            "filter_ms": latency_summary([r["filter_ms"] for r in chosen]),
                            "rank_ms": latency_summary([r["rank_ms"] for r in chosen]),
                        }
                    )
                summary["series"][f"{mode}/{stratum}/{variant}"] = {
                    metric: {
                        quantile: {
                            "median": median(run[metric][quantile] for run in per_run),
                            "min": min(run[metric][quantile] for run in per_run),
                            "max": max(run[metric][quantile] for run in per_run),
                        }
                        for quantile in ("p50", "p95", "p99")
                    }
                    for metric in ("client_ms", "filter_ms", "rank_ms")
                }
    return summary


def stress_level(db, requests, context, clients, seconds):
    """Closed loop: each client thread sends its next request when the last one ends.

    Threads share one Database, as handler threads do in a service process, so waits for a free
    connection and the 503s they end in are real. Client work shares the GIL too, so saturated
    throughput describes this one process and not PostgreSQL alone.
    """

    def client(index):
        latencies, rejected, violations = [], 0, 0
        position = index * len(requests) // clients
        deadline = perf_counter() + seconds
        while perf_counter() < deadline:
            spec, mode = requests[position % len(requests)]
            position += 1
            started = perf_counter()
            try:
                response = search.search_catalog(db, NoEvents(), make_request(spec, mode), context)
            except ServiceError:
                rejected += 1
                continue
            latencies.append((perf_counter() - started) * 1000)
            violations += sum(
                len(hit_violations(spec["request"]["intent"], hit.model_dump(mode="json")))
                for hit in response.hits
            )
        return latencies, rejected, violations

    started = perf_counter()
    with ThreadPoolExecutor(clients) as pool:
        results = list(pool.map(client, range(clients)))
    elapsed = perf_counter() - started
    latencies = [ms for found, _, _ in results for ms in found]
    return {
        "clients": clients,
        "seconds": elapsed,
        "completed_per_second": len(latencies) / elapsed,
        "rejected": sum(rejected for _, rejected, _ in results),
        "hard_filter_violations": sum(bad for _, _, bad in results),
        "latency_ms": latency_summary(latencies),
    }


def run_stress_experiment(arguments):
    out = Path(arguments.out)
    out.mkdir(parents=True, exist_ok=True)
    specs = json.loads(QUERIES.read_text(encoding="utf-8"))["queries"]
    rng = random.Random(SEED)
    requests = [(spec, mode) for spec in specs for mode in ("filter_only", "lexical")]
    rng.shuffle(requests)
    levels = []
    for repetition in range(1, REPETITIONS + 1):
        for variant in rng.sample(STRESS_VARIANTS, len(STRESS_VARIANTS)):
            schema = create_schema()
            url = scoped_url(schema)
            namespace = f"bench-stress-{variant.lower().replace('+', '-')}-{repetition}"
            db = Database(
                url, max_connections=arguments.max_connections, reuse_connections="P1" in variant
            )
            context = experiment_context(namespace)
            try:
                prepare_variant(
                    url,
                    namespace,
                    variant,
                    Path(arguments.source),
                    out / "import" / f"{variant}-{repetition}",
                )
                for spec, mode in requests:
                    search.search_catalog(db, NoEvents(), make_request(spec, mode), context)
                for clients in STRESS_CLIENTS:
                    level = stress_level(db, requests, context, clients, arguments.seconds)
                    levels.append({"variant": variant, "repetition": repetition, **level})
                    print(f"rep {repetition} {variant}: {level}", flush=True)
            finally:
                drop_schema(schema)
    series = {}
    for variant in STRESS_VARIANTS:
        for clients in STRESS_CLIENTS:
            runs = [r for r in levels if r["variant"] == variant and r["clients"] == clients]
            series[f"{variant}/{clients}"] = {
                "completed_per_second": median(r["completed_per_second"] for r in runs),
                "p50_ms": median(r["latency_ms"]["p50"] for r in runs),
                "p95_ms": median(r["latency_ms"]["p95"] for r in runs),
                "p99_ms": median(r["latency_ms"]["p99"] for r in runs),
                "rejected": sum(r["rejected"] for r in runs),
                "hard_filter_violations": sum(r["hard_filter_violations"] for r in runs),
            }
    write_json(
        out / "summary.json",
        {
            "workload": "W-SEARCH concurrent client ladder",
            "profile": "owner-local closed-loop threads; no outbox write; not the P9 runner",
            "host": host_facts(),
            "max_connections": arguments.max_connections,
            "seconds_per_level": arguments.seconds,
            "repetitions": REPETITIONS,
            "series": series,
            "levels": levels,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("import", "search", "stress"):
        command = commands.add_parser(name)
        command.add_argument("--out", required=True)
        command.add_argument("--source", default=str(SOURCE))
    commands.choices["search"].add_argument("--scale", type=int, default=1)
    commands.choices["search"].add_argument("--variants", default="B0,O2,P1,O2+P1")
    commands.choices["search"].add_argument("--executions", type=int, default=EXECUTIONS)
    commands.choices["stress"].add_argument("--seconds", type=float, default=30)
    commands.choices["stress"].add_argument("--max-connections", type=int, default=4)
    one = commands.add_parser("import-one")
    for flag in ("--source", "--mode", "--namespace", "--schema", "--out"):
        one.add_argument(flag, required=True)
    arguments = parser.parse_args()
    if arguments.command == "import":
        run_import_experiment(arguments)
    elif arguments.command == "search":
        run_search_experiment(arguments)
    elif arguments.command == "stress":
        run_stress_experiment(arguments)
    else:
        import_one(arguments)


if __name__ == "__main__":
    main()
