"""F-COMPACT and F-PARTITION on one frozen snapshot, real publisher, Q1-Q6 3+30 x 3 reps.

python -m analytics.queries.experiment --out DIR [--publications 300 --events 200] [--cold]
Owner-run on one host without frozen limits; labelled so in the summary it writes. --cold needs
Linux and an output directory on real storage: eviction does nothing on a RAM-backed filesystem.
"""

import argparse
import json
import math
import os
import platform
import random
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from time import perf_counter
from uuid import uuid4

import psycopg
import pyarrow as pa
import pyarrow.parquet as pq
from psycopg import sql
from psycopg.conninfo import make_conninfo

from analytics.compaction.compact import (
    LayoutConfig,
    compact_snapshot,
    rewrite_unpartitioned,
)
from analytics.queries import fixture
from analytics.queries.suite import QUERIES, open_connection, result_digest, run_query
from pipelines.catalog.experiments import git_state
from pipelines.curation import AnalyticsPipeline
from pipelines.ingestion.receipts import migrate_analytics
from pipelines.storage import FileStore
from shared.event_transport.codec import EventCodec

WARMUPS, EXECUTIONS, REPETITIONS, SEED = 3, 30, 3, 42
COLD_EXECUTIONS = 5


def nearest(values, quantile):
    ordered = sorted(values)
    return ordered[max(math.ceil(quantile * len(ordered)), 1) - 1]


class Layout:
    """Minimal manifest view so unpartitioned rewrites share the query path."""

    def __init__(self, files):
        self.files = files


def measure(layouts, store_root, day, out):
    """Same query order for every layout within a repetition; layout order is shuffled."""
    rng, rows, digests = random.Random(SEED), [], defaultdict(dict)
    for repetition in range(1, REPETITIONS + 1):
        names = list(layouts)
        rng.shuffle(names)
        for name in names:
            connection = open_connection()
            order = list(QUERIES) * EXECUTIONS
            rng.shuffle(order)
            for query_id in QUERIES:
                for _ in range(WARMUPS):
                    run_query(connection, query_id, layouts[name], store_root, day)
            for query_id in order:
                result, facts = run_query(connection, query_id, layouts[name], store_root, day)
                digests[query_id].setdefault(name, result_digest(result))
                if digests[query_id][name] != result_digest(result):
                    raise AssertionError(f"{query_id} is not deterministic on {name}")
                rows.append(
                    {"layout": name, "repetition": repetition, "query_id": query_id, **facts}
                )
            connection.close()
            print(f"rep {repetition} layout {name} done", flush=True)
    pq.write_table(pa.Table.from_pylist(rows), out / "query_results.parquet", compression="zstd")
    return rows, digests


def evict(files, store_root):
    """Drops these files from the OS page cache without root. Dirty pages must be written first."""
    for descriptor in files:
        handle = os.open(Path(store_root) / descriptor.path, os.O_RDONLY)
        try:
            os.fsync(handle)
            os.posix_fadvise(handle, 0, 0, os.POSIX_FADV_DONTNEED)
        finally:
            os.close(handle)


def storage_read_bytes():
    """Bytes this process fetched from storage, which proves whether an eviction really happened."""
    for line in Path("/proc/self/io").read_text().splitlines():
        if line.startswith("read_bytes:"):
            return int(line.split()[1])
    raise OSError("read_bytes is missing from /proc/self/io")


def measure_cold(layouts, store_root, day, out):
    """Same eviction before every execution of every layout, in a separate series and file."""
    rng, rows, digests = random.Random(SEED + 1), [], defaultdict(dict)
    for repetition in range(1, REPETITIONS + 1):
        names = list(layouts)
        rng.shuffle(names)
        for name in names:
            order = list(QUERIES) * COLD_EXECUTIONS
            rng.shuffle(order)
            for query_id in order:
                evict(layouts[name].files, store_root)
                connection = open_connection()
                before = storage_read_bytes()
                result, facts = run_query(connection, query_id, layouts[name], store_root, day)
                fetched = storage_read_bytes() - before
                connection.close()
                digests[query_id].setdefault(name, result_digest(result))
                rows.append(
                    {
                        "layout": name,
                        "repetition": repetition,
                        "query_id": query_id,
                        "storage_read_bytes": fetched,
                        **facts,
                    }
                )
            print(f"cold rep {repetition} layout {name} done", flush=True)
    pq.write_table(
        pa.Table.from_pylist(rows), out / "query_results_cold.parquet", compression="zstd"
    )
    return rows, digests


def summarize_cold(rows, layouts):
    series = summarize(rows, layouts)
    for key, value in series.items():
        query_id, name = key.split("/")
        value["median_storage_read_bytes"] = median(
            row["storage_read_bytes"]
            for row in rows
            if row["layout"] == name and row["query_id"] == query_id
        )
    return series


def summarize(rows, layouts):
    series = {}
    for name in layouts:
        for query_id in QUERIES:
            per_run = []
            for repetition in range(1, REPETITIONS + 1):
                chosen = [
                    row
                    for row in rows
                    if row["layout"] == name
                    and row["query_id"] == query_id
                    and row["repetition"] == repetition
                ]
                times = [row["wall_ms"] for row in chosen]
                per_run.append(
                    {
                        "p50": nearest(times, 0.5),
                        "p95": nearest(times, 0.95),
                        "files": chosen[0]["files_opened"],
                        "selected_bytes": chosen[0]["selected_file_bytes"],
                        "syscall_read_bytes": median(r["syscall_read_bytes"] or 0 for r in chosen),
                        "returned": chosen[0]["returned_rows"],
                    }
                )
            series[f"{query_id}/{name}"] = {
                "p50_ms": median(run["p50"] for run in per_run),
                "p50_ms_range": [min(r["p50"] for r in per_run), max(r["p50"] for r in per_run)],
                "p95_ms": median(run["p95"] for run in per_run),
                "files_opened": per_run[0]["files"],
                "selected_file_bytes": per_run[0]["selected_bytes"],
                "median_syscall_read_bytes": median(run["syscall_read_bytes"] for run in per_run),
                "returned_rows": per_run[0]["returned"],
            }
    return series


def layout_facts(manifest_files):
    return {
        "file_count": len(manifest_files),
        "total_bytes": sum(f.byte_size for f in manifest_files),
        "rows": sum(f.row_count for f in manifest_files),
        "median_file_bytes": median(f.byte_size for f in manifest_files) if manifest_files else 0,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--publications", type=int, default=300)
    parser.add_argument("--events", type=int, default=200)
    parser.add_argument("--cold", action="store_true", help="add the separate cold-cache series")
    arguments = parser.parse_args()
    out = Path(arguments.out)
    out.mkdir(parents=True, exist_ok=True)
    admin_url = os.environ["ANALYTICS_DATABASE_URL"]
    schema = "exp_" + uuid4().hex
    scoped = make_conninfo(admin_url, options=f"-c search_path={schema} -c timezone=UTC")
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))

    def connect():
        return psycopg.connect(scoped, autocommit=True)

    store_root = out / "lake"
    store_root.mkdir(parents=True, exist_ok=True)
    namespace = "bench-analytics-" + uuid4().hex[:12]
    try:
        with connect() as tx, tx.transaction():
            migrate_analytics(tx)
        pipeline = AnalyticsPipeline(
            connect,
            FileStore(store_root),
            EventCodec(fixture.offline_cache(), source_service="catalog"),
            code_commit=os.environ.get("CODE_COMMIT", "uncommitted"),
        )
        started = perf_counter()
        built = fixture.build(
            pipeline,
            namespace,
            publications=arguments.publications,
            events_per_publication=arguments.events,
        )
        build_seconds = perf_counter() - started
        print(f"fixture: {built} in {build_seconds:.1f}s", flush=True)
        silver = pipeline.active_manifest(namespace, "silver")
        gold = pipeline.active_manifest(namespace, "gold")
        base_files = list(silver.files) + list(gold.files)
        print(f"base: {len(silver.files)} silver files, {len(gold.files)} gold", flush=True)
        day = (datetime.now(UTC) - timedelta(days=2)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        config = LayoutConfig()
        started = perf_counter()
        silver_candidate = compact_snapshot(
            pipeline.store,
            silver,
            config,
            output_prefix=f"candidate/{namespace}/{uuid4()}/silver",
        )
        compact_seconds = perf_counter() - started
        published = pipeline.publish_candidate(silver_candidate)
        print(f"published compacted silver generation {published.generation}", flush=True)
        gold_now = pipeline.active_manifest(namespace, "gold")
        gold_candidate = compact_snapshot(
            pipeline.store,
            gold_now,
            config,
            output_prefix=f"candidate/{namespace}/{uuid4()}/gold",
        )
        published_gold = pipeline.publish_candidate(gold_candidate)
        compact_files = list(published.files) + list(published_gold.files)
        unpartitioned = rewrite_unpartitioned(
            pipeline.store, silver, config, f"layout/{namespace}/{uuid4()}"
        )
        flat_gold = rewrite_unpartitioned(
            pipeline.store, gold, config, f"layout/{namespace}/{uuid4()}"
        )
        flat_files = [f for group in {**unpartitioned, **flat_gold}.values() for f in group]
        layouts = {
            "small_files": Layout(base_files),
            "compacted": Layout(compact_files),
            "unpartitioned": Layout(flat_files),
        }
        rows, digests = measure(layouts, store_root, day, out)
        mismatches = [q for q, values in digests.items() if len(set(values.values())) != 1]
        summary = {
            "workload": "W-ANALYTICS",
            "profile": "owner-local warm cache; not the frozen profile or the P9 runner",
            "synthetic_fixture": built,
            "fixture_build_seconds": build_seconds,
            "compaction_seconds_silver": compact_seconds,
            "host": {
                "git": git_state(),
                "cpu_count": os.cpu_count(),
                "platform": platform.platform(),
            },
            "layouts": {name: layout_facts(layout.files) for name, layout in layouts.items()},
            "candidate": {
                "row_count": silver_candidate.row_count,
                "digest": silver_candidate.logical_row_digest,
                "published_generation": published.generation,
            },
            "result_digest_mismatches": mismatches,
            "series": summarize(rows, layouts),
        }
        if arguments.cold:
            cold_rows, cold_digests = measure_cold(layouts, store_root, day, out)
            summary["cold_series"] = summarize_cold(cold_rows, layouts)
            summary["cold_digest_mismatches_against_warm"] = [
                query_id
                for query_id, values in cold_digests.items()
                if any(values[name] != digests[query_id][name] for name in values)
            ]
        (out / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
        print(
            json.dumps({k: summary[k] for k in ("layouts", "result_digest_mismatches")}, indent=1)
        )
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


if __name__ == "__main__":
    main()
