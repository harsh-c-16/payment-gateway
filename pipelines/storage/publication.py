"""Bounded incremental exports, frozen SQL membership and paired generation CAS."""

import hashlib
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from time import monotonic
from uuid import uuid4

from psycopg import sql
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import TypeAdapter

from pipelines.curation.db import lock_key, one, rows, sink_lock
from pipelines.curation.event_time import POLICY, advance_watermark
from pipelines.curation.observations import enqueue_observation
from pipelines.gold.business import business_query, business_row
from shared.contracts.analytics import DatasetManifest, SourceRange
from shared.contracts.events import Namespace
from shared.event_transport.schemas import canonical_json

from .parquet import verified_parquet, write_parquet
from .readers import _wire

FILE_MAX_ROWS = 512
FILE_MAX_BYTES = 4 * 1024 * 1024
ROW_MAX_BYTES = 8 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[2]


class PublicationConflict(RuntimeError):
    pass


class SnapshotCapacityError(RuntimeError):
    pass


@dataclass
class Frozen:
    pending_count: int
    dirty_gold: set


def boundary(point):
    """Disabled fault seam; callers cannot supply commands or HTTP fault controls."""


@contextmanager
def publisher_session(pipeline, namespace):
    TypeAdapter(Namespace).validate_python(namespace)
    pipeline.recover_observations(namespace)
    with pipeline.connect() as tx:
        if not tx.autocommit:
            raise ValueError(
                "Publisher connection must be autocommit outside explicit transactions"
            )
        key = lock_key(namespace, "publisher")
        if not one(tx, "SELECT pg_try_advisory_lock(%s) AS locked", (key,))["locked"]:
            raise PublicationConflict("A publisher already owns this namespace")
        try:
            yield tx
        finally:
            tx.execute("SELECT pg_advisory_unlock(%s)", (key,))


def _active(tx, namespace):
    found = rows(
        tx,
        """SELECT m.manifest,a.generation,a.dataset FROM active_datasets a
        JOIN snapshot_manifests m USING(namespace,dataset,generation) WHERE namespace=%s""",
        (namespace,),
    )
    result = {r["dataset"]: DatasetManifest.model_validate(r["manifest"]) for r in found}
    if any(
        r["manifest"]["namespace"] != namespace
        or r["manifest"]["generation"] != r["generation"]
        or r["manifest"]["dataset"] != r["dataset"]
        for r in found
    ):
        raise PublicationConflict("Active manifest identity mismatch")
    if result and (
        set(result) != {"silver", "gold"}
        or result["silver"].generation != result["gold"].generation
    ):
        raise PublicationConflict("Active Silver/Gold pointers are inconsistent")
    return result


def stream_rows(tx, statement, parameters=(), *, batch=1):
    with tx.cursor(name="m08_" + uuid4().hex, row_factory=dict_row) as cursor:
        cursor.itersize = batch
        cursor.execute(statement, parameters)
        yield from cursor


def _freeze(tx, namespace):
    old = _active(tx, namespace)
    tx.execute("CREATE TEMP TABLE m08_pending(event_id uuid PRIMARY KEY) ON COMMIT PRESERVE ROWS")
    tx.execute(
        "INSERT INTO m08_pending SELECT event_id FROM export_pending WHERE namespace=%s",
        (namespace,),
    )
    count = one(tx, "SELECT count(*) AS n FROM m08_pending")["n"]
    if not count:
        return old, Frozen(0, set())
    tx.execute("CREATE TEMP TABLE m08_members(event_id uuid PRIMARY KEY) ON COMMIT PRESERVE ROWS")
    tx.execute(
        """INSERT INTO m08_members SELECT p.event_id FROM m08_pending p
        WHERE NOT EXISTS(SELECT 1 FROM event_visibility v
        WHERE v.namespace=%s AND v.event_id=p.event_id)""",
        (namespace,),
    )
    dirty = rows(
        tx,
        """SELECT DISTINCT 'pipeline_minute' AS table_name,
        (e.event_time AT TIME ZONE 'UTC')::date AS cohort_date
        FROM silver_events e JOIN m08_pending p USING(event_id) WHERE e.namespace=%s
        UNION SELECT g.table_name,g.cohort_date FROM gold_dirty_keys g
        JOIN m08_pending p USING(event_id) WHERE g.namespace=%s""",
        (namespace, namespace),
    )
    return old, Frozen(count, {(r["table_name"], r["cohort_date"].isoformat()) for r in dirty})


def _silver_row(fact):
    doc = fact["document"]
    row = {
        key: doc.get(key)
        for key in (
            "namespace",
            "event_id",
            "event_type",
            "source_service",
            "aggregate_type",
            "aggregate_id",
            "aggregate_version",
            "run_id",
            "correlation_id",
            "session_id",
            "user_id",
        )
    }
    row.update(
        namespace=fact["namespace"],
        content_hash=fact["content_hash"],
        event_time=fact["event_time"],
        produced_at=datetime.fromisoformat(doc["produced_at"].replace("Z", "+00:00")),
        dataset_revision=doc.get("metadata", {}).get("dataset_revision"),
        schema_version=doc["schema_version"],
        synthetic=doc.get("metadata", {}).get("synthetic"),
        scenario_source=doc.get("metadata", {}).get("scenario_source"),
        metadata_json=canonical_json(doc["metadata"]).decode(),
        envelope_json=canonical_json(doc).decode(),
        raw_locator=fact["raw_locator"],
    )
    payload = dict(fact["normalized_payload"])
    for name in ("created_at", "changed_at", "attempt_created_at"):
        if payload.get(name) is not None:
            payload[name] = datetime.fromisoformat(payload[name].replace("Z", "+00:00"))
    row["payload"] = payload
    return row


def provenance(pipeline, namespace):
    return {
        "format_version": 2,
        "namespace": namespace,
        "code_commit": pipeline.code_commit,
        "transform_version": pipeline.transform_version,
        "uv_lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "event_dictionary_sha256": hashlib.sha256(
            (ROOT / "contracts/dictionaries/events/reasons.v1.json").read_bytes()
        ).hexdigest(),
        "schema_hashes": {s: e["sha256"] for s, e in pipeline.codec.cache.entries.items()},
        "source_provenance": "Original Silver metadata and Bronze receipts; no inferred origin",
    }


def write_lineage(pipeline, namespace, snapshot_id, document):
    path = f"lineage/{namespace}/{snapshot_id}.json"
    data = canonical_json(document)
    pipeline.store.write_immutable(path, data, hashlib.sha256(data).hexdigest())
    return path


def _lineage(pipeline, tx, namespace, old, snapshot_id):
    parts, batch = [], []

    def flush():
        path = f"lineage/{namespace}/{snapshot_id}-{len(parts)}.json"
        data = canonical_json({"event_ids": [r["event_id"] for r in batch], "sources": batch})
        file = pipeline.store.write_immutable(path, data, hashlib.sha256(data).hexdigest())
        parts.append({"path": path, "sha256": file.sha256, "event_count": len(batch)})
        batch.clear()

    for row in stream_rows(
        tx,
        """SELECT e.event_id::text,s.topic,s.partition,s.offset_number,
        s.raw_locator,s.raw_sha256,s.capture_id::text,
        t.watermark_before,t.timestamp_quality,t.revision,t.reason,
        b.namespace AS origin_namespace FROM silver_events e
        JOIN m08_pending p USING(event_id) JOIN source_receipts s ON s.namespace=e.namespace
        AND s.topic=e.source_topic AND s.partition=e.source_partition
        AND s.offset_number=e.source_offset
        JOIN bronze_captures b ON b.capture_id=s.capture_id
        LEFT JOIN event_time_observations t ON t.namespace=e.namespace AND t.event_id=e.event_id
        WHERE e.namespace=%s ORDER BY e.event_id""",
        (namespace,),
        batch=512,
    ):
        row["watermark_before"] = _wire(row["watermark_before"])
        batch.append(row)
        if len(batch) == 512:
            flush()
    if batch:
        flush()
    replay = one(
        tx,
        """SELECT replay_id::text,request,clock_at,provider_sha256,
        'fixed original ingress ceiling; validation uses original ingress' AS clock_policy
        FROM replay_jobs WHERE target_namespace=%s""",
        (namespace,),
    )
    document = {
        **provenance(pipeline, namespace),
        "event_time_policy": {**POLICY, "clock": replay["clock_policy"]} if replay else POLICY,
        "replay": _wire(replay),
        "event_time_status": _wire(
            one(tx, "SELECT * FROM event_time_watermarks WHERE namespace=%s", (namespace,))
        ),
        "membership_files": parts,
        "parent_input_manifest_ids": sorted(
            {ref for manifest in old.values() for ref in manifest.input_manifest_ids}
        ),
    }
    path = write_lineage(pipeline, namespace, snapshot_id, document)
    ranges = rows(
        tx,
        """SELECT s.topic,s.partition,min(s.offset_number) AS first_offset,
        max(s.offset_number)+1 AS next_offset FROM silver_events e
        JOIN m08_pending m USING(event_id) JOIN source_receipts s ON s.namespace=e.namespace
        AND s.topic=e.source_topic AND s.partition=e.source_partition
        AND s.offset_number=e.source_offset WHERE e.namespace=%s GROUP BY s.topic,s.partition
        ORDER BY s.topic,s.partition""",
        (namespace,),
    )
    merged = (
        {
            (r.topic, r.partition): r.model_copy(update={"receipt_membership_ref": path})
            for r in old["silver"].source_ranges
        }
        if old
        else {}
    )
    for row in ranges:
        key = row["topic"], row["partition"]
        previous = merged.get(key)
        if previous:
            row["first_offset"] = min(previous.first_offset, row["first_offset"])
            row["next_offset"] = max(previous.next_offset, row["next_offset"])
        merged[key] = SourceRange(**row, receipt_membership_ref=path)
    return path, [merged[key] for key in sorted(merged)]


def iter_membership(tx, namespace, dataset, generation):
    """Resolve complete membership across M08 deltas and retained older full sets."""
    with tx.transaction():
        for row in stream_rows(
            tx,
            """WITH RECURSIVE ancestry AS (
            SELECT generation,(manifest->>'parent_generation')::bigint AS parent
            FROM snapshot_manifests WHERE namespace=%s AND dataset=%s AND generation=%s
            UNION ALL SELECT s.generation,(s.manifest->>'parent_generation')::bigint
            FROM snapshot_manifests s JOIN ancestry a ON s.generation=a.parent
            WHERE s.namespace=%s AND s.dataset=%s)
            SELECT DISTINCT m.event_id::text FROM manifest_members m
            JOIN ancestry a USING(generation) WHERE m.namespace=%s AND m.dataset=%s
            ORDER BY event_id""",
            (namespace, dataset, generation, namespace, dataset, namespace, dataset),
            batch=512,
        ):
            yield row["event_id"]


def _export(
    pipeline,
    tx,
    statement,
    parameters,
    schema,
    partitions,
    time_column,
    convert,
    files,
    namespace,
    snapshot_id,
    generation,
):
    too_large = one(
        tx,
        sql.SQL("""SELECT EXISTS(SELECT 1 FROM ({}) x
        WHERE octet_length(to_jsonb(x)::text)>%s) AS bad""").format(
            sql.SQL(statement) if isinstance(statement, str) else statement
        ),
        (*parameters, ROW_MAX_BYTES),
    )["bad"]
    if too_large:
        raise SnapshotCapacityError("A single projected row exceeds the 8 MiB bound")
    batch, size = [], 0

    def flush():
        dataset = "silver" if schema == "silver-events-v1" else "gold"
        path = f"{dataset}/{namespace}/{snapshot_id}-{len(files)}.parquet"
        files.append(
            write_parquet(
                pipeline.store, path, batch, schema, partitions, [r[time_column] for r in batch]
            )
        )
        batch.clear()

    for raw in stream_rows(tx, statement, parameters):
        row = convert(raw)
        if schema != "silver-events-v1":
            row["publication_generation"] = generation
        row_size = len(canonical_json(_wire(row)))
        if row_size > ROW_MAX_BYTES:
            raise SnapshotCapacityError("A single exported row exceeds the 8 MiB bound")
        if batch and (len(batch) >= FILE_MAX_ROWS or size + row_size > FILE_MAX_BYTES):
            flush()
            size = 0
        batch.append(row)
        size += row_size
    if batch:
        flush()


def _files(pipeline, tx, namespace, old, frozen, generation, snapshot_id):
    files = {"silver": [], "gold": []}
    for dataset, manifest in old.items():
        for file in manifest.files:
            cohort = file.partition_values.get(
                "event_date", file.partition_values.get("cohort_date")
            )
            if dataset == "gold" and (file.schema_name, cohort) in frozen.dirty_gold:
                continue
            with verified_parquet(pipeline.store, file):
                pass
            files[dataset].append(file)
    new = """SELECT e.* FROM silver_events e JOIN m08_pending p USING(event_id)
        WHERE e.namespace=%s AND NOT EXISTS(SELECT 1 FROM event_visibility v
        WHERE v.namespace=e.namespace AND v.event_id=e.event_id)"""
    partitions = rows(
        tx,
        sql.SQL("""SELECT DISTINCT (event_time AT TIME ZONE 'UTC')::date AS day,
        event_type FROM ({}) x ORDER BY day,event_type""").format(sql.SQL(new)),
        (namespace,),
    )
    for part in partitions:
        statement = (
            new + " AND (e.event_time AT TIME ZONE 'UTC')::date=%s"
            " AND e.event_type=%s ORDER BY e.event_id"
        )
        _export(
            pipeline,
            tx,
            statement,
            (namespace, part["day"], part["event_type"]),
            "silver-events-v1",
            {"event_date": part["day"].isoformat(), "event_type": part["event_type"]},
            "event_time",
            _silver_row,
            files["silver"],
            namespace,
            snapshot_id,
            generation,
        )
    for table, day in sorted(frozen.dirty_gold):
        if table == "pipeline_minute":
            start = datetime.combine(date.fromisoformat(day), datetime.min.time(), tzinfo=UTC)
            statement = """SELECT * FROM pipeline_minute WHERE namespace=%s AND minute>=%s
                AND minute<%s ORDER BY minute,event_type,source_service"""
            parameters = (namespace, start, start + timedelta(days=1))
            partitions = {"event_date": day, "table": table}
            convert, time_column = lambda row: row, "minute"
        else:
            statement, parameters = business_query(table), (table, namespace, day)
            partitions = {"cohort_date": day, "table": table}
            convert, time_column = lambda row, t=table: business_row(row, t), "cohort_date"
        _export(
            pipeline,
            tx,
            statement,
            parameters,
            table,
            partitions,
            time_column,
            convert,
            files["gold"],
            namespace,
            snapshot_id,
            generation,
        )
    return files


def activate(tx, namespace, old, manifests):
    sink_lock(tx, namespace)
    current = _active(tx, namespace)
    if {k: m.generation for k, m in current.items()} != {k: m.generation for k, m in old.items()}:
        raise PublicationConflict("STALE_MANIFEST: active generation changed")
    for dataset, manifest in manifests.items():
        tx.execute(
            "INSERT INTO snapshot_manifests VALUES (%s,%s,%s,%s)",
            (namespace, dataset, manifest.generation, Jsonb(manifest.model_dump(mode="json"))),
        )
        moved = tx.execute(
            """INSERT INTO active_datasets VALUES (%s,%s,%s)
            ON CONFLICT(namespace,dataset) DO UPDATE SET generation=EXCLUDED.generation
            WHERE active_datasets.generation=%s RETURNING generation""",
            (namespace, dataset, manifest.generation, old[dataset].generation if old else 0),
        ).fetchone()
        if moved is None:
            raise PublicationConflict("STALE_MANIFEST: pointer compare-and-swap failed")


def _commit(pipeline, tx, namespace, old, manifests):
    jobs = []
    with tx.transaction():
        activate(tx, namespace, old, manifests)
        for dataset, manifest in manifests.items():
            tx.execute(
                """INSERT INTO manifest_members SELECT %s,%s,%s,event_id FROM m08_members""",
                (namespace, dataset, manifest.generation),
            )
        tx.execute(
            """CREATE TEMP TABLE m08_new_visible ON COMMIT DROP AS SELECT m.event_id
            FROM m08_members m WHERE NOT EXISTS(SELECT 1 FROM event_visibility v
            WHERE v.namespace=%s AND v.event_id=m.event_id)""",
            (namespace,),
        )
        tx.execute(
            """INSERT INTO event_visibility(namespace,event_id,generation)
            SELECT %s,event_id,%s FROM m08_new_visible""",
            (namespace, manifests["gold"].generation),
        )
        batch = []
        for row in stream_rows(
            tx, "SELECT event_id::text FROM m08_new_visible ORDER BY event_id", batch=512
        ):
            batch.append(row["event_id"])
            if len(batch) == 512:
                jobs.append(enqueue_observation(tx, namespace, "gold", batch))
                batch = []
        if batch:
            jobs.append(enqueue_observation(tx, namespace, "gold", batch))
        tx.execute(
            """DELETE FROM export_pending e WHERE namespace=%s
            AND EXISTS(SELECT 1 FROM m08_pending p WHERE p.event_id=e.event_id)""",
            (namespace,),
        )
        boundary("before_manifest_swap")
    return jobs


def publish_snapshot(pipeline, namespace):
    started = monotonic()
    with publisher_session(pipeline, namespace) as tx:
        with tx.transaction():
            advance_watermark(tx, namespace)
        with tx.transaction():
            tx.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            tx.execute("SET LOCAL work_mem='4MB'")
            old, frozen = _freeze(tx, namespace)
            if not frozen.pending_count:
                if not old:
                    raise LookupError("No accepted facts have been published")
                return old["gold"]
            generation = old["gold"].generation + 1 if old else 1
            snapshot_id = str(uuid4())
            lineage, ranges = _lineage(pipeline, tx, namespace, old, snapshot_id)
            files = _files(pipeline, tx, namespace, old, frozen, generation, snapshot_id)
            boundary("after_files_durable")
            manifests = {
                dataset: DatasetManifest(
                    namespace=namespace,
                    dataset=dataset,
                    generation=generation,
                    parent_generation=generation - 1 if old else None,
                    files=data,
                    source_ranges=ranges,
                    transform_version=pipeline.transform_version,
                    code_commit=pipeline.code_commit,
                    input_manifest_ids=[lineage],
                    created_at=datetime.now(UTC),
                )
                for dataset, data in files.items()
            }
        jobs = _commit(pipeline, tx, namespace, old, manifests)
        boundary("after_manifest_swap")
        for job in jobs:
            pipeline._observe(namespace, job)
        pending = one(
            tx, "SELECT count(*) AS n FROM export_pending WHERE namespace=%s", (namespace,)
        )["n"]
        pipeline.telemetry.record("gold_pending_events", pending)
        pipeline.telemetry.record("gold_generation", generation)
        pipeline.telemetry.record("gold_publication_duration_seconds", monotonic() - started)
        return manifests["gold"]
