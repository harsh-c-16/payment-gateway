"""Consistent frozen membership, durable files, paired pointer CAS, post-commit observation."""

import hashlib
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic
from uuid import uuid4

from psycopg.types.json import Jsonb
from pydantic import TypeAdapter

from pipelines.curation.db import lock_key, one, rows, sink_lock
from pipelines.curation.observations import enqueue_observation
from shared.contracts.analytics import DatasetManifest, SourceRange
from shared.contracts.events import Namespace
from shared.event_transport.schemas import canonical_json

from .parquet import read_verified, write_parquet

# shortcut: bounded full M05 snapshot; implement incremental loading before W-QUALITY/scale runs.
MAX_SNAPSHOT_ROWS = 10000
MAX_SNAPSHOT_BYTES = 8 * 1024 * 1024
ROOT = Path(__file__).resolve().parents[2]


class PublicationConflict(RuntimeError):
    pass


class SnapshotCapacityError(RuntimeError):
    pass


def _active(tx, namespace):
    found = rows(
        tx,
        """SELECT m.manifest,a.generation,a.dataset FROM active_datasets a JOIN snapshot_manifests m
        USING(namespace,dataset,generation) WHERE namespace=%s""",
        (namespace,),
    )
    result = {
        row["manifest"]["dataset"]: DatasetManifest.model_validate(row["manifest"]) for row in found
    }
    if any(
        row["manifest"]["namespace"] != namespace
        or row["manifest"]["generation"] != row["generation"]
        or row["manifest"]["dataset"] != row["dataset"]
        for row in found
    ):
        raise PublicationConflict("Active manifest identity mismatch")
    if result and (
        set(result) != {"silver", "gold"}
        or result["silver"].generation != result["gold"].generation
    ):
        raise PublicationConflict("Active Silver/Gold pointers are inconsistent")
    return result


def _freeze(tx, namespace):
    with tx.transaction():
        tx.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
        old = _active(tx, namespace)
        pending = [
            str(row["event_id"])
            for row in rows(
                tx,
                "SELECT event_id FROM export_pending WHERE namespace=%s ORDER BY event_id LIMIT %s",
                (namespace, MAX_SNAPSHOT_ROWS + 1),
            )
        ]
        if len(pending) > MAX_SNAPSHOT_ROWS:
            raise SnapshotCapacityError("M05 frozen membership bound reached")
        if not pending:
            return old, [], [], [], []
        bounds = one(
            tx,
            """SELECT count(*) AS n,COALESCE(sum(octet_length(document::text)),0) AS bytes
                            FROM silver_events WHERE namespace=%s""",
            (namespace,),
        )
        if bounds["n"] > MAX_SNAPSHOT_ROWS or bounds["bytes"] > MAX_SNAPSHOT_BYTES:
            raise SnapshotCapacityError(
                "M05 full-snapshot memory bound reached; incremental M08 pending"
            )
        facts = rows(
            tx, "SELECT * FROM silver_events WHERE namespace=%s ORDER BY event_id", (namespace,)
        )
        gold = rows(
            tx,
            """SELECT * FROM pipeline_minute WHERE namespace=%s
                           ORDER BY minute,event_type,source_service""",
            (namespace,),
        )
        sources = rows(
            tx,
            """SELECT s.topic,s.partition,s.offset_number,s.raw_locator,s.raw_sha256,
                       s.capture_id FROM source_receipts s JOIN silver_events e
                       ON e.namespace=s.namespace AND e.source_topic=s.topic
                       AND e.source_partition=s.partition AND e.source_offset=s.offset_number
                       WHERE s.namespace=%s ORDER BY s.topic,s.partition,s.offset_number""",
            (namespace,),
        )
    return old, pending, facts, gold, sources


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
        content_hash=fact["content_hash"],
        event_time=fact["event_time"],
        produced_at=datetime.fromisoformat(doc["produced_at"].replace("Z", "+00:00")),
        dataset_revision=doc.get("metadata", {}).get("dataset_revision"),
        envelope_json=canonical_json(doc).decode(),
        raw_locator=fact["raw_locator"],
    )
    row.update(
        {
            key: doc["payload"][key]
            for key in (
                "turn_id",
                "mode",
                "outcome",
                "duration_ms",
                "llm_call_count",
                "extractor_source",
            )
        }
    )
    return row


def _lineage(pipeline, namespace, facts, sources, snapshot_id):
    path = f"lineage/{namespace}/{snapshot_id}.json"
    ranges = defaultdict(list)
    for source in sources:
        ranges[(source["topic"], source["partition"])].append(source["offset_number"])
    document = {
        "namespace": namespace,
        "code_commit": pipeline.code_commit,
        "transform_version": pipeline.transform_version,
        "uv_lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        "event_dictionary_sha256": hashlib.sha256(
            (ROOT / "contracts/dictionaries/events/reasons.v1.json").read_bytes()
        ).hexdigest(),
        "event_ids": [str(fact["event_id"]) for fact in facts],
        "sources": [{**source, "capture_id": str(source["capture_id"])} for source in sources],
        "schema_hashes": {
            subject: entry["sha256"] for subject, entry in pipeline.codec.cache.entries.items()
        },
        "source_provenance": "Original event/capture provenance; no inferred origin",
    }
    data = canonical_json(document)
    pipeline.store.write_immutable(path, data, hashlib.sha256(data).hexdigest())
    return path, [
        SourceRange(
            topic=topic,
            partition=partition,
            first_offset=min(offsets),
            next_offset=max(offsets) + 1,
            receipt_membership_ref=path,
        )
        for (topic, partition), offsets in ranges.items()
    ]


def _files(pipeline, namespace, old, pending, facts, gold, generation, snapshot_id):
    fresh = set(pending)
    dirty_silver = {
        (f["event_time"].date().isoformat(), f["event_type"])
        for f in facts
        if str(f["event_id"]) in fresh
    }
    dirty_dates = {date for date, _ in dirty_silver}
    result = {"silver": [], "gold": []}
    for dataset, manifest in old.items():
        for file in manifest.files:
            date = file.partition_values["event_date"]
            dirty = (
                (date, file.partition_values["event_type"]) in dirty_silver
                if dataset == "silver"
                else date in dirty_dates
            )
            if not dirty:
                read_verified(pipeline.store, file)
                result[dataset].append(file)
    silver_groups, gold_groups = defaultdict(list), defaultdict(list)
    for fact in facts:
        key = (fact["event_time"].date().isoformat(), fact["event_type"])
        if key in dirty_silver:
            silver_groups[key].append(_silver_row(fact))
    for row in gold:
        date = row["minute"].date().isoformat()
        if date in dirty_dates:
            gold_groups[date].append({**row, "publication_generation": generation})
    for (date, event_type), data in silver_groups.items():
        path = f"silver/{namespace}/{snapshot_id}-{len(result['silver'])}.parquet"
        result["silver"].append(
            write_parquet(
                pipeline.store,
                path,
                data,
                "silver-conversation-turn",
                {"event_date": date, "event_type": event_type},
                [r["event_time"] for r in data],
            )
        )
    for date, data in gold_groups.items():
        path = f"gold/{namespace}/{snapshot_id}-{len(result['gold'])}.parquet"
        result["gold"].append(
            write_parquet(
                pipeline.store,
                path,
                data,
                "pipeline_minute",
                {"event_date": date, "table": "pipeline_minute"},
                [r["minute"] for r in data],
            )
        )
    return result


def _commit(pipeline, tx, namespace, old, manifests, pending, facts):
    with tx.transaction():
        sink_lock(tx, namespace)
        current = _active(tx, namespace)
        if {k: m.generation for k, m in current.items()} != {
            k: m.generation for k, m in old.items()
        }:
            raise PublicationConflict("STALE_MANIFEST: active generation changed")
        ids = [str(f["event_id"]) for f in facts]
        new_visible = []
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
            for event_id in ids:
                tx.execute(
                    "INSERT INTO manifest_members VALUES (%s,%s,%s,%s)",
                    (namespace, dataset, manifest.generation, event_id),
                )
        for event_id in ids:
            inserted = tx.execute(
                """INSERT INTO event_visibility(namespace,event_id,generation)
                VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING event_id""",
                (namespace, event_id, manifests["gold"].generation),
            ).fetchone()
            if inserted:
                new_visible.append(event_id)
        tx.execute(
            "DELETE FROM export_pending WHERE namespace=%s AND event_id=ANY(%s::uuid[])",
            (namespace, pending),
        )
        job = enqueue_observation(tx, namespace, "gold", new_visible) if new_visible else None
    return job


def publish_snapshot(pipeline, namespace):
    TypeAdapter(Namespace).validate_python(namespace)
    pipeline.recover_observations(namespace)
    started = monotonic()
    key = lock_key(namespace, "publisher")
    with pipeline.connect() as tx:
        if not tx.autocommit:
            raise ValueError(
                "Publisher connection must be autocommit outside explicit transactions"
            )
        if not one(tx, "SELECT pg_try_advisory_lock(%s) AS locked", (key,))["locked"]:
            raise PublicationConflict("A publisher already owns this namespace")
        try:
            old, pending, facts, gold, sources = _freeze(tx, namespace)
            if not pending:
                if not old:
                    raise LookupError("No accepted facts have been published")
                return old["gold"]
            generation = old["gold"].generation + 1 if old else 1
            snapshot_id = str(uuid4())
            lineage, source_ranges = _lineage(pipeline, namespace, facts, sources, snapshot_id)
            files = _files(pipeline, namespace, old, pending, facts, gold, generation, snapshot_id)
            manifests = {
                dataset: DatasetManifest(
                    namespace=namespace,
                    dataset=dataset,
                    generation=generation,
                    parent_generation=generation - 1 if old else None,
                    files=files[dataset],
                    source_ranges=source_ranges,
                    transform_version=pipeline.transform_version,
                    code_commit=pipeline.code_commit,
                    input_manifest_ids=[lineage],
                    created_at=datetime.now(UTC),
                )
                for dataset in files
            }
            job = _commit(pipeline, tx, namespace, old, manifests, pending, facts)
            if job:
                pipeline._observe(namespace, job)  # Pointer COMMIT has acknowledged first.
            pending_count = one(
                tx, "SELECT count(*) AS n FROM export_pending WHERE namespace=%s", (namespace,)
            )["n"]
            pipeline.telemetry.record("gold_pending_events", pending_count)
            pipeline.telemetry.record("gold_generation", generation)
            pipeline.telemetry.record("gold_publication_duration_seconds", monotonic() - started)
            return manifests["gold"]
        finally:
            tx.execute("SELECT pg_advisory_unlock(%s)", (key,))
