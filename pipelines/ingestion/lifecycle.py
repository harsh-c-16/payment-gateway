"""Owner-local storage setup/reset. No Kafka or operational database deletion."""

import re
from datetime import UTC, datetime, timedelta

from psycopg import sql
from pydantic import TypeAdapter

from pipelines.curation.db import lock_key, one, sink_lock
from shared.contracts.events import Namespace

# Child tables precede parents. Replay metadata is never removed by this provider.
TABLES = (
    "gold_dirty_keys",
    "manifest_members",
    "active_datasets",
    "event_visibility",
    "event_time_observations",
    "gold_business_contributions",
    "reducer_contributions",
    "order_fact",
    "order_cohorts",
    "payment_fact",
    "funnel_stages",
    "pending_order_joins",
    "inventory_failure_outcomes",
    "search_fact",
    "export_pending",
    "silver_events",
    "pipeline_minute",
    "gold_partition_revisions",
    "observation_jobs",
    "receipt_journal",
    "quarantine",
    "sink_batches",
    "source_receipts",
    "snapshot_manifests",
    "event_time_partitions",
    "event_time_watermarks",
    "processing_runs",
    "outbox",
    "bronze_captures",
)


def isolated_namespace(namespace):
    TypeAdapter(Namespace).validate_python(namespace)
    if not namespace.startswith("bench-") or re.match(
        r"bench-(dev|live|prod|production)(-|$)", namespace
    ):
        raise ValueError("Only isolated bench namespaces may be prepared/reset")
    return namespace


def assert_empty(tx, namespace):
    for table in TABLES:
        if tx.execute(
            sql.SQL("SELECT 1 FROM {} WHERE namespace=%s LIMIT 1").format(sql.Identifier(table)),
            (namespace,),
        ).fetchone():
            raise ValueError("Analytics namespace already contains data")
    if tx.execute("SELECT 1 FROM replay_jobs WHERE target_namespace=%s", (namespace,)).fetchone():
        raise ValueError("Analytics namespace belongs to a replay")


def reset_namespace(pipeline, namespace, *, quiescent, evaluation_accepted):
    """Explicit cleanup after retention/acceptance; immutable files remain retained."""
    isolated_namespace(namespace)
    if quiescent is not True or evaluation_accepted is not True:
        raise ValueError("Reset requires stopped writers/readers and final evaluation acceptance")
    with pipeline.connect() as tx, tx.transaction():
        # Serialize against replay pin creation before checking its references.
        tx.execute("SET LOCAL lock_timeout='5s'")
        tx.execute("LOCK TABLE replay_jobs,replay_inputs,replay_references IN SHARE MODE")
        sink_lock(tx, namespace)
        if not one(
            tx,
            "SELECT pg_try_advisory_xact_lock(%s) AS locked",
            (lock_key(namespace, "publisher"),),
        )["locked"]:
            raise ValueError("A publisher still owns this namespace")
        if tx.execute(
            """SELECT 1 FROM replay_inputs WHERE namespace=%s
            UNION ALL SELECT 1 FROM replay_references WHERE namespace=%s
            UNION ALL SELECT 1 FROM replay_jobs WHERE target_namespace=%s
            UNION ALL SELECT 1 FROM replay_keys WHERE request_namespace=%s LIMIT 1""",
            (namespace,) * 4,
        ).fetchone():
            raise ValueError("Replay references prevent namespace reset")
        cutoff = datetime.now(UTC) - timedelta(days=30)
        if tx.execute(
            "SELECT 1 FROM bronze_captures WHERE namespace=%s AND captured_at>%s LIMIT 1",
            (namespace, cutoff),
        ).fetchone():
            raise ValueError("Thirty-day source/dedup/manifest retention has not elapsed")
        if tx.execute(
            """SELECT 1 FROM snapshot_manifests WHERE namespace=%s AND
            (manifest->>'created_at')::timestamptz>%s LIMIT 1""",
            (namespace, cutoff),
        ).fetchone():
            raise ValueError("Thirty-day manifest retention has not elapsed")
        if tx.execute(
            """SELECT 1 FROM outbox WHERE namespace=%s AND
            (published_at IS NULL OR published_at > clock_timestamp()-interval '7 days') LIMIT 1""",
            (namespace,),
        ).fetchone():
            raise ValueError("Unpublished or retained outbox rows prevent reset")
        deleted = {}
        for table in TABLES:
            deleted[table] = tx.execute(
                sql.SQL("DELETE FROM {} WHERE namespace=%s").format(sql.Identifier(table)),
                (namespace,),
            ).rowcount
    return {"namespace": namespace, "deleted_rows": deleted, "immutable_files_retained": True}
