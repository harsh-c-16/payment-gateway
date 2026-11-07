"""All-or-nothing inventory reservation with sorted SKU locking, commit, release, expiry."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from services.inventory.errors import conflict, not_found


def reserve(db, events, namespace, request, context):
    """All-or-nothing reservation: sort SKUs, lock rows, decrement available."""
    sorted_items = sorted(request.items, key=lambda i: i.sku)
    reservation_id = str(uuid4())
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=request.ttl_seconds)

    with db.transaction() as tx:
        tx.execute(
            """
            INSERT INTO reservations (namespace, reservation_id, order_id, state, expires_at, created_at, updated_at)
            VALUES (%s, %s, %s, 'ACTIVE', %s, %s, %s)
            ON CONFLICT (namespace, order_id) DO NOTHING
            RETURNING reservation_id
            """,
            (namespace, reservation_id, request.order_id, expires_at, now, now),
        )
        existing = tx.execute(
            "SELECT reservation_id, state FROM reservations WHERE namespace = %s AND order_id = %s",
            (namespace, request.order_id),
        ).fetchone()
        if existing["reservation_id"] != reservation_id:
            # A retried reserve for the same order (lost response, crash, lease expiry) replays
            # the live reservation; a RELEASED/EXPIRED row is a tombstone and stays rejected.
            if existing["state"] in ("ACTIVE", "COMMITTED"):
                return _snapshot(tx, namespace, existing["reservation_id"], request.order_id)
            raise conflict(
                "Reservation already exists for this order.",
                details={"existing_state": existing["state"]},
            )

        receipts = []
        for item in sorted_items:
            row = tx.execute(
                """
                UPDATE inventory
                SET reserved = reserved + %s,
                    stock_version = stock_version + 1,
                    changed_at = %s
                WHERE namespace = %s AND sku = %s
                  AND (on_hand - reserved) >= %s
                RETURNING stock_version
                """,
                (item.quantity, now, namespace, item.sku, item.quantity),
            ).fetchone()
            if row is None:
                raise conflict(
                    f"Insufficient stock for SKU {item.sku}.",
                    details={"sku": item.sku},
                )
            receipts.append({"sku": item.sku, "stock_version": row["stock_version"]})

            tx.execute(
                """
                INSERT INTO reservation_items (namespace, reservation_id, sku, quantity)
                VALUES (%s, %s, %s, %s)
                """,
                (namespace, reservation_id, item.sku, item.quantity),
            )

            stock = tx.execute(
                "SELECT on_hand, reserved FROM inventory WHERE namespace = %s AND sku = %s",
                (namespace, item.sku),
            ).fetchone()
            events.append(
                tx,
                event_type="INVENTORY_RESERVED",
                payload={
                    "sku": item.sku,
                    "on_hand": stock["on_hand"],
                    "reserved": stock["reserved"],
                    "available": stock["on_hand"] - stock["reserved"],
                    "stock_version": row["stock_version"],
                    "changed_at": now.isoformat().replace("+00:00", "Z"),
                    "order_id": request.order_id,
                    "reservation_id": reservation_id,
                    "reason_code": None,
                },
                context=context,
                aggregate_type="sku",
                aggregate_id=item.sku,
                aggregate_version=row["stock_version"],
                event_time=now,
            )

    return {
        "reservation_id": reservation_id,
        "order_id": request.order_id,
        "state": "ACTIVE",
        "items": [{"sku": i.sku, "quantity": i.quantity} for i in sorted_items],
        "expires_at": expires_at,
        "inventory_receipts": receipts,
        "updated_at": now,
    }


def get_reservation_by_order(db, namespace, order_id):
    with db.transaction() as tx:
        row = tx.execute(
            """
            SELECT reservation_id, order_id, state, expires_at, updated_at
            FROM reservations WHERE namespace = %s AND order_id = %s
            """,
            (namespace, order_id),
        ).fetchone()
        if row is None:
            raise not_found("Reservation")
        items = tx.execute(
            "SELECT sku, quantity FROM reservation_items WHERE namespace = %s AND reservation_id = %s",
            (namespace, row["reservation_id"]),
        ).fetchall()
    return {
        **row,
        "items": items,
        "inventory_receipts": [],
    }


def commit_reservation(db, events, namespace, order_id, reservation_id, context):
    """Commit: decrement on_hand, clear reserved for each item. Idempotent if already COMMITTED."""
    now = datetime.now(UTC)

    with db.transaction() as tx:
        row = tx.execute(
            """
            SELECT reservation_id, state, expires_at
            FROM reservations
            WHERE namespace = %s AND order_id = %s
            FOR UPDATE
            """,
            (namespace, order_id),
        ).fetchone()
        if row is None:
            raise not_found("Reservation")
        if row["reservation_id"] != reservation_id:
            raise conflict("Reservation ID mismatch.")
        if row["state"] == "COMMITTED":
            return _snapshot(tx, namespace, row["reservation_id"], order_id)
        if row["state"] != "ACTIVE":
            raise conflict(f"Cannot commit reservation in state {row['state']}.")

        items = tx.execute(
            "SELECT sku, quantity FROM reservation_items WHERE namespace = %s AND reservation_id = %s",
            (namespace, reservation_id),
        ).fetchall()

        for item in sorted(items, key=lambda i: i["sku"]):
            updated = tx.execute(
                """
                UPDATE inventory
                SET on_hand = on_hand - %s,
                    reserved = reserved - %s,
                    stock_version = stock_version + 1,
                    changed_at = %s
                WHERE namespace = %s AND sku = %s
                  AND reserved >= %s
                RETURNING stock_version, on_hand, reserved
                """,
                (item["quantity"], item["quantity"], now, namespace, item["sku"], item["quantity"]),
            ).fetchone()
            if updated is None:
                raise conflict(f"Inconsistent reserved count for SKU {item['sku']}.")
            events.append(
                tx,
                event_type="INVENTORY_COMMITTED",
                payload={
                    "sku": item["sku"],
                    "on_hand": updated["on_hand"],
                    "reserved": updated["reserved"],
                    "available": updated["on_hand"] - updated["reserved"],
                    "stock_version": updated["stock_version"],
                    "changed_at": now.isoformat().replace("+00:00", "Z"),
                    "order_id": order_id,
                    "reservation_id": reservation_id,
                    "reason_code": None,
                },
                context=context,
                aggregate_type="sku",
                aggregate_id=item["sku"],
                aggregate_version=updated["stock_version"],
                event_time=now,
            )

        tx.execute(
            """
            UPDATE reservations SET state = 'COMMITTED', updated_at = %s
            WHERE namespace = %s AND reservation_id = %s
            """,
            (now, namespace, reservation_id),
        )
        return _snapshot(tx, namespace, reservation_id, order_id)


def release_reservation(db, events, namespace, order_id, reason, context):
    """Release: return reserved qty back to available. Idempotent if already RELEASED/EXPIRED."""
    now = datetime.now(UTC)

    with db.transaction() as tx:
        row = tx.execute(
            """
            SELECT reservation_id, state
            FROM reservations
            WHERE namespace = %s AND order_id = %s
            FOR UPDATE
            """,
            (namespace, order_id),
        ).fetchone()
        if row is None:
            return _tombstone_release(tx, namespace, order_id, reason, now)
        if row["state"] in ("RELEASED", "EXPIRED"):
            return _snapshot(tx, namespace, row["reservation_id"], order_id)
        if row["state"] == "COMMITTED":
            raise conflict("Cannot release a committed reservation.")

        reservation_id = row["reservation_id"]
        _unreserve_items(tx, events, namespace, reservation_id, order_id, now, context)

        tx.execute(
            """
            UPDATE reservations SET state = 'RELEASED', updated_at = %s
            WHERE namespace = %s AND reservation_id = %s
            """,
            (now, namespace, reservation_id),
        )
        return _snapshot(tx, namespace, reservation_id, order_id)


def expire_reservations(db, events, context, *, batch_size=50):
    """Expire ACTIVE reservations past their TTL. Returns count expired."""
    now = datetime.now(UTC)
    expired_count = 0

    with db.transaction(statement_timeout_ms=5000) as tx:
        rows = tx.execute(
            """
            SELECT reservation_id, order_id, namespace
            FROM reservations
            WHERE state = 'ACTIVE' AND expires_at <= %s
            ORDER BY expires_at
            LIMIT %s
            FOR UPDATE SKIP LOCKED
            """,
            (now, batch_size),
        ).fetchall()

        for row in rows:
            ns = row["namespace"]
            rid = row["reservation_id"]
            oid = row["order_id"]

            _unreserve_items(tx, events, ns, rid, oid, now, context)

            tx.execute(
                """
                UPDATE reservations SET state = 'EXPIRED', updated_at = %s
                WHERE namespace = %s AND reservation_id = %s AND state = 'ACTIVE'
                """,
                (now, ns, rid),
            )
            expired_count += 1

    return expired_count


def get_stock(db, namespace, sku):
    with db.transaction() as tx:
        row = tx.execute(
            """
            SELECT sku, on_hand, reserved, (on_hand - reserved) AS available,
                   stock_version, changed_at
            FROM inventory WHERE namespace = %s AND sku = %s
            """,
            (namespace, sku),
        ).fetchone()
    if row is None:
        raise not_found("SKU")
    return row


def _unreserve_items(tx, events, namespace, reservation_id, order_id, now, context):
    items = tx.execute(
        "SELECT sku, quantity FROM reservation_items WHERE namespace = %s AND reservation_id = %s",
        (namespace, reservation_id),
    ).fetchall()
    for item in sorted(items, key=lambda i: i["sku"]):
        updated = tx.execute(
            """
            UPDATE inventory
            SET reserved = reserved - %s,
                stock_version = stock_version + 1,
                changed_at = %s
            WHERE namespace = %s AND sku = %s
              AND reserved >= %s
            RETURNING stock_version, on_hand, reserved
            """,
            (item["quantity"], now, namespace, item["sku"], item["quantity"]),
        ).fetchone()
        if updated is not None:
            events.append(
                tx,
                event_type="INVENTORY_RELEASED",
                payload={
                    "sku": item["sku"],
                    "on_hand": updated["on_hand"],
                    "reserved": updated["reserved"],
                    "available": updated["on_hand"] - updated["reserved"],
                    "stock_version": updated["stock_version"],
                    "changed_at": now.isoformat().replace("+00:00", "Z"),
                    "order_id": order_id,
                    "reservation_id": reservation_id,
                    "reason_code": None,
                },
                context=context,
                aggregate_type="sku",
                aggregate_id=item["sku"],
                aggregate_version=updated["stock_version"],
                event_time=now,
            )


def _tombstone_release(tx, namespace, order_id, reason, now):
    """Create a tombstone RELEASED reservation when the saga releases before any reservation existed."""
    reservation_id = str(uuid4())
    tx.execute(
        """
        INSERT INTO reservations (namespace, reservation_id, order_id, state, expires_at, created_at, updated_at)
        VALUES (%s, %s, %s, 'RELEASED', %s, %s, %s)
        ON CONFLICT (namespace, order_id) DO NOTHING
        RETURNING reservation_id
        """,
        (namespace, reservation_id, order_id, now, now, now),
    )
    check = tx.execute(
        "SELECT reservation_id, state FROM reservations WHERE namespace = %s AND order_id = %s",
        (namespace, order_id),
    ).fetchone()
    return _snapshot(tx, namespace, check["reservation_id"], order_id)


def _snapshot(tx, namespace, reservation_id, order_id):
    row = tx.execute(
        "SELECT reservation_id, order_id, state, expires_at, updated_at FROM reservations WHERE namespace = %s AND reservation_id = %s",
        (namespace, reservation_id),
    ).fetchone()
    items = tx.execute(
        "SELECT sku, quantity FROM reservation_items WHERE namespace = %s AND reservation_id = %s",
        (namespace, reservation_id),
    ).fetchall()
    return {
        **row,
        "items": items,
        "inventory_receipts": [],
    }
