"""Small, reproducible viva experiments; never changes the prototype's databases.

Run on Windows Desktop: python -m benchmarks.defense --out artifacts/defense/<name>
The PostgreSQL data directory is disposable RAM storage. These are warm component
experiments, not SSD, HTTP/Kafka end-to-end, capacity or formal P9 measurements.
"""

import argparse
import hashlib
import json
import math
import os
import random
import secrets
import shutil
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from uuid import uuid4

import duckdb
import psycopg
from psycopg.conninfo import make_conninfo

from benchmarks.windows.evidence import (
    ROOT,
    command,
    container_facts,
    desktop_only,
    digest,
    host,
    write,
)
from benchmarks.windows.measure import Database

RULES = {
    "none": None,
    "btree": "CREATE INDEX candidate ON products(namespace,category,price_minor)",
    "hash": "CREATE INDEX candidate ON products USING hash(category)",
    "brin": "CREATE INDEX candidate ON products USING brin(category,price_minor) "
    "WITH (pages_per_range=4)",
    "gin": "CREATE INDEX candidate ON products USING gin(search_vector)",
}


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def stats(values):
    if not values or any(not math.isfinite(v) or v < 0 for v in values):
        raise ValueError("finite nonnegative measurements required")
    ordered = sorted(values)
    return {
        "n": len(values),
        "median": median(values),
        "min": min(values),
        "max": max(values),
        "p95": ordered[math.ceil(len(values) * 0.95) - 1],
    }


class ScratchDatabase(Database):
    """Existing pinned image/cleanup guard, smaller explicit RAM-backed budget."""

    def __enter__(self):
        password = secrets.token_urlsafe(32)
        image = json.loads((ROOT / "infra/images.lock.json").read_text())["postgres"]["image"]
        try:
            self.identity = command(
                "docker",
                "run",
                "-d",
                "--name",
                self.name,
                "--label",
                "group3.windows.measurement=" + self.name,
                "--cpus",
                str(self.cpus),
                "--memory",
                str(self.memory),
                "--memory-swap",
                str(self.memory),
                "--pids-limit",
                "128",
                "--tmpfs",
                "/var/lib/postgresql:rw,size=268435456",
                "-p",
                "127.0.0.1::5432",
                "-e",
                "POSTGRES_PASSWORD",
                "-e",
                "PGDATA=/var/lib/postgresql/data",
                image,
                "-c",
                "shared_buffers=32MB",
                "-c",
                "work_mem=4MB",
                "-c",
                "max_wal_size=64MB",
                "-c",
                "min_wal_size=32MB",
                "-c",
                "max_parallel_workers_per_gather=0",
                env={**os.environ, "POSTGRES_PASSWORD": password},
                timeout=60,
            )
            port = command("docker", "port", self.identity, "5432/tcp").rsplit(":", 1)[1]
            self.url = make_conninfo(
                host="127.0.0.1",
                port=port,
                dbname="postgres",
                user="postgres",
                password=password,
                connect_timeout=3,
            )
            deadline = time.monotonic() + 45
            while True:
                try:
                    with psycopg.connect(self.url, autocommit=True) as tx:
                        durability = {
                            k: tx.execute("SHOW " + k).fetchone()[0]
                            for k in ("fsync", "synchronous_commit", "full_page_writes")
                        }
                    break
                except psycopg.OperationalError:
                    if time.monotonic() > deadline:
                        raise RuntimeError("Scratch database readiness timeout") from None
                    time.sleep(0.25)
            self.facts = container_facts([self.identity])[0]
            if (
                self.facts["memory_bytes"] != self.memory
                or self.facts["nano_cpus"] != round(self.cpus * 1e9)
                or set(durability.values()) != {"on"}
            ):
                raise RuntimeError("Scratch resource/durability controls differ")
            write(
                self.out / "resources-before.json",
                {
                    "container": self.facts,
                    "durability": durability,
                    "storage": "256 MiB tmpfs; no disk latency claim",
                },
            )
            return self
        except BaseException:
            self.cleanup()
            raise


def catalogue(source):
    """Reuse canonical normalization/selection, retaining only this probe's fields."""
    from pipelines.catalog.normalize import (
        load_dictionary,
        normalize_catalog_row,
        read_source,
        select_latest_listings,
    )

    dictionary, observations = load_dictionary(), []
    for number, raw in read_source(source, dictionary):
        observation = normalize_catalog_row(raw, number, dictionary)
        observation.fields = {
            k: observation.fields.get(k)
            for k in ("sku", "title", "category", "price_minor", "active")
        }
        observations.append(observation)
    selected = select_latest_listings(observations)
    rows = [o.fields for o in selected.canonical if o.fields["active"]]
    if (len(observations), len(selected.canonical), len(rows)) != (20000, 19998, 19920):
        raise AssertionError("Original catalogue conservation differs")
    return rows, {
        "raw": len(observations),
        "canonical": len(selected.canonical),
        "active": len(rows),
        "source_sha256": digest(source),
        "logical_digest": selected.digest,
    }


def query_cases(rows):
    categories = Counter(r["category"] for r in rows if r["category"] is not None)
    common = categories.most_common(1)[0][0]
    rare = sorted(categories, key=lambda c: (categories[c], c))[0]
    prices = sorted(r["price_minor"] for r in rows if r["category"] == common)
    low = prices[max(0, len(prices) // 10)]
    all_prices = sorted(r["price_minor"] for r in rows)
    cap = all_prices[len(all_prices) // 20]
    return [
        {
            "id": "category_price",
            "sql": "SELECT sku,price_minor FROM products WHERE "
            "namespace=%s AND category=%s AND price_minor<=%s ORDER BY price_minor,sku LIMIT 20",
            "params": ["bench-defense", common, low],
        },
        {
            "id": "category_broad",
            "sql": "SELECT count(*) FROM products WHERE namespace=%s AND category=%s",
            "params": ["bench-defense", common],
        },
        {
            "id": "category_rare",
            "sql": "SELECT count(*) FROM products WHERE namespace=%s AND category=%s",
            "params": ["bench-defense", rare],
        },
        {
            "id": "price_range",
            "sql": "SELECT count(*) FROM products WHERE price_minor<=%s",
            "params": [cap],
        },
        *[
            {
                "id": "lexical_" + term,
                "sql": "SELECT sku, "
                "ts_rank(search_vector,plainto_tsquery('english',%s))::float8 AS score "
                "FROM products WHERE search_vector @@ plainto_tsquery('english',%s) "
                "ORDER BY score DESC,sku LIMIT 20",
                "params": [term, term],
            }
            for term in ("shirt", "wristwatch")
        ],
    ]


def plan_nodes(node):
    return [
        {
            k: node[k]
            for k in (
                "Node Type",
                "Index Name",
                "Actual Rows",
                "Rows Removed by Filter",
                "Rows Removed by Index Recheck",
                "Shared Hit Blocks",
                "Shared Read Blocks",
            )
            if k in node
        }
    ] + [row for child in node.get("Plans", []) for row in plan_nodes(child)]


def index_trials(url, rows, args):
    samples, costs, references = [], [], {}
    reference_rows = {}
    cases = query_cases(rows)
    write(args.out / "query-fixture.json", cases)
    with psycopg.connect(url, autocommit=True) as tx:
        tx.execute("SET timezone='UTC'")
        for layout in ("shuffled", "price_sorted"):
            source = list(rows)
            if layout == "price_sorted":
                source.sort(key=lambda r: (r["price_minor"], r["sku"]))
            else:
                random.Random(args.seed).shuffle(source)
            tx.execute(
                "CREATE TABLE products(namespace text NOT NULL,sku text NOT NULL, "
                "category text,price_minor bigint NOT NULL,title text NOT NULL, "
                "search_vector tsvector GENERATED ALWAYS AS "
                "(to_tsvector('english',title)) STORED, PRIMARY KEY(namespace,sku))"
            )
            with tx.cursor().copy(
                "COPY products(namespace,sku,category,price_minor,title) FROM STDIN"
            ) as copy:
                for r in source:
                    copy.write_row(
                        ("bench-defense", r["sku"], r["category"], r["price_minor"], r["title"])
                    )
            tx.execute("VACUUM ANALYZE products")
            for case in cases:
                result = tx.execute(case["sql"], case["params"]).fetchall()
                if case["id"] in references and fingerprint(result) != references[case["id"]]:
                    raise AssertionError("Layout changed logical results")
                references[case["id"]] = fingerprint(result)
                reference_rows[case["id"]] = result
            write(args.out / "query-reference-results.json", reference_rows)
            rng = random.Random(args.seed)
            for rep in range(1, args.repetitions + 1):
                order = list(RULES)
                rng.shuffle(order)
                for variant in order:
                    print(f"Index {layout} repetition {rep}: {variant}", flush=True)
                    before = tx.execute("SELECT pg_current_wal_insert_lsn()").fetchone()[0]
                    start = time.perf_counter()
                    if RULES[variant]:
                        tx.execute(RULES[variant])
                    build = time.perf_counter() - start if RULES[variant] else 0
                    build_wal = tx.execute(
                        "SELECT pg_wal_lsn_diff(pg_current_wal_insert_lsn(),%s)", (before,)
                    ).fetchone()[0]
                    size = (
                        tx.execute("SELECT pg_relation_size('candidate')").fetchone()[0]
                        if RULES[variant]
                        else 0
                    )
                    for case in random.Random(args.seed + rep).sample(cases, len(cases)):
                        for _ in range(3):
                            tx.execute(case["sql"], case["params"]).fetchall()
                        plan = tx.execute(
                            "EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) " + case["sql"], case["params"]
                        ).fetchone()[0][0]
                        write(args.out / f"plans/{layout}-{rep}-{variant}-{case['id']}.json", plan)
                        for sample in range(args.samples):
                            start = time.perf_counter()
                            result = tx.execute(case["sql"], case["params"]).fetchall()
                            elapsed = time.perf_counter() - start
                            if fingerprint(result) != references[case["id"]]:
                                raise AssertionError("Index changed logical results")
                            samples.append(
                                {
                                    "layout": layout,
                                    "repetition": rep,
                                    "variant": variant,
                                    "query": case["id"],
                                    "sample": sample,
                                    "seconds": elapsed,
                                    "result_sha256": references[case["id"]],
                                    "server_execution_ms": plan["Execution Time"],
                                    "plan": plan_nodes(plan["Plan"]),
                                }
                            )
                    # The same 100 exact SKUs; rolled back, so no changed logical data.
                    ids = sorted(r["sku"] for r in source)[:100]
                    before = tx.execute("SELECT pg_current_wal_insert_lsn()").fetchone()[0]
                    start = time.perf_counter()
                    with tx.transaction(force_rollback=True):
                        tx.execute(
                            "UPDATE products SET price_minor=price_minor+1 "
                            "WHERE namespace='bench-defense' AND sku=ANY(%s)",
                            (ids,),
                        )
                        update_seconds = time.perf_counter() - start
                        update_wal = tx.execute(
                            "SELECT pg_wal_lsn_diff(pg_current_wal_insert_lsn(),%s)", (before,)
                        ).fetchone()[0]
                    costs.append(
                        {
                            "layout": layout,
                            "repetition": rep,
                            "variant": variant,
                            "index_bytes": size,
                            "build_seconds": build,
                            "build_wal_bytes": int(build_wal),
                            "update_100_seconds": update_seconds,
                            "update_100_wal_bytes": int(update_wal),
                        }
                    )
                    if RULES[variant]:
                        tx.execute("DROP INDEX candidate")
                    tx.execute("VACUUM ANALYZE products")
            tx.execute("DROP TABLE products")
    write(args.out / "index-costs.json", costs)
    write(args.out / "index-samples.json", samples)
    return samples, costs


def summary_trials(args):
    """Analytical aggregation example, not a new production retention policy."""
    connection = duckdb.connect(config={"threads": 1, "memory_limit": "64MB"})
    raw, rollup = args.out / "raw.parquet", args.out / "summary.parquet"
    try:
        connection.execute(
            "CREATE TABLE events AS SELECT i AS event_id, "
            "TIMESTAMP '2026-11-01' + i * INTERVAL 1 SECOND AS event_time, "
            "'type-' || (i%4) AS kind, ((i%1000)+1)*100 AS amount_minor "
            "FROM range(?) t(i)",
            [args.events],
        )
        start = time.perf_counter()
        connection.execute(
            "CREATE TABLE summaries AS SELECT date_trunc('minute',event_time) "
            "AS minute,kind,count(*) AS n,sum(amount_minor)::BIGINT AS amount_minor "
            "FROM events GROUP BY 1,2"
        )
        build_seconds = time.perf_counter() - start
        for table, path in (("events", raw), ("summaries", rollup)):
            connection.execute(
                f"COPY {table} TO '{path.as_posix()}' (FORMAT PARQUET,COMPRESSION ZSTD)"
            )
        queries = {
            "raw": f"SELECT kind,count(*)::BIGINT,sum(amount_minor)::BIGINT FROM "
            f"read_parquet('{raw.as_posix()}') GROUP BY kind ORDER BY kind",
            "summary": f"SELECT kind,sum(n)::BIGINT,sum(amount_minor)::BIGINT FROM "
            f"read_parquet('{rollup.as_posix()}') GROUP BY kind ORDER BY kind",
        }
        expected = [
            (
                f"type-{k}",
                len(range(k, args.events, 4)),
                sum(((i % 1000) + 1) * 100 for i in range(k, args.events, 4)),
            )
            for k in range(4)
        ]
        timings = []
        for rep in range(1, args.repetitions + 1):
            for variant in random.Random(args.seed + rep).sample(list(queries), 2):
                for _ in range(3):
                    connection.execute(queries[variant]).fetchall()
                for sample in range(args.samples):
                    start = time.perf_counter()
                    observed = connection.execute(queries[variant]).fetchall()
                    elapsed = time.perf_counter() - start
                    if observed != expected:
                        raise AssertionError("Rollup or raw query differs from independent oracle")
                    timings.append(
                        {
                            "variant": variant,
                            "repetition": rep,
                            "sample": sample,
                            "seconds": elapsed,
                            "result_sha256": fingerprint(observed),
                        }
                    )
        # Two histories with identical aggregates but different per-event monetary facts.
        a, b = [("E1", 100), ("E2", 200)], [("E1", 200), ("E2", 100)]
        collision = {
            "a": a,
            "b": b,
            "count_equal": len(a) == len(b),
            "sum_equal": sum(v for _, v in a) == sum(v for _, v in b),
            "history_equal": a == b,
        }
        # Deliberately unsafe experimental policy: retire the seen ID before a replay.
        connection.execute("CREATE TABLE seen(event_id VARCHAR PRIMARY KEY)")
        counts = []
        for retire_keys in (False, True):
            connection.execute("DELETE FROM seen")
            total = 0
            for attempt in range(2):
                if retire_keys and attempt == 1:
                    connection.execute("DELETE FROM seen")
                total += len(
                    connection.execute(
                        "INSERT INTO seen VALUES ('E1') ON CONFLICT DO NOTHING RETURNING event_id"
                    ).fetchall()
                )
            counts.append(total)
        result = {
            "raw_rows": args.events,
            "summary_rows": connection.execute("SELECT count(*) FROM summaries").fetchone()[0],
            "raw_bytes": raw.stat().st_size,
            "summary_bytes": rollup.stat().st_size,
            "summary_build_seconds": build_seconds,
            "timings": timings,
            "expected_by_type": expected,
            "histories_with_same_summary": collision,
            "duplicate_effects_with_retained_ids": counts[0],
            "duplicate_effects_after_unsafe_id_retirement": counts[1],
            "production_policy_changed": False,
        }
        if counts != [1, 2] or collision["history_equal"]:
            raise AssertionError("Retention counterexample failed")
        write(args.out / "retention.json", result)
        return result
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts/defense" / uuid4().hex)
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--events", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    desktop_only()
    args.out = args.out.resolve()
    if not args.out.is_relative_to(ROOT / "artifacts") or args.out.exists():
        parser.error("Use a fresh directory inside this checkout's artifacts")
    if args.repetitions != 3 or not 5 <= args.samples <= 30 or not 1000 <= args.events <= 50000:
        parser.error("Require three repetitions, 5..30 samples, 1000..50000 events")
    args.out.mkdir(parents=True)
    manifest = {
        "status": "RUNNING",
        "started_at": datetime.now(UTC).isoformat(),
        "scope": "exploratory warm component experiments; not formal P9",
        "formal_p9_qualified": False,
        "seed": args.seed,
        "repetitions": args.repetitions,
        "samples_per_query_per_repetition": args.samples,
        "timing_clock": "one Windows time.perf_counter; no cross-clock subtraction",
        "storage": "PostgreSQL tmpfs, DuckDB local Parquet; warm cache",
        "limitations": [
            "Host background activity is not eliminated; active containers are recorded",
            "Catalogue title/filter projection excludes stock joins and HTTP",
            "GIN is a separately labelled lexical-index experiment",
            "No disk-write latency, cold-cache or sustained throughput claim",
        ],
        "host": host(),
        "free_disk_bytes_before": shutil.disk_usage(ROOT).free,
        "existing_containers": command("docker", "ps", "--format", "{{.Names}} {{.Status}}"),
    }
    write(args.out / "manifest.json", manifest)
    try:
        rows, source = catalogue(ROOT / "data/raw/flipkart_com-ecommerce_sample.csv")
        manifest["catalogue"] = source
        summary_trials(args)
        with ScratchDatabase(args.out, 1, 512) as database:
            index_trials(database.url, rows, args)
        manifest["status"] = "MEASURED_COMPONENT"
    except Exception as error:
        manifest.update(status="FAILED", error_type=type(error).__name__)
        raise
    finally:
        manifest["completed_at"] = datetime.now(UTC).isoformat()
        manifest["files"] = {
            p.relative_to(args.out).as_posix(): digest(p)
            for p in args.out.rglob("*")
            if p.is_file() and p.name != "manifest.json"
        }
        write(args.out / "manifest.json", manifest)
        print(f"Defense evidence: {args.out} ({manifest['status']})", flush=True)


if __name__ == "__main__":
    main()
