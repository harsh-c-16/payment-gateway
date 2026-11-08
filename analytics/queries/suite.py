"""Frozen Q1-Q6 over explicit manifest file lists; a glob could include retired files."""

import asyncio
import hashlib
import json
import os
from datetime import timedelta
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import duckdb

from analytics.compaction.compact import LayoutConfig, compact_snapshot, rewrite_unpartitioned
from pipelines.catalog.artifacts import peak_rss_kib

SILVER = ("silver-events-v1", "silver-conversation-turn")
QUERIES = {
    "Q1": {
        "schemas": SILVER,
        "sql": """SELECT CAST(event_time AS DATE) AS day, event_type,
                         count(DISTINCT event_id) AS events
                  FROM source GROUP BY 1, 2 ORDER BY 1, 2""",
    },
    "Q2": {
        "schemas": ("daily_conversion",),
        "sql": """SELECT CAST(cohort_date AS DATE) AS day, currency, confirmed_orders,
                         CAST(confirmed_amount_minor AS VARCHAR) AS confirmed_amount_minor
                  FROM source ORDER BY 1, 2""",
    },
    "Q3": {
        "schemas": ("payment_failures",),
        "sql": """SELECT CAST(cohort_date AS DATE) AS day, failure_code,
                         CAST(sum(failed_attempts) AS BIGINT) AS failed
                  FROM source WHERE failed_attempts > 0 GROUP BY 1, 2 ORDER BY 1, 2""",
    },
    "Q4": {
        "schemas": ("search_performance",),
        "sql": """SELECT CAST(cohort_date AS DATE) AS day, mode,
                         CAST(sum(unique_searches) AS BIGINT) AS searches,
                         CAST(sum(empty_results) AS BIGINT) AS empty,
                         CAST(sum(empty_results) AS DOUBLE) / sum(unique_searches) AS empty_rate
                  FROM source GROUP BY 1, 2 ORDER BY 1, 2""",
    },
    "Q5": {
        "schemas": SILVER,
        "sql": """SELECT event_id, event_type, CAST(event_time AS VARCHAR) AS event_time,
                         aggregate_id
                  FROM source
                  WHERE event_time >= $start AND event_time < $end ORDER BY event_id""",
        "day_filter": True,
    },
    "Q6": {
        "schemas": SILVER,
        "sql": """SELECT event_id, event_type, CAST(event_time AS VARCHAR) AS event_time,
                         aggregate_id, source_service
                  FROM source ORDER BY event_id""",
    },
}


def selected_files(manifest, schemas, day):
    """Partition pruning happens here: only files that can hold the requested day are opened."""
    chosen = []
    for descriptor in manifest.files:
        if descriptor.schema_name not in schemas or not descriptor.row_count:
            continue
        date = descriptor.partition_values.get("event_date")
        if day is not None and date is not None and date != day.date().isoformat():
            continue
        chosen.append(descriptor)
    return chosen


def read_bytes_counter():
    """Bytes through read syscalls (Linux), or None. Includes cache hits; not physical I/O."""
    try:
        for line in Path("/proc/self/io").read_text().splitlines():
            if line.startswith("rchar:"):
                return int(line.split()[1])
    except OSError:
        pass
    return None


def run_query(connection, query_id, manifest, store_root, day):
    """Returns (rows, measurements). No file list means the table has no rows at this generation."""
    spec = QUERIES[query_id]
    target_day = day if spec.get("day_filter") else None
    files = selected_files(manifest, spec["schemas"], target_day)
    if not files:
        return [], measurement([], 0.0, None, None, 0)
    paths = [str(Path(store_root) / descriptor.path) for descriptor in files]
    statement = spec["sql"].replace(
        "FROM source", f"FROM read_parquet({json.dumps(paths)}, union_by_name=true)"
    )
    parameters = {"start": target_day, "end": target_day + timedelta(days=1)} if target_day else {}
    cpu_before, reads_before = os.times(), read_bytes_counter()
    started = perf_counter()
    rows = connection.execute(statement, parameters).fetchall()
    elapsed = (perf_counter() - started) * 1000
    cpu_after, reads_after = os.times(), read_bytes_counter()
    cpu = cpu_after.user + cpu_after.system - cpu_before.user - cpu_before.system
    reads = None if reads_before is None else reads_after - reads_before
    return rows, measurement(files, elapsed, cpu, reads, len(rows))


def measurement(files, elapsed, cpu, reads, returned):
    return {
        "wall_ms": elapsed,
        "cpu_seconds": cpu,
        "files_opened": len(files),
        "selected_file_bytes": sum(descriptor.byte_size for descriptor in files),
        "syscall_read_bytes": reads,
        "returned_rows": returned,
        "peak_rss_kib": peak_rss_kib(),
    }


def result_digest(rows):
    """Layout-independent equality: identical values in the query's own frozen order."""
    return hashlib.sha256(json.dumps(rows, default=str).encode()).hexdigest()


def open_connection():
    connection = duckdb.connect(":memory:")
    # File metadata is re-read per query: caching would hide the small-file open cost under test.
    connection.execute("SET enable_object_cache=false")
    connection.execute("SET TimeZone='UTC'")
    return connection


def runner_query_adapter(layout_for, store_root, day):
    """Adapter for Jaineel's QueryDriver. layout_for(context) picks the variant's manifest."""
    connection = open_connection()

    async def query_adapter(body, context):
        rows, facts = await asyncio.to_thread(
            run_query, connection, body["query_id"], layout_for(context), store_root, day
        )
        return {**facts, "result_digest": result_digest(rows)}

    return query_adapter


class Layout:
    """Minimal manifest view so unpartitioned rewrites share the query path."""

    def __init__(self, files):
        self.files = files


# (file_layout, partitioning) from the variant's effective config -> layout name.
LAYOUT_FOR_PARAMETERS = {
    ("small", "date_type"): "small_files",
    ("compact", "date_type"): "compacted",
    ("compact", "unpartitioned"): "unpartitioned",
}


def build_layouts(pipeline, namespace):
    """Compact the namespace's active Silver and Gold through the publisher, before any query.

    The small-file layout is the snapshot as it was; compaction never deletes its files.
    """
    config = LayoutConfig()
    silver = pipeline.active_manifest(namespace, "silver")
    gold = pipeline.active_manifest(namespace, "gold")
    run = uuid4()
    started = perf_counter()
    silver_candidate = compact_snapshot(
        pipeline.store, silver, config, output_prefix=f"candidate/{namespace}/{run}/silver"
    )
    compaction_seconds = perf_counter() - started
    published = pipeline.publish_candidate(silver_candidate)
    gold_candidate = compact_snapshot(
        pipeline.store,
        pipeline.active_manifest(namespace, "gold"),
        config,
        output_prefix=f"candidate/{namespace}/{run}/gold",
    )
    published_gold = pipeline.publish_candidate(gold_candidate)
    flat = {
        **rewrite_unpartitioned(pipeline.store, silver, config, f"layout/{namespace}/{run}/s"),
        **rewrite_unpartitioned(pipeline.store, gold, config, f"layout/{namespace}/{run}/g"),
    }
    layouts = {
        "small_files": Layout(list(silver.files) + list(gold.files)),
        "compacted": Layout(list(published.files) + list(published_gold.files)),
        "unpartitioned": Layout([f for group in flat.values() for f in group]),
    }
    facts = {
        "compaction_seconds_silver": compaction_seconds,
        "candidate": {
            "row_count": silver_candidate.row_count,
            "digest": silver_candidate.logical_row_digest,
            "published_generation": published.generation,
        },
    }
    return layouts, facts


def runner_layout_for(layouts):
    """layout_for for runner_query_adapter. An unlisted variant fails instead of guessing."""

    def layout_for(context):
        parameters = context["parameters"]
        return layouts[LAYOUT_FOR_PARAMETERS[parameters["file_layout"], parameters["partitioning"]]]

    return layout_for
