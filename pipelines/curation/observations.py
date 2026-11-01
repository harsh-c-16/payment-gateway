"""Retriable post-COMMIT upper-bound observations and ordered receipt changes."""

from datetime import UTC, datetime
from uuid import uuid4

from psycopg.types.json import Jsonb

from .db import journal, one, rows, sink_lock


def enqueue_observation(tx, namespace, kind, members):
    job_id = str(uuid4())
    tx.execute(
        "INSERT INTO observation_jobs(namespace,job_id,kind,members) VALUES (%s,%s,%s,%s)",
        (namespace, job_id, kind, Jsonb(members)),
    )
    return job_id


def observe(connect, namespace, job_id, *, recovery=False):
    observed = datetime.now(UTC)
    with connect() as tx, tx.transaction():
        sink_lock(tx, namespace)
        job = one(
            tx,
            "SELECT * FROM observation_jobs WHERE namespace=%s AND job_id=%s FOR UPDATE",
            (namespace, job_id),
        )
        if job is None or job["observed_at"] is not None:
            return
        if job["kind"] == "sink":
            for source in job["members"]:
                updated = rows(
                    tx,
                    """UPDATE source_receipts SET
                    silver_committed_observed_at=COALESCE(silver_committed_observed_at,%s),
                    timing_validity=CASE WHEN %s OR timing_validity='recovery_upper_bound'
                        THEN 'recovery_upper_bound' WHEN gold_visible_at IS NOT NULL
                        THEN 'observed' ELSE 'missing' END
                    WHERE namespace=%s AND topic=%s AND partition=%s AND offset_number=%s
                    RETURNING topic,partition,offset_number""",
                    (
                        observed,
                        recovery,
                        namespace,
                        source["topic"],
                        source["partition"],
                        source["offset_number"],
                    ),
                )
                for changed in updated:
                    journal(tx, namespace, changed)
        else:
            for event_id in job["members"]:
                visibility = one(
                    tx,
                    """UPDATE event_visibility SET
                    observed_at=COALESCE(observed_at,%s),
                    timing_validity=CASE WHEN %s THEN 'recovery_upper_bound' ELSE 'observed' END
                    WHERE namespace=%s AND event_id=%s RETURNING *""",
                    (observed, recovery, namespace, event_id),
                )
                updated = rows(
                    tx,
                    """UPDATE source_receipts SET
                    gold_visible_at=%s,visibility_generation=%s,
                    timing_validity=CASE WHEN %s OR timing_validity='recovery_upper_bound'
                        THEN 'recovery_upper_bound' WHEN silver_committed_observed_at IS NOT NULL
                        THEN 'observed' ELSE 'missing' END
                    WHERE namespace=%s AND event_id=%s
                      AND disposition IN ('new_valid','duplicate_delivery')
                    RETURNING topic,partition,offset_number""",
                    (
                        visibility["observed_at"],
                        visibility["generation"],
                        recovery,
                        namespace,
                        event_id,
                    ),
                )
                for changed in updated:
                    journal(tx, namespace, changed)
        tx.execute(
            "UPDATE observation_jobs SET observed_at=%s WHERE namespace=%s AND job_id=%s",
            (observed, namespace, job_id),
        )


def recover_observations(connect, namespace):
    with connect() as tx:
        pending = rows(
            tx,
            """SELECT job_id FROM observation_jobs WHERE namespace=%s
                              AND observed_at IS NULL ORDER BY job_id LIMIT 100""",
            (namespace,),
        )
    for job in pending:
        observe(connect, namespace, job["job_id"], recovery=True)
    return len(pending)
