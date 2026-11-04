"""Idempotent inventory seeding from catalog SKU manifest."""

import hashlib
import json
import logging
from datetime import UTC, datetime

logger = logging.getLogger("inventory.seed")


def seed_inventory(db, namespace, manifest, *, default_on_hand=100):
    """Seed inventory rows from a SKU manifest. Idempotent via inventory_seeds table.

    manifest: list of dicts with at least {"sku": str}. Optional "on_hand" override.
    Returns (inserted, skipped) counts.
    """
    content = json.dumps(
        sorted([{"sku": m["sku"]} for m in manifest], key=lambda x: x["sku"]),
        sort_keys=True,
        separators=(",", ":"),
    )
    manifest_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    now = datetime.now(UTC)
    inserted = 0
    skipped = 0

    with db.transaction(statement_timeout_ms=10000) as tx:
        existing = tx.execute(
            "SELECT seed_id FROM inventory_seeds WHERE namespace = %s AND manifest_hash = %s",
            (namespace, manifest_hash),
        ).fetchone()
        if existing is not None:
            logger.info("seed manifest already applied for namespace=%s", namespace)
            return 0, len(manifest)

        seed_row = tx.execute(
            """
            INSERT INTO inventory_seeds (namespace, manifest_hash, sku_count, created_at)
            VALUES (%s, %s, %s, %s)
            RETURNING seed_id
            """,
            (namespace, manifest_hash, len(manifest), now),
        ).fetchone()
        seed_id = seed_row["seed_id"]

        for item in manifest:
            sku = item["sku"]
            on_hand = item.get("on_hand", default_on_hand)
            result = tx.execute(
                """
                INSERT INTO inventory (namespace, sku, on_hand, reserved, stock_version, changed_at)
                VALUES (%s, %s, %s, 0, 1, %s)
                ON CONFLICT (namespace, sku) DO NOTHING
                RETURNING sku
                """,
                (namespace, sku, on_hand, now),
            ).fetchone()
            if result is not None:
                inserted += 1
            else:
                skipped += 1

            tx.execute(
                """
                INSERT INTO inventory_seed_chunks (namespace, seed_id, sku, on_hand_seeded)
                VALUES (%s, %s, %s, %s)
                """,
                (namespace, seed_id, sku, on_hand),
            )

    logger.info("seed complete: inserted=%d skipped=%d namespace=%s", inserted, skipped, namespace)
    return inserted, skipped
