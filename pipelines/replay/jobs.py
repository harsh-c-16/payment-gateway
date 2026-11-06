"""Durable replay ownership, frozen original-source selection and resumable execution."""

import hashlib
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb
from pydantic import TypeAdapter

from pipelines.curation.db import lock_key, one, rows, sink_lock
from pipelines.ingestion.bronze import SourceCorruption
from pipelines.storage.publication import provenance, stream_rows
from shared.contracts.analytics import (
    RawBatchReceipt,
    ReplayAccepted,
    ReplayJob,
    ReplayRequest,
    ReplayStatus,
)
from shared.contracts.common import IdempotencyKey, UUIDText
from shared.contracts.events import Namespace
from shared.event_transport.schemas import canonical_json


class ReplayConflict(ValueError):
    pass


class ReplayMismatch(RuntimeError):
    pass


def provider_hash(pipeline, namespace):
    identity = {
        "provenance": provenance(pipeline, namespace),
        "schema_cache": [*pipeline.codec.cache.entries.values(), *pipeline.codec.cache.historical],
    }
    return hashlib.sha256(canonical_json(identity)).hexdigest()


def capture_scope(tx, pipeline, receipt, replay_id):
    receipt = RawBatchReceipt.model_validate(receipt)
    origin = receipt.records[0].namespace
    if replay_id is None:
        if one(tx, "SELECT 1 FROM replay_jobs WHERE target_namespace=%s", (origin,)):
            raise ReplayConflict("The namespace belongs to an isolated replay job")
        return origin, None, None
    job = _job(tx, replay_id)
    if (
        job["status"] != "RUNNING"
        or job["transform_version"] != pipeline.transform_version
        or job["provider_sha256"] != provider_hash(pipeline, job["target_namespace"])
    ):
        raise ReplayConflict("Replay is not running with the requested transform")
    selected = rows(
        tx,
        """SELECT raw_locator,raw_sha256,ingested_at FROM replay_inputs
        WHERE replay_id=%s AND capture_id=%s""",
        (replay_id, receipt.capture_id),
    )
    expected = {r["raw_locator"]: r["raw_sha256"] for r in selected}
    actual = {r.source.raw_locator: r.raw_sha256 for r in receipt.records}
    if not expected or any(actual.get(k) != v for k, v in expected.items()):
        raise SourceCorruption("Replay input is not the frozen original capture selection")
    return (
        job["target_namespace"],
        set(expected),
        {r["raw_locator"]: r["ingested_at"] for r in selected},
    )


def _job(tx, replay_id):
    TypeAdapter(UUIDText).validate_python(replay_id)
    job = one(tx, "SELECT * FROM replay_jobs WHERE replay_id=%s", (replay_id,))
    if job is None:
        raise LookupError("Unknown replay job")
    return job


def _freeze_capture(tx, replay_id, ref):
    try:
        identity = str(UUID(ref))
    except ValueError:
        return False
    captured = one(tx, "SELECT receipt FROM bronze_captures WHERE capture_id=%s", (identity,))
    if captured is None:
        raise LookupError("Unknown Bronze capture manifest")
    tx.execute(
        """INSERT INTO replay_inputs
        SELECT %s,%s,r->>'namespace',r->'source'->>'topic',
        (r->'source'->>'partition')::integer,(r->'source'->>'offset')::bigint,
        r->'source'->>'raw_locator',r->>'raw_sha256',s.ingested_at
        FROM jsonb_array_elements(%s->'records') r
        JOIN source_receipts s ON s.namespace=r->>'namespace' AND s.topic=r->'source'->>'topic'
        AND s.partition=(r->'source'->>'partition')::integer
        AND s.offset_number=(r->'source'->>'offset')::bigint
        ON CONFLICT DO NOTHING""",
        (replay_id, identity, Jsonb(captured["receipt"])),
    )
    conflicting = one(
        tx,
        """SELECT 1 FROM jsonb_array_elements(%s->'records') r
        LEFT JOIN replay_inputs p ON p.replay_id=%s AND p.topic=r->'source'->>'topic'
        AND p.partition=(r->'source'->>'partition')::integer
        AND p.offset_number=(r->'source'->>'offset')::bigint
        LEFT JOIN source_receipts s ON s.namespace=r->>'namespace'
        AND s.topic=r->'source'->>'topic' AND s.partition=(r->'source'->>'partition')::integer
        AND s.offset_number=(r->'source'->>'offset')::bigint
        WHERE p.raw_sha256 IS NULL OR s.raw_sha256 IS NULL
        OR p.raw_sha256<>r->>'raw_sha256' OR s.raw_sha256<>r->>'raw_sha256' LIMIT 1""",
        (Jsonb(captured["receipt"]), replay_id),
    )
    if conflicting:
        raise SourceCorruption("Selected capture differs from the original durable source")
    return True


def _freeze_publication(tx, replay_id, ref):
    # Paired compaction carries unchanged lineage forward; pin its first paired generation.
    found = rows(
        tx,
        """SELECT namespace,min(generation) AS generation FROM snapshot_manifests
        WHERE manifest->'input_manifest_ids' @> %s::jsonb
        GROUP BY namespace LIMIT 2""",
        (Jsonb([ref]),),
    )
    if len(found) != 1:
        raise LookupError("Unknown or ambiguous publication lineage ID")
    namespace, generation = found[0]["namespace"], found[0]["generation"]
    tx.execute(
        """INSERT INTO replay_references SELECT %s,namespace,dataset,generation
        FROM snapshot_manifests WHERE namespace=%s AND generation=%s""",
        (replay_id, namespace, generation),
    )
    if (
        tx.execute(
            "SELECT count(*) FROM replay_references WHERE replay_id=%s", (replay_id,)
        ).fetchone()[0]
        != 2
    ):
        raise SourceCorruption("A paired Silver/Gold reference is required")
    tx.execute(
        """WITH RECURSIVE ancestry AS (
        SELECT generation,(manifest->>'parent_generation')::bigint AS parent
        FROM snapshot_manifests WHERE namespace=%s AND dataset='silver' AND generation=%s
        UNION ALL SELECT s.generation,(s.manifest->>'parent_generation')::bigint
        FROM snapshot_manifests s JOIN ancestry a ON s.generation=a.parent
        WHERE s.namespace=%s AND s.dataset='silver'), members AS (
        SELECT DISTINCT m.event_id FROM manifest_members m JOIN ancestry a USING(generation)
        WHERE m.namespace=%s AND m.dataset='silver')
        INSERT INTO replay_inputs
        SELECT %s,s.capture_id,b.namespace,s.topic,s.partition,s.offset_number,
            s.raw_locator,s.raw_sha256,s.ingested_at
        FROM members m JOIN silver_events e USING(event_id)
        JOIN source_receipts s ON s.namespace=e.namespace AND s.topic=e.source_topic
            AND s.partition=e.source_partition AND s.offset_number=e.source_offset
        JOIN bronze_captures b USING(capture_id) WHERE e.namespace=%s""",
        (namespace, generation, namespace, namespace, replay_id, namespace),
    )


def create_replay(pipeline, request, *, idempotency_key=None, source_namespace=None):
    request = ReplayRequest.model_validate(request)
    if request.transform_version != pipeline.transform_version:
        raise ValueError("The requested transform is not installed in this provider")
    refs = sorted(request.source_manifest_ids)
    if len(set(refs)) != len(refs):
        raise ValueError("Repeated replay manifest ID")
    request = request.model_copy(update={"source_manifest_ids": refs})
    digest = hashlib.sha256(canonical_json(request.model_dump(mode="json"))).hexdigest()
    key = TypeAdapter(IdempotencyKey).validate_python(
        digest if idempotency_key is None else idempotency_key
    )
    ns = request.target_namespace
    request_namespace = (
        ns if source_namespace is None else TypeAdapter(Namespace).validate_python(source_namespace)
    )
    with pipeline.connect() as tx, tx.transaction():
        tx.execute(
            "SELECT pg_advisory_xact_lock(%s)", (lock_key(request_namespace, "replay-key:" + key),)
        )
        sink_lock(tx, ns)
        binding = one(
            tx,
            "SELECT * FROM replay_keys WHERE request_namespace=%s AND idempotency_key=%s",
            (request_namespace, key),
        )
        existing = one(tx, "SELECT * FROM replay_jobs WHERE target_namespace=%s", (ns,))
        if (binding and binding["request_sha256"] != digest) or (
            existing and existing["request_sha256"] != digest
        ):
            raise ReplayConflict("Replay target or idempotency key already has a different request")
        if existing:
            replay_id = str(existing["replay_id"])
            if existing["status"] != "COMPLETED" and existing["provider_sha256"] != provider_hash(
                pipeline, ns
            ):
                raise ReplayConflict("Resume requires the original code, lock and schema mapping")
            tx.execute(
                """UPDATE replay_jobs SET status='PENDING',error=NULL
                WHERE replay_id=%s AND status='FAILED'""",
                (replay_id,),
            )
        else:
            occupied = one(
                tx,
                """SELECT 1 FROM (
                SELECT namespace FROM source_receipts UNION ALL SELECT namespace FROM silver_events
                UNION ALL SELECT namespace FROM pipeline_minute
                UNION ALL SELECT namespace FROM active_datasets
                UNION ALL SELECT namespace FROM bronze_captures
                UNION ALL SELECT namespace FROM processing_runs
                UNION ALL SELECT namespace FROM event_time_watermarks
                UNION ALL SELECT namespace FROM event_time_partitions
                UNION ALL SELECT namespace FROM observation_jobs
                UNION ALL SELECT namespace FROM snapshot_manifests
                UNION ALL SELECT namespace FROM gold_partition_revisions
                UNION ALL SELECT namespace FROM order_cohorts) s
                WHERE namespace=%s LIMIT 1""",
                (ns,),
            )
            if occupied:
                raise ReplayConflict("A new replay requires an empty isolated target")
            replay_id = str(uuid4())
            tx.execute(
                """INSERT INTO replay_jobs
                (replay_id,target_namespace,request,request_sha256,transform_version,
                 code_commit,provider_sha256,status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'PENDING')""",
                (
                    replay_id,
                    ns,
                    Jsonb(request.model_dump(mode="json")),
                    digest,
                    request.transform_version,
                    pipeline.code_commit,
                    provider_hash(pipeline, ns),
                ),
            )
            for ref in refs:
                if _freeze_capture(tx, replay_id, ref):
                    continue
                elif len(refs) == 1:
                    _freeze_publication(tx, replay_id, ref)
                else:
                    raise ValueError("Use multiple Bronze capture IDs or one pinned publication ID")
            info = one(
                tx,
                """SELECT count(*) AS n,count(DISTINCT namespace) AS origins,
                max(ingested_at) AS clock FROM replay_inputs WHERE replay_id=%s""",
                (replay_id,),
            )
            if not info["n"] or info["origins"] != 1:
                raise ValueError("Replay needs nonempty sources from one original namespace")
            tx.execute(
                "UPDATE replay_jobs SET clock_at=%s WHERE replay_id=%s", (info["clock"], replay_id)
            )
        if source_namespace is not None:
            origin = one(
                tx,
                "SELECT namespace FROM replay_references WHERE replay_id=%s AND dataset='silver'",
                (replay_id,),
            )
            if origin is None:
                origin = one(
                    tx,
                    "SELECT namespace FROM replay_inputs WHERE replay_id=%s LIMIT 1",
                    (replay_id,),
                )
            if origin is None or origin["namespace"] != source_namespace:
                raise ValueError("X-Namespace must identify the selected replay source")
        tx.execute(
            "INSERT INTO replay_keys VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (request_namespace, key, digest, replay_id),
        )
    return ReplayAccepted(
        replay_id=replay_id, status_url=f"/internal/v1/analytics/replays/{replay_id}"
    )


def get_status(pipeline, replay_id):
    with pipeline.connect() as tx:
        job = _job(tx, replay_id)
    return ReplayStatus(**{k: job[k] for k in ("status", "counts", "reconciliation", "error")})


def job_dto(job):
    return ReplayJob(
        replay_id=str(job["replay_id"]),
        source_manifest_ids=job["request"]["source_manifest_ids"],
        **{
            k: job[k]
            for k in (
                "target_namespace",
                "transform_version",
                "status",
                "started_at",
                "completed_at",
                "reconciliation",
            )
        },
    )


def _counts(tx, job):
    counts = dict.fromkeys(("new_valid", "duplicate_delivery", "invalid", "redelivery_noop"), 0)
    for row in rows(
        tx,
        """SELECT disposition,count(*) AS n FROM source_receipts
        WHERE namespace=%s AND disposition IS NOT NULL GROUP BY disposition""",
        (job["target_namespace"],),
    ):
        counts[row["disposition"]] = row["n"]
    counts["source_records"] = sum(counts.values())
    return counts


def run_replay(pipeline, replay_id):
    from .reconciliation import reconcile

    with pipeline.connect() as control:
        job = _job(control, replay_id)
        if job["transform_version"] != pipeline.transform_version or job[
            "provider_sha256"
        ] != provider_hash(pipeline, job["target_namespace"]):
            raise ReplayConflict("Resume requires the original code, lock and schema mapping")
        lock = lock_key(job["target_namespace"], "replay")
        if not control.execute("SELECT pg_try_advisory_lock(%s)", (lock,)).fetchone()[0]:
            return job_dto(job)
        try:
            control.execute(
                """UPDATE replay_jobs SET status='RUNNING',error=NULL,completed_at=NULL,
                reconciliation=NULL
                WHERE replay_id=%s""",
                (replay_id,),
            )
            with pipeline.connect() as tx, tx.transaction():
                for source in stream_rows(
                    tx,
                    """SELECT b.receipt FROM bronze_captures b
                    JOIN (SELECT capture_id,min(ingested_at) AS first_at FROM replay_inputs
                    WHERE replay_id=%s GROUP BY capture_id) i USING(capture_id)
                    ORDER BY i.first_at,b.capture_id""",
                    (replay_id,),
                ):
                    pipeline.curate_silver(
                        RawBatchReceipt.model_validate(source["receipt"]),
                        {"run_id": replay_id},
                        replay_id=replay_id,
                    )
            counts = _counts(control, job)
            expected = control.execute(
                "SELECT count(*) FROM replay_inputs WHERE replay_id=%s", (replay_id,)
            ).fetchone()[0]
            if counts["source_records"] != expected:
                raise SourceCorruption("Replay did not durably classify every selected source")
            if counts["new_valid"]:
                pipeline.publish_snapshot(job["target_namespace"])
            result = reconcile(pipeline, control, job, counts)
            control.execute(
                "UPDATE replay_jobs SET reconciliation=%s WHERE replay_id=%s",
                (Jsonb(result.model_dump(mode="json")) if result else None, replay_id),
            )
            if result and not result.passed:
                raise ReplayMismatch("Replay differs from its pinned semantic reference")
            control.execute(
                """UPDATE replay_jobs SET status='COMPLETED',counts=%s,
                completed_at=clock_timestamp() WHERE replay_id=%s""",
                (Jsonb(counts), replay_id),
            )
        except Exception as exc:
            # Keep restricted SQL/credentials/payloads out of the public status error.
            control.execute(
                """UPDATE replay_jobs SET status='FAILED',counts=%s,error=%s,
                completed_at=clock_timestamp() WHERE replay_id=%s""",
                (
                    Jsonb(_counts(control, job)),
                    Jsonb(
                        {
                            "type": type(exc).__name__,
                            "message": "Replay stopped; sources and target progress are retained",
                        }
                    ),
                    replay_id,
                ),
            )
        finally:
            control.execute("SELECT pg_advisory_unlock(%s)", (lock,))
        return job_dto(_job(control, replay_id))
