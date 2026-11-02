"""Stock read model: absolute inventory snapshots, version-compared and restart-safe."""

from datetime import UTC, datetime
from uuid import uuid4

from shared.contracts.catalog import ProjectionResult
from shared.contracts.events import LocalDiagnostic, ReasonCode, ValidationFailure


def _receipt(tx, record, namespace, event, outcome, previous=None, current=None, gap=False):
    tx.execute(
        'INSERT INTO projection_receipts (namespace,topic,partition,"offset",event_id,sku,outcome,'
        "previous_version,current_version,version_gap,produced_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            namespace,
            record.topic,
            record.partition,
            record.offset,
            event.event_id if event else None,
            event.payload["sku"] if event else None,
            outcome,
            previous,
            current,
            gap,
            event.produced_at if event else None,
        ),
    )


def _result(event, outcome, previous=None, current=None):
    return ProjectionResult(
        event_id=event.event_id,
        outcome=outcome,
        previous_version=previous,
        current_version=current,
        observed_commit_at=None,
    )


def _diagnose(tx, namespace, reason, content_hash, record, run_id, correlation_id, diagnostics):
    """Persist locally; the source offset may then advance. Analytics quarantines independently."""
    diagnostics(
        tx,
        LocalDiagnostic(
            diagnostic_id=str(uuid4()),
            namespace=namespace,
            run_id=run_id,
            source_service="catalog",
            reason_code=reason,
            correlation_id=correlation_id,
            created_at=datetime.now(UTC),
            content_hash=content_hash,
            restricted_content_reference=f"{record.topic}/{record.partition}/{record.offset}",
            source_coordinates={
                "topic": record.topic,
                "partition": record.partition,
                "offset": record.offset,
                "raw_locator": f"{record.topic}/{record.partition}/{record.offset}",
            },
        ),
    )


def _replace(tx, namespace, event_id, snapshot):
    tx.execute(
        """INSERT INTO stock_projection
             (namespace,sku,on_hand,reserved,stock_version,changed_at,applied_at,event_id)
           VALUES (%(namespace)s,%(sku)s,%(on_hand)s,%(reserved)s,%(stock_version)s,
                   %(changed_at)s,clock_timestamp(),%(event_id)s)
           ON CONFLICT (namespace,sku) DO UPDATE SET on_hand=EXCLUDED.on_hand,
             reserved=EXCLUDED.reserved, stock_version=EXCLUDED.stock_version,
             changed_at=EXCLUDED.changed_at, applied_at=EXCLUDED.applied_at,
             event_id=EXCLUDED.event_id
           WHERE stock_projection.stock_version < EXCLUDED.stock_version""",
        {"namespace": namespace, "event_id": event_id, **snapshot},
    )


def apply_stock_event(tx, valid_event, source_record, *, diagnostics):
    """One event in the caller's transaction; the caller commits, then advances the offset.

    A redelivered offset, a duplicate event ID, a stale version and an identical same-version
    snapshot are all no-ops. Same ID or same version with different content is a conflict.
    """
    event = valid_event.envelope
    namespace = source_record.source_namespace
    seen = tx.execute(
        "SELECT outcome FROM projection_receipts WHERE namespace=%s AND topic=%s AND partition=%s "
        'AND "offset"=%s',
        (namespace, source_record.topic, source_record.partition, source_record.offset),
    ).fetchone()
    if seen:
        return _result(event, "duplicate")

    def conflict(reason):
        _diagnose(
            tx,
            namespace,
            reason,
            valid_event.canonical_content_hash,
            source_record,
            event.run_id,
            event.correlation_id,
            diagnostics,
        )
        _receipt(tx, source_record, namespace, event, "conflict")
        return _result(event, "conflict")

    if event.namespace != namespace or event.source_service != "inventory":
        return conflict(ReasonCode.INVARIANT_VIOLATION)
    inserted = tx.execute(
        "INSERT INTO projection_event_ids (namespace,event_id,content_hash) VALUES (%s,%s,%s) "
        "ON CONFLICT DO NOTHING RETURNING 1 AS new",
        (namespace, event.event_id, valid_event.canonical_content_hash),
    ).fetchone()
    if not inserted:
        stored = tx.execute(
            "SELECT content_hash FROM projection_event_ids WHERE namespace=%s AND event_id=%s",
            (namespace, event.event_id),
        ).fetchone()["content_hash"]
        if stored != valid_event.canonical_content_hash:
            return conflict(ReasonCode.EVENT_ID_CONFLICT)
        _receipt(tx, source_record, namespace, event, "duplicate")
        return _result(event, "duplicate")
    payload = event.payload
    snapshot = {
        name: payload[name]
        for name in ("sku", "on_hand", "reserved", "stock_version", "changed_at")
    }
    version = payload["stock_version"]
    known = tx.execute(
        "SELECT 1 AS known FROM products WHERE namespace=%s AND sku=%s",
        (namespace, payload["sku"]),
    ).fetchone()
    if not known:
        tx.execute(
            "INSERT INTO stock_deferred (namespace,event_id,sku,on_hand,reserved,stock_version,"
            "changed_at) VALUES (%(namespace)s,%(event_id)s,%(sku)s,%(on_hand)s,%(reserved)s,"
            "%(stock_version)s,%(changed_at)s)",
            {"namespace": namespace, "event_id": event.event_id, **snapshot},
        )
        _receipt(tx, source_record, namespace, event, "deferred")
        return _result(event, "deferred")
    current = tx.execute(
        "SELECT on_hand,reserved,stock_version FROM stock_projection "
        "WHERE namespace=%s AND sku=%s FOR UPDATE",
        (namespace, payload["sku"]),
    ).fetchone()
    previous = current["stock_version"] if current else None
    if previous is not None and version == previous:
        if (current["on_hand"], current["reserved"]) == (payload["on_hand"], payload["reserved"]):
            _receipt(tx, source_record, namespace, event, "duplicate", previous, previous)
            return _result(event, "duplicate", previous, previous)
        return conflict(ReasonCode.AGGREGATE_VERSION_CONFLICT)
    if previous is not None and version < previous:
        _receipt(tx, source_record, namespace, event, "stale", previous, previous)
        return _result(event, "stale", previous, previous)
    _replace(tx, namespace, event.event_id, snapshot)
    gap = previous is not None and version > previous + 1
    _receipt(tx, source_record, namespace, event, "applied", previous, version, gap)
    return _result(event, "applied", previous, version)


def reject_record(tx, failure: ValidationFailure, source_record, *, diagnostics, run_id):
    """Malformed wire input never reaches the projection; it stays traceable locally."""
    namespace = source_record.source_namespace
    seen = tx.execute(
        "SELECT 1 AS seen FROM projection_receipts WHERE namespace=%s AND topic=%s "
        'AND partition=%s AND "offset"=%s',
        (namespace, source_record.topic, source_record.partition, source_record.offset),
    ).fetchone()
    if seen:
        return
    _diagnose(
        tx,
        namespace,
        failure.reason_code,
        failure.original_content_hash,
        source_record,
        run_id,
        str(uuid4()),
        diagnostics,
    )
    _receipt(tx, source_record, namespace, None, "invalid")


def reconcile_deferred(tx, namespace):
    """Apply deferred snapshots whose SKU has since been imported, newest version last."""
    rows = tx.execute(
        "DELETE FROM stock_deferred d USING products p WHERE d.namespace=%s AND "
        "p.namespace=d.namespace AND p.sku=d.sku RETURNING d.event_id,d.sku,d.on_hand,d.reserved,"
        "d.stock_version,d.changed_at",
        (namespace,),
    ).fetchall()
    for row in sorted(rows, key=lambda item: item["stock_version"]):
        _replace(tx, namespace, row.pop("event_id"), row)
    return len(rows)


def mark_observed(tx, namespace, records):
    """Post-commit freshness observation: an upper bound, never the commit timestamp itself."""
    with tx.cursor() as cursor:
        cursor.executemany(
            "UPDATE projection_receipts SET observed_commit_at=clock_timestamp() "
            'WHERE namespace=%s AND topic=%s AND partition=%s AND "offset"=%s',
            [(namespace, r.topic, r.partition, r.offset) for r in records],
        )
