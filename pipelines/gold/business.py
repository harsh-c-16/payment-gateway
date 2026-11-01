"""Transactional business facts, reached-stage sets and exact cohort projections."""

from datetime import UTC, datetime
from decimal import Decimal

from psycopg import sql

from shared.contracts.events import EVENTS, EventEnvelope, ReasonCode

TABLES = (
    "order_fact",
    "daily_conversion",
    "checkout_funnel",
    "payment_failures",
    "inventory_failures",
    "search_performance",
)
BUSINESS_EVENTS = {name for name in EVENTS if name.startswith(("ORDER_", "PAYMENT_", "INVENTORY_"))}
BUSINESS_EVENTS |= {"STOCK_UPDATED", "PRODUCT_RETRIEVED"}


class GoldConflict(ValueError):
    def __init__(self, message, reason=ReasonCode.INVARIANT_VIOLATION):
        super().__init__(message)
        self.reason = reason


def _latest(tx, table, key, event, payload):
    from pipelines.curation.db import one

    old = one(
        tx,
        sql.SQL("SELECT * FROM {} WHERE namespace=%s AND {}=%s").format(
            sql.Identifier(table), sql.Identifier(key)
        ),
        (event.namespace, payload[key]),
    )
    if old:
        if table == "payment_fact" and str(old["order_id"]) != payload["order_id"]:
            raise GoldConflict("Payment attempt changed its parent order")
        if (
            old["aggregate_version"] == event.aggregate_version
            and str(old["event_id"]) != event.event_id
        ):
            raise GoldConflict(
                "Business aggregate version conflicts", ReasonCode.AGGREGATE_VERSION_CONFLICT
            )
        if old["aggregate_version"] >= event.aggregate_version:
            return old, False
    values = dict(
        namespace=event.namespace,
        event_id=event.event_id,
        aggregate_version=event.aggregate_version,
        **payload,
    )
    columns = list(values)
    tx.execute(
        sql.SQL(
            "INSERT INTO {} ({}) VALUES ({}) ON CONFLICT(namespace,{}) DO UPDATE SET {}"
        ).format(
            sql.Identifier(table),
            sql.SQL(",").join(map(sql.Identifier, columns)),
            sql.SQL(",").join(sql.Placeholder() for _ in columns),
            sql.Identifier(key),
            sql.SQL(",").join(
                sql.SQL("{}=EXCLUDED.{}").format(sql.Identifier(c), sql.Identifier(c))
                for c in columns
                if c not in ("namespace", key)
            ),
        ),
        tuple(values.values()),
    )
    return old, True


def _reach(tx, event, order_id, stage):
    return (
        tx.execute(
            """INSERT INTO funnel_stages VALUES (%s,%s,%s,%s)
        ON CONFLICT DO NOTHING RETURNING event_id""",
            (event.namespace, order_id, stage, event.event_id),
        ).fetchone()
        is not None
    )


def apply_business(event, tx, transform_version):
    from pipelines.curation.db import one

    if event.event_type not in BUSINESS_EVENTS:
        return set()
    claimed = tx.execute(
        """INSERT INTO gold_business_contributions VALUES (%s,%s)
        ON CONFLICT DO NOTHING RETURNING event_id""",
        (event.namespace, event.event_id),
    ).fetchone()
    if not claimed:
        return set()
    tx.execute(
        "INSERT INTO export_pending VALUES (%s,%s) ON CONFLICT DO NOTHING",
        (event.namespace, event.event_id),
    )
    payload = EVENTS[event.event_type][4].model_validate(event.payload).model_dump()
    dirty = set()
    order_id = payload.get("order_id")
    if event.event_type.startswith("ORDER_"):
        payload.setdefault("reservation_id", None)
        payload.setdefault("payment_id", None)
        old, changed = _latest(tx, "order_fact", "order_id", event, payload)
        cohort = payload["created_at"].date()
        new_cohort = tx.execute(
            """INSERT INTO order_cohorts VALUES (%s,%s,%s) ON CONFLICT DO NOTHING
            RETURNING cohort_date""",
            (event.namespace, cohort, payload["currency"]),
        ).fetchone()
        if new_cohort:
            # Empty historical cohorts must be independent of delivery order.
            dirty |= {(table, cohort) for table in ("daily_conversion", "checkout_funnel")}
        if changed:
            dates = {cohort} | ({old["created_at"].date()} if old else set())
            dirty |= {
                (table, date)
                for table in ("order_fact", "daily_conversion", "checkout_funnel")
                for date in dates
            }
        _reach(tx, event, order_id, "created")
        if event.event_type == "ORDER_CONFIRMED":
            gained = _reach(tx, event, order_id, "confirmed")
            if gained:
                current = one(
                    tx,
                    "SELECT created_at FROM order_fact WHERE namespace=%s AND order_id=%s",
                    (event.namespace, order_id),
                )
                dirty.add(("checkout_funnel", current["created_at"].date()))
        tx.execute(
            "DELETE FROM pending_order_joins WHERE namespace=%s AND order_id=%s",
            (event.namespace, order_id),
        )
    else:
        stage = {
            "PAYMENT_SUCCESS": "payment_success",
            "INVENTORY_RESERVED": "reserved",
            "INVENTORY_COMMITTED": "inventory_committed",
        }.get(event.event_type)
        if order_id is not None:
            parent = one(
                tx,
                "SELECT created_at FROM order_fact WHERE namespace=%s AND order_id=%s",
                (event.namespace, order_id),
            )
            if parent is None:
                tx.execute(
                    "INSERT INTO pending_order_joins VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                    (event.namespace, event.event_id, order_id),
                )
            if stage and _reach(tx, event, order_id, stage) and parent:
                dirty.add(("checkout_funnel", parent["created_at"].date()))
        if event.event_type.startswith("PAYMENT_"):
            old, changed = _latest(tx, "payment_fact", "payment_id", event, payload)
            if changed:
                dirty.add(("payment_failures", payload["attempt_created_at"].date()))
                if old:
                    dirty.add(("payment_failures", old["attempt_created_at"].date()))
        elif event.event_type == "INVENTORY_REJECTED":
            old = one(
                tx,
                """SELECT * FROM inventory_failure_outcomes WHERE namespace=%s
                AND order_id=%s AND reservation_request_id=%s""",
                (event.namespace, order_id, payload["reservation_request_id"]),
            )
            if old and old["reason_code"] != payload["reason_code"]:
                raise GoldConflict("Reservation request has conflicting rejection reasons")
            if old is None or event.event_time < old["first_event_time"]:
                tx.execute(
                    """INSERT INTO inventory_failure_outcomes VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(namespace,order_id,reservation_request_id) DO UPDATE SET
                    first_event_time=EXCLUDED.first_event_time,event_id=EXCLUDED.event_id""",
                    (
                        event.namespace,
                        order_id,
                        payload["reservation_request_id"],
                        payload["reason_code"],
                        event.event_time,
                        event.event_id,
                    ),
                )
                dirty.add(("inventory_failures", event.event_time.date()))
                if old:
                    dirty.add(("inventory_failures", old["first_event_time"].date()))
        elif event.event_type == "PRODUCT_RETRIEVED":
            old, changed = _latest(
                tx,
                "search_fact",
                "search_id",
                event,
                {
                    "search_id": payload["search_id"],
                    "completed_at": event.event_time,
                    "mode": payload["mode"],
                    "returned_count": payload["returned_count"],
                    "duration_ms": Decimal(str(payload["duration_ms"])),
                },
            )
            if changed:
                dirty.add(("search_performance", event.event_time.date()))
                if old:
                    dirty.add(("search_performance", old["completed_at"].date()))
    for table, date in sorted(dirty):
        tx.execute(
            """INSERT INTO gold_partition_revisions VALUES (%s,%s,%s,1,%s)
            ON CONFLICT(namespace,table_name,cohort_date) DO UPDATE SET
            revision=gold_partition_revisions.revision+1,transform_version=EXCLUDED.transform_version""",
            (event.namespace, table, date, transform_version),
        )
        tx.execute(
            "INSERT INTO gold_dirty_keys VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
            (event.namespace, event.event_id, table, date),
        )
    return dirty


def backfill_business(tx):
    # A server cursor bounds upgrade memory; migration 004 holds the Silver write lock.
    with tx.cursor(name="analytics_business_backfill") as cursor:
        cursor.execute(
            """SELECT document FROM silver_events WHERE event_type=ANY(%s)
            ORDER BY namespace,source_service,aggregate_type,aggregate_id,aggregate_version""",
            (sorted(BUSINESS_EVENTS),),
        )
        for (document,) in cursor:
            apply_business(EventEnvelope.model_validate(document), tx, "m07-business-v1")


def business_query(table):
    if table not in TABLES:
        raise ValueError("Unknown business table")
    source = (
        sql.SQL("SELECT o.*,(created_at AT TIME ZONE 'UTC')::date AS cohort_date FROM order_fact o")
        if table == "order_fact"
        else sql.SQL("SELECT * FROM {}").format(sql.Identifier(table))
    )
    return sql.SQL("""SELECT f.*,r.revision,r.transform_version FROM ({}) f
        JOIN gold_partition_revisions r ON r.namespace=f.namespace
        AND r.cohort_date=f.cohort_date AND r.table_name=%s
        WHERE f.namespace=%s AND f.cohort_date=%s""").format(source)


def business_row(row, table):
    for key, value in list(row.items()):
        if key.endswith("_id") and value is not None:
            row[key] = str(value)
    row["cohort_date"] = datetime.combine(row["cohort_date"], datetime.min.time(), tzinfo=UTC)
    if table == "order_fact":
        row["order_version"] = row.pop("aggregate_version")
    return row
