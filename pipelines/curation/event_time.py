"""Durable partition clocks and late-revision annotations, under the sink lock."""

from datetime import timedelta

from .db import one, sink_lock

POLICY = {
    "window_seconds": 60,
    "allowed_lateness_seconds": 120,
    "idle_seconds": 10,
    "future_tolerance_seconds": 5,
    "finality": "provisional; valid late facts remain revisable",
    "clock": "analytics processing wall time; original event_time is preserved",
}


def processing_clock(tx, namespace):
    return tx.execute(
        """SELECT coalesce((SELECT clock_at FROM replay_jobs WHERE target_namespace=%s),
                           clock_timestamp())""",
        (namespace,),
    ).fetchone()[0]


def advance_watermark(tx, namespace, now=None):
    sink_lock(tx, namespace)
    if now is None:
        now = processing_clock(tx, namespace)
    return one(
        tx,
        """INSERT INTO event_time_watermarks(namespace,watermark,evaluated_at,active_partitions)
        SELECT %s,min(maximum_event_time)-interval '120 seconds',%s,count(*)
        FROM event_time_partitions WHERE namespace=%s
            AND last_seen_at > %s-interval '10 seconds'
        ON CONFLICT(namespace) DO UPDATE SET
            watermark=greatest(event_time_watermarks.watermark,EXCLUDED.watermark),
            evaluated_at=EXCLUDED.evaluated_at,active_partitions=EXCLUDED.active_partitions
        RETURNING *""",
        (namespace, now, namespace, now),
    )


def track_event_time(tx, record, event, *, new_fact, namespace=None):
    namespace = namespace or record.source_namespace
    now = processing_clock(tx, namespace)
    before = advance_watermark(tx, namespace, now)["watermark"]
    previous = one(
        tx,
        """SELECT * FROM event_time_partitions
        WHERE namespace=%s AND topic=%s AND partition=%s""",
        (namespace, record.topic, record.partition),
    )
    flags = []
    resumed = previous and now - previous["last_seen_at"] >= timedelta(seconds=10)
    older = previous and event.event_time < previous["maximum_event_time"]
    if older:
        flags.append("OUT_OF_ORDER")
    if resumed:
        flags.append("RESUMED_IDLE_PARTITION")
    late = (before is not None and event.event_time < before) or (resumed and older)
    if late:
        flags.append("LATE_RECONCILIATION")
    if event.event_time > record.ingested_at:
        flags.append("FUTURE_WITHIN_TOLERANCE")
    tx.execute(
        """INSERT INTO event_time_partitions VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT(namespace,topic,partition) DO UPDATE SET
        maximum_event_time=greatest(event_time_partitions.maximum_event_time,
            EXCLUDED.maximum_event_time),last_seen_at=EXCLUDED.last_seen_at""",
        (namespace, record.topic, record.partition, event.event_time, now),
    )
    advance_watermark(tx, namespace, now)
    if new_fact:
        tx.execute(
            """INSERT INTO event_time_observations
            SELECT %s,%s,%s,%s,%s,revision,%s FROM pipeline_minute
            WHERE namespace=%s AND minute=%s AND event_type=%s AND source_service=%s""",
            (
                namespace,
                event.event_id,
                now,
                before,
                flags or ["WITHIN_POLICY"],
                "LATE_RECONCILIATION" if late else "INGESTION",
                namespace,
                event.event_time.replace(second=0, microsecond=0),
                event.event_type,
                event.source_service,
            ),
        )
