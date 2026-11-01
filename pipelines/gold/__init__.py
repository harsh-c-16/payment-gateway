"""Unique contributions, latest business facts and reached-stage sets in one transaction."""

from pipelines.ingestion.receipts import _transaction
from shared.contracts.analytics import DirtyPartitionSet
from shared.contracts.events import EventEnvelope


def aggregate_gold(new_facts, db_transaction, *, transform_version="m07-business-v1"):
    _transaction(db_transaction)
    from pipelines.curation.db import sink_lock

    from .business import apply_business

    changed = []
    dirty = set()
    with db_transaction.transaction():
        for event in new_facts:
            if not isinstance(event, EventEnvelope):
                raise TypeError("Only business events contribute to pipeline_minute")
            sink_lock(db_transaction, event.namespace)
            inserted = db_transaction.execute(
                """INSERT INTO reducer_contributions(namespace,event_id) VALUES (%s,%s)
                   ON CONFLICT DO NOTHING RETURNING event_id""",
                (event.namespace, event.event_id),
            ).fetchone()
            if inserted:
                db_transaction.execute(
                    """INSERT INTO pipeline_minute
                       (namespace,minute,event_type,source_service,unique_events,revision,transform_version)
                       VALUES (%s,%s,%s,%s,1,1,%s)
                       ON CONFLICT(namespace,minute,event_type,source_service) DO UPDATE SET
                       unique_events=pipeline_minute.unique_events+1,
                       revision=pipeline_minute.revision+1,
                       transform_version=EXCLUDED.transform_version""",
                    (
                        event.namespace,
                        event.event_time.replace(second=0, microsecond=0),
                        event.event_type,
                        event.source_service,
                        transform_version,
                    ),
                )
                db_transaction.execute(
                    "INSERT INTO export_pending(namespace,event_id) VALUES (%s,%s)",
                    (event.namespace, event.event_id),
                )
                changed.append(event)
                dirty |= apply_business(event, db_transaction, transform_version)
    dirty |= {("pipeline_minute", e.event_time.date()) for e in changed}
    return DirtyPartitionSet(
        logical_keys=sorted(table + ":" + date.isoformat() for table, date in dirty),
        new_event_ids=[e.event_id for e in changed],
        affected_tables=sorted({table for table, _ in dirty}),
        minimum_event_time=min(e.event_time for e in changed) if changed else None,
    )
