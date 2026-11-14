"""Controlled Desktop comparisons. Local provider boundaries, not formal P9 qualification."""

import argparse
import json
import math
import os
import random
import re
import secrets
import subprocess
import threading
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from benchmarks.windows.evidence import (
    ROOT,
    clocks,
    command,
    container_facts,
    desktop_only,
    digest,
    host,
    process_usage,
    write,
)


def distribution(values):
    ordered = sorted(values)
    if not ordered:
        raise ValueError("No measurements")
    return {
        "count": len(values),
        "median": median(values),
        "min": min(values),
        "max": max(values),
        "p95": ordered[math.ceil(0.95 * len(ordered)) - 1],
    }


def compare(baseline, candidate):
    if len(baseline) != len(candidate) or not baseline:
        raise ValueError("Complete paired repetitions required")
    b, c = distribution(baseline), distribution(candidate)
    return {
        "baseline": b,
        "candidate": c,
        "baseline_values": baseline,
        "candidate_values": candidate,
        "lower_is_better": True,
        "improvement_percent": (b["median"] - c["median"]) / b["median"] * 100
        if b["median"]
        else None,
        "paired_improvement_percent": [
            (x - y) / x * 100 if x else None for x, y in zip(baseline, candidate, strict=True)
        ],
    }


@contextmanager
def schema(url):
    name = "win_measure_" + uuid4().hex
    with psycopg.connect(url, autocommit=True) as tx:
        tx.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(name)))
    try:
        yield make_conninfo(url, options=f"-c search_path={name},public -c timezone=UTC")
    finally:
        with psycopg.connect(url, autocommit=True) as tx:
            tx.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(name)))


class Database:
    """A uniquely labelled, limited PostgreSQL container; no retained project volume."""

    def __init__(self, out, cpus, memory_mib):
        self.out, self.cpus, self.memory = out, cpus, memory_mib * 1024 * 1024
        self.name = "group3-windows-measure-" + uuid4().hex[:12]
        self.identity = None

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
                "-p",
                "127.0.0.1::5432",
                "-e",
                "POSTGRES_PASSWORD",
                image,
                env={**os.environ, "POSTGRES_PASSWORD": password},
                timeout=60,
            )
            port = command("docker", "port", self.identity, "5432/tcp").rsplit(":", 1)[1]
            self.url = make_conninfo(
                host="127.0.0.1",
                port=port,
                user="postgres",
                password=password,
                dbname="postgres",
                connect_timeout=3,
            )
            self.worker_url = make_conninfo(self.url, port=5432)
            deadline = time.monotonic() + 60
            while True:
                try:
                    with psycopg.connect(self.url, autocommit=True) as tx:
                        tx.execute("CREATE EXTENSION IF NOT EXISTS vector")
                        settings = {
                            key: tx.execute("SHOW " + key).fetchone()[0]
                            for key in ("fsync", "synchronous_commit", "full_page_writes")
                        }
                    if set(settings.values()) != {"on"}:
                        raise RuntimeError("Database durability settings must be enabled")
                    break
                except psycopg.OperationalError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Isolated PostgreSQL did not become ready") from None
                    time.sleep(0.5)
            self.facts = container_facts([self.identity])[0]
            if (
                self.facts["memory_bytes"] != self.memory
                or self.facts["nano_cpus"] != round(self.cpus * 1e9)
                or self.facts["image"] != image
            ):
                raise RuntimeError("Actual container limits/image differ from requested controls")
            self.facts["durability"] = settings
            self.facts["cgroup_before"] = self.cgroup()
            write(self.out / "resources-before.json", self.facts)
            return self
        except BaseException:
            self.cleanup()
            raise

    def cgroup(self):
        return {
            name: command("docker", "exec", self.identity, "cat", "/sys/fs/cgroup/" + name)
            for name in ("memory.max", "cpu.max", "memory.events", "memory.peak")
        }

    def cleanup(self):
        # A timeout may happen after Docker creates the container but before returning its ID.
        ids = command("docker", "ps", "-aq", "--filter", "name=^/" + self.name + "$")
        if not ids:
            write(self.out / "cleanup.json", {"container_removed": True})
            return
        facts = container_facts([ids])[0]
        if facts["labels"].get("group3.windows.measurement") != self.name:
            raise RuntimeError("Cleanup label mismatch")
        # -v removes only this disposable container's anonymous PostgreSQL volume.
        command("docker", "rm", "-f", "-v", ids)
        remaining = command(
            "docker", "ps", "-aq", "--filter", "label=group3.windows.measurement=" + self.name
        )
        write(self.out / "cleanup.json", {"container_id": ids, "container_removed": not remaining})
        if remaining:
            raise RuntimeError("Measurement PostgreSQL container remains after cleanup")

    def __exit__(self, *exc):
        try:
            write(
                self.out / "resources-after.json",
                {
                    "container": container_facts([self.identity])[0],
                    "cgroup": self.cgroup(),
                },
            )
        finally:
            self.cleanup()


class Observer:
    def __init__(self, database, out):
        self.database, self.out, self.stop = database, out, threading.Event()
        self.errors = []

    def __enter__(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        return self

    def run(self):
        with (self.out / "resource-samples.jsonl").open("w", encoding="utf-8") as stream:
            while not self.stop.is_set():
                try:
                    row = {
                        "at": datetime.now(UTC).isoformat(),
                        "observer": process_usage(),
                        "postgres": json.loads(
                            command(
                                "docker",
                                "stats",
                                "--no-stream",
                                "--format",
                                "{{json .}}",
                                self.database.identity,
                                timeout=30,
                            )
                        ),
                    }
                    stream.write(json.dumps(row) + "\n")
                    stream.flush()
                except Exception as error:
                    self.errors.append(type(error).__name__)
                self.stop.wait(1)  # Docker stats adds acquisition time; actual timestamps retained.

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join(35)
        write(
            self.out / "observer.json",
            {
                "errors": self.errors,
                "usage": process_usage(),
                "sample_interval": "1s plus acquisition time",
            },
        )
        if self.thread.is_alive() or self.errors:
            raise RuntimeError("Resource observer incomplete")


def imports(url, args, rows):
    from pipelines.catalog.adapter import run_import

    for rep, order in paired(args.repetitions, ["I0", "I1"]):
        for variant in order:
            print(f"Import {rep} {variant}", flush=True)
            # Both sides start with an absent archive and pay the same durable write cost.
            os.environ["LAKEHOUSE_ROOT"] = str(args.out / f"import/archive-{rep}-{variant}")
            with schema(url) as scoped:
                _, timings = run_import(
                    args.source,
                    load_mode="row" if variant == "I0" else "copy",
                    namespace="bench-windows-measure",
                    out=args.out / f"import/{rep}-{variant}",
                    url=scoped,
                )
                if (timings["raw_rows"], timings["canonical_rows"], timings["active_rows"]) != (
                    20000,
                    19998,
                    19920,
                ):
                    raise AssertionError("Import source/canonical/active conservation failed")
                rows.append(
                    {
                        "axis": "import",
                        "variant": variant,
                        "repetition": rep,
                        "seconds": timings["raw_to_ready_seconds"],
                        "staging_seconds": timings["stages"]["staging_seconds"],
                        "digest": timings["logical_digest"],
                        "raw": timings,
                    }
                )
                save_rows(args.out, rows)


def paired(repetitions, variants):
    rng = random.Random(42)
    for rep in range(1, repetitions + 1):
        order = list(variants)
        rng.shuffle(order)
        yield rep, order


def searches(url, args, rows):
    from pipelines.catalog.adapter import run_import
    from pipelines.catalog.experiments import seed_stock
    from pipelines.catalog.migrate import apply_variant
    from services.catalog import search
    from shared.contracts.catalog import SearchRequest

    specs = json.loads((ROOT / "contracts/fixtures/catalog/queries.json").read_text())["queries"]
    if args.queries_per_stratum:
        strata = sorted({spec["stratum"] for spec in specs})
        specs = [
            spec
            for stratum in strata
            for spec in sorted(
                (s for s in specs if s["stratum"] == stratum), key=lambda s: s["query_id"]
            )[: args.queries_per_stratum]
        ]
    write(args.out / "search/fixture.json", specs)
    for rep, order in paired(args.repetitions, ["B0", "O2"]):
        for variant in order:
            print(f"Index {rep} {variant}", flush=True)
            with schema(url) as scoped:
                run_import(
                    args.source,
                    load_mode="copy",
                    namespace="bench-windows-measure",
                    out=args.out / f"search/import-{rep}-{variant}",
                    url=scoped,
                )
                with psycopg.connect(scoped, autocommit=True, row_factory=dict_row) as tx:
                    seed_stock(tx, "bench-windows-measure")
                    start = time.perf_counter()
                    if variant == "O2":
                        apply_variant(tx, "o2")
                    build_seconds = time.perf_counter() - start if variant == "O2" else 0
                    indexes = tx.execute(
                        "SELECT indexname,indexdef FROM pg_indexes "
                        "WHERE schemaname=current_schema()"
                    ).fetchall()
                    write(args.out / f"search/indexes-{rep}-{variant}.json", indexes)
                    for mode, rank in (
                        ("filter_only", search.rank_filter_only),
                        ("lexical", search.rank_lexical),
                    ):
                        queries = list(specs)
                        random.Random(42 + rep).shuffle(queries)
                        for spec in queries:
                            request = SearchRequest(
                                request_id=str(uuid4()),
                                session_id=str(uuid4()),
                                **{**spec["request"], "mode": mode},
                            )
                            where, parameters = search.hard_filters(
                                request.intent, "bench-windows-measure"
                            )

                            def execute(
                                where=where, parameters=parameters, rank=rank, request=request
                            ):
                                count = tx.execute(
                                    f"SELECT count(*) AS n FROM {search.FROM_ELIGIBLE} "
                                    f"WHERE {where}",
                                    parameters,
                                ).fetchone()["n"]
                                hits = rank(
                                    tx,
                                    where,
                                    parameters,
                                    request.top_k,
                                    request.intent.query_text,
                                    None,
                                )
                                return {
                                    "eligible_count": count,
                                    "hits": [
                                        (h["sku"], h["price_minor"], h["score"]) for h in hits
                                    ],
                                }

                            for _ in range(3):
                                execute()
                            plan = tx.execute(
                                "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "
                                f"SELECT count(*) FROM {search.FROM_ELIGIBLE} WHERE {where}",
                                parameters,
                            ).fetchone()["QUERY PLAN"]
                            write(
                                args.out / f"search/plans/{rep}-{variant}-{mode}-"
                                f"{spec['query_id']}.json",
                                plan,
                            )
                            for sample in range(args.executions):
                                started = time.perf_counter()
                                result = execute()
                                elapsed = time.perf_counter() - started
                                rows.append(
                                    {
                                        "axis": "index",
                                        "variant": variant,
                                        "repetition": rep,
                                        "query": spec["query_id"],
                                        "mode": mode,
                                        "sample": sample,
                                        "seconds": elapsed,
                                        "result": result,
                                        "index_build_seconds": build_seconds,
                                    }
                                )
                    save_rows(args.out, rows)


def make_pipeline(scoped, root, batch=100):
    from analytics.queries.fixture import offline_cache
    from pipelines.curation import AnalyticsPipeline
    from pipelines.ingestion.receipts import migrate_analytics
    from pipelines.storage import FileStore
    from shared.event_transport.codec import EventCodec

    def connect():
        return psycopg.connect(scoped, autocommit=True)

    with connect() as tx, tx.transaction():
        migrate_analytics(tx)
    return AnalyticsPipeline(
        connect,
        FileStore(root),
        EventCodec(offline_cache(), source_service="catalog"),
        code_commit=os.environ["WINDOWS_MEASURE_COMMIT"],
        sink_batch_max_rows=batch,
    )


def batching(url, args, rows):
    from analytics.queries import fixture
    from analytics.queries.suite import QUERIES, Layout, open_connection, result_digest, run_query
    from pipelines.ingestion import BronzeCapture

    events = None
    for rep, order in paired(args.repetitions, ["B0", "O1"]):
        for variant in order:
            print(f"Batch {rep} {variant}", flush=True)
            with schema(url) as scoped:
                root = args.out / f"batch/{rep}-{variant}"
                root.mkdir(parents=True)
                pipeline = make_pipeline(scoped, root)
                if events is None:
                    rng, events = random.Random(42), []
                    at = "2026-11-01T12:00:00Z"
                    while len(events) < args.events:
                        events += fixture.search_events(
                            pipeline.codec, "bench-windows-measure", rng, at
                        )
                records = fixture.records_for(pipeline.codec, events, "bench-windows-measure", {})
                capture = BronzeCapture(pipeline.store)
                receipts = [
                    capture.ingest_bronze(records[start : start + 100])
                    for start in range(0, len(records), 100)
                ]
                size = 1 if variant == "B0" else 100
                started = time.perf_counter()
                for receipt in receipts:
                    pipeline.curate_silver(
                        receipt, {"run_id": "bench-windows-measure", "sink_batch_max_rows": size}
                    )
                elapsed = time.perf_counter() - started
                with pipeline.connect() as tx:
                    actual = tx.execute(
                        "SELECT sum(new_valid),sum(duplicate_delivery),sum(invalid),"
                        "sum(redelivery_noop),sum(batch_rows) FROM sink_batches"
                    ).fetchone()
                if tuple(actual) != (len(events), 0, 0, 0, len(events)):
                    raise AssertionError("Sink source conservation failed")
                pipeline.publish_snapshot("bench-windows-measure")
                layout = Layout(
                    list(pipeline.active_manifest("bench-windows-measure", "silver").files)
                    + list(pipeline.active_manifest("bench-windows-measure", "gold").files)
                )
                query_results = {}
                with open_connection() as duck:
                    for query in QUERIES:
                        result, _ = run_query(
                            duck, query, layout, root, datetime(2026, 11, 1, tzinfo=UTC)
                        )
                        query_results[query] = result_digest(result)
                rows.append(
                    {
                        "axis": "batch",
                        "variant": variant,
                        "repetition": rep,
                        "seconds": elapsed,
                        "events": len(events),
                        "events_per_second": len(events) / elapsed,
                        "result": query_results,
                        "sink_batch_rows": size,
                    }
                )
                save_rows(args.out, rows)


def compaction(url, args, rows):
    from analytics.queries import fixture
    from analytics.queries.suite import (
        QUERIES,
        build_layouts,
        open_connection,
        result_digest,
        run_query,
    )

    with schema(url) as scoped:
        root = args.out / "compaction/lake"
        root.mkdir(parents=True)
        pipeline = make_pipeline(scoped, root)
        generated = fixture.build(
            pipeline,
            "bench-windows-measure",
            publications=args.publications,
            events_per_publication=100,
            days=3,
        )
        layouts, costs = build_layouts(pipeline, "bench-windows-measure")
        write(
            args.out / "compaction/layouts.json",
            {
                "fixture": generated,
                "costs": costs,
                "layouts": {
                    k: [f.model_dump(mode="json") for f in v.files] for k, v in layouts.items()
                },
            },
        )
        day = (datetime.now(UTC) - timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        for rep, order in paired(args.repetitions, ["small_files", "compacted"]):
            for variant in order:
                print(f"Compaction {rep} {variant}", flush=True)
                with open_connection() as duck:
                    duck.execute("SET threads=1")
                    duck.execute("SET memory_limit='512MB'")
                    for query in QUERIES:
                        for _ in range(3):
                            run_query(duck, query, layouts[variant], root, day)
                        for sample in range(args.executions):
                            result, facts = run_query(duck, query, layouts[variant], root, day)
                            rows.append(
                                {
                                    "axis": "compaction",
                                    "variant": variant,
                                    "repetition": rep,
                                    "query": query,
                                    "sample": sample,
                                    "seconds": facts["wall_ms"] / 1000,
                                    "result": result_digest(result),
                                    "raw": facts,
                                }
                            )
                save_rows(args.out, rows)


def save_rows(out, rows):
    with (out / "measurements.jsonl").open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(json.dumps(row, default=str, allow_nan=False) + "\n")


def run_worker(database, args):
    """Windows orchestration; owner FileStore runs on a durable Docker data volume."""
    name = database.name + "-provider"
    image = command("docker", "image", "inspect", "--format", "{{.Id}}", "group3-m04-storage:local")
    mounts = [
        item
        for directory in (
            "benchmarks",
            "pipelines",
            "analytics",
            "services",
            "shared",
            "infra",
            "projectctl",
            "migrations",
            "contracts",
            "configs",
        )
        for item in (
            "--mount",
            f"type=bind,source={ROOT / directory},destination=/app/{directory},readonly",
        )
    ]
    worker_env = {
        **os.environ,
        "WINDOWS_MEASURE_DATABASE": database.worker_url,
        "WINDOWS_MEASURE_COMMIT": command("git", "rev-parse", "HEAD"),
    }
    identity = None
    try:
        identity = command(
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--label",
            "group3.windows.measurement=" + name,
            "--network",
            "container:" + database.identity,
            "--cpus",
            "1",
            "--memory",
            "1073741824",
            "--memory-swap",
            "1073741824",
            "--pids-limit",
            "256",
            "--workdir",
            "/app",
            "--env",
            "WINDOWS_MEASURE_DATABASE",
            "--env",
            "WINDOWS_MEASURE_COMMIT",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "OMP_NUM_THREADS=1",
            "--env",
            "OPENBLAS_NUM_THREADS=1",
            "--env",
            "ARROW_NUM_THREADS=1",
            *mounts,
            "--mount",
            "type=volume,destination=/evidence",
            "--mount",
            f"type=bind,source={args.source.resolve()},destination=/input.csv,readonly",
            image,
            "python",
            "-u",
            "-m",
            "benchmarks.windows.worker",
            "--repetitions",
            str(args.repetitions),
            "--executions",
            str(args.executions),
            "--events",
            str(args.events),
            "--publications",
            str(args.publications),
            "--queries-per-stratum",
            str(args.queries_per_stratum),
            env=worker_env,
            timeout=60,
        )
        facts = container_facts([identity])[0]
        write(args.out / "provider-resources-before.json", facts)
        if facts["memory_bytes"] != 1073741824 or facts["nano_cpus"] != 1_000_000_000:
            raise RuntimeError("Provider container limit mismatch")
        deadline, logged = time.monotonic() + args.timeout_minutes * 60, 0
        while True:
            logs = command("docker", "logs", identity).splitlines()
            for line in logs[logged:]:
                print(line, flush=True)
            logged = len(logs)
            state = container_facts([identity])[0]["state"]
            if not state["Running"]:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Provider measurements exceeded the configured deadline")
            time.sleep(2)
        if state["ExitCode"] or state["OOMKilled"]:
            log = subprocess.run(
                ["docker", "logs", identity],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=20,
            )
            error_log = re.sub(r"(?i)(password\s*[=:]\s*)[^\s]+", r"\1<redacted>", log.stderr)
            (args.out / "provider-error.log").write_text(error_log, "utf-8")
            raise RuntimeError(
                "Provider measurement failed; retained worker-status.json has details"
            )
    finally:
        ids = command("docker", "ps", "-aq", "--filter", "name=^/" + name + "$")
        if ids:
            facts = container_facts([ids])[0]
            if facts["labels"].get("group3.windows.measurement") != name:
                raise RuntimeError("Provider cleanup label mismatch")
            try:
                write(args.out / "provider-resources-after.json", facts)
                command("docker", "cp", ids + ":/evidence/.", str(args.out), timeout=180)
            finally:
                command("docker", "rm", "-f", "-v", ids)
                remaining = command(
                    "docker", "ps", "-aq", "--filter", "label=group3.windows.measurement=" + name
                )
                write(args.out / "provider-cleanup.json", {"container_removed": not remaining})
                if remaining:
                    raise RuntimeError("Provider container remains after cleanup")
    return [json.loads(line) for line in (args.out / "measurements.jsonl").read_text().splitlines()]


def summarize(rows, repetitions):
    comparisons = {}
    for axis, b, c in (
        ("import", "I0", "I1"),
        ("index", "B0", "O2"),
        ("batch", "B0", "O1"),
        ("compaction", "small_files", "compacted"),
    ):
        chosen = [row for row in rows if row["axis"] == axis]
        keys = sorted({(r.get("mode", ""), r.get("query", "")) for r in chosen})
        for mode, query in keys:
            subset = [
                r for r in chosen if r.get("mode", "") == mode and r.get("query", "") == query
            ]
            # Reject differences across every measured execution, not only a convenient pair.
            outputs = {
                json.dumps(r.get("result", r.get("digest")), sort_keys=True, default=str)
                for r in subset
            }
            if len(outputs) != 1:
                raise AssertionError(f"Logical results differ: {axis}/{mode}/{query}")
            values = []
            for variant in (b, c):
                per_run = []
                for rep in range(1, repetitions + 1):
                    timings = [
                        r["seconds"]
                        for r in subset
                        if r["variant"] == variant and r["repetition"] == rep
                    ]
                    per_run.append(distribution(timings)["median"])
                values.append(per_run)
            comparisons["/".join(filter(None, (axis, mode, query)))] = {
                "baseline_variant": b,
                "candidate_variant": c,
                "correctness_equal": True,
                "unit": "seconds",
                "per_run_statistic": "median",
                **compare(*values),
            }
    return comparisons


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts/windows" / uuid4().hex)
    parser.add_argument(
        "--source", type=Path, default=ROOT / "data/raw/flipkart_com-ecommerce_sample.csv"
    )
    parser.add_argument("--smoke", action="store_true", help="Setup only; no performance claim")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Local triage: 3 pairs, 2 timed samples and 2 queries per stratum",
    )
    parser.add_argument("--timeout-minutes", type=int, default=120)
    parser.add_argument("--cpus", type=float, default=1)
    parser.add_argument("--memory-mib", type=int, default=2048)
    args = parser.parse_args()
    if args.smoke and args.quick or not 1 <= args.timeout_minutes <= 720:
        parser.error("Smoke/quick are exclusive; timeout must be 1..720 minutes")
    desktop_only()
    if not 0 < args.cpus <= 4 or not 512 <= args.memory_mib <= 8192:
        parser.error("Choose a feasible fixed budget: CPUs (0,4], memory 512..8192 MiB")
    args.out = args.out.resolve()
    if not args.out.is_relative_to(ROOT / "artifacts"):
        parser.error("Evidence must stay under this Desktop checkout's ignored artifacts directory")
    args.out.mkdir(parents=True, exist_ok=False)
    expected = "56f8f699c9e847356666c2eab3c3ab1244340f6a98ad08e39ea2199ebe993ad1"
    if digest(args.source) != expected:
        raise RuntimeError("Original Flipkart CSV checksum differs from the pinned source")
    if command("docker", "ps", "-q"):
        raise RuntimeError("Stop running Docker containers before isolated comparisons")
    args.repetitions, args.executions = (1, 2) if args.smoke else (3, 30)
    if args.quick:
        args.executions = 2
    args.queries_per_stratum = 2 if args.quick else 0
    args.events, args.publications = (100, 3) if args.smoke else (1000, 30)
    os.environ["LAKEHOUSE_ROOT"] = str(args.out / "import-archive")
    manifest = {
        "schema_version": 1,
        "status": "RUNNING",
        "host": host(),
        "scope": "Windows Desktop provider comparisons; not formal P9/G4/G5",
        "source_sha256": expected,
        "seed": 42,
        "repetitions": args.repetitions,
        "executions_per_query": args.executions,
        "warmups_per_query": 3,
        "smoke": args.smoke,
        "quick": args.quick,
        "queries_per_stratum": args.queries_per_stratum or "all",
        "import_archive_policy": "fresh absent archive for every measured import",
        "provider_timeout_minutes": args.timeout_minutes,
        "cross_service_latency_qualified": False,
        "limitations": [
            "Search measures count/ranking SQL; excludes HTTP and outbox",
            "Batching measures persisted capture to sink; no Kafka or 50ms wait",
            "Compaction uses labelled synthetic frozen facts and warm cache",
            "PostgreSQL limits fixed; provider container separately limited to 1 CPU/1 GiB",
            "Desktop background processes remain possible interference",
            "Formal P9 readiness/review and integrated correctness gates remain required",
        ],
    }
    rows = []
    write(args.out / "manifest.json", manifest)
    try:
        with Database(args.out, args.cpus, args.memory_mib) as database:
            before = clocks([database.identity])
            write(args.out / "clocks-before.json", before)
            if not before["passed"]:
                raise RuntimeError("Clock verification failed before measurement")
            with Observer(database, args.out):
                rows = run_worker(database, args)
            after = clocks([database.identity])
            write(args.out / "clocks-after.json", after)
            if not after["passed"]:
                raise RuntimeError("Clock verification failed after measurement")
            if any(
                int(line.split()[1])
                for line in database.cgroup()["memory.events"].splitlines()
                if line.split()[0] in {"oom", "oom_kill"}
            ):
                raise RuntimeError("PostgreSQL cgroup recorded an OOM event")
            comparisons = summarize(rows, args.repetitions)
            write(args.out / "comparison.json", comparisons)
            lines = [
                "# Windows Desktop measurements",
                "",
                "Setup smoke only."
                if args.smoke
                else "Three paired repetitions; descriptive local evidence.",
                "",
                "| Comparison | Baseline median s | Candidate median s | Improvement % |",
                "|---|---:|---:|---:|",
            ]
            for name, value in comparisons.items():
                change = value["improvement_percent"]
                lines.append(
                    f"| {name} | {value['baseline']['median']:.6f} | "
                    f"{value['candidate']['median']:.6f} | "
                    + (f"{change:.2f}" if change is not None else "null")
                    + " |"
                )
            lines += ["", *manifest["limitations"]]
            (args.out / "report.md").write_text("\n".join(lines) + "\n", "utf-8")
        manifest["status"] = (
            "SMOKE_ONLY"
            if args.smoke
            else "MEASURED_LOCAL_QUICK"
            if args.quick
            else "MEASURED_LOCAL"
        )
    except BaseException as error:
        manifest.update(status="FAILED", error_type=type(error).__name__)
        raise
    finally:
        # A failed provider already copied its partial journal back from the volume.
        # Never replace that evidence with the controller's still-empty local list.
        if rows or not (args.out / "measurements.jsonl").exists():
            save_rows(args.out, rows)
        manifest["files"] = {
            p.relative_to(args.out).as_posix(): digest(p)
            for p in sorted(args.out.rglob("*"))
            if p.is_file() and p.name != "manifest.json"
        }
        write(args.out / "manifest.json", manifest)
        print(f"Evidence: {args.out} ({manifest['status']})", flush=True)


if __name__ == "__main__":
    main()
