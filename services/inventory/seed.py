"""Idempotent, resumable synthetic stock initialization from a catalogue manifest."""

import hashlib
from datetime import UTC, datetime
from uuid import uuid4

from shared.contracts.catalog import SkuManifest
from shared.event_transport.schemas import canonical_json

CHUNK_ROWS = 1000


def seed_inventory(db, namespace, manifest, *, events, context, seed=42, default_on_hand=10_000):
    document = SkuManifest.model_validate(manifest)
    content = {key: value for key, value in manifest.items() if key != "content_sha256"}
    if hashlib.sha256(canonical_json(content)).hexdigest() != document.content_sha256:
        raise ValueError("SKU manifest hash mismatch")
    skus = [entry.sku for entry in document.sorted_skus]
    if not skus or skus != sorted(set(skus)) or document.sku_count != len(skus):
        raise ValueError("SKU manifest requires sorted unique SKUs and an exact nonzero count")
    if document.namespace != namespace or context.namespace != namespace:
        raise ValueError("SKU manifest and request namespaces must match")
    if not document.dataset_revision.strip() or document.rules_version != "flipkart-v1":
        raise ValueError("SKU manifest requires a dataset revision and flipkart-v1 rules")
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    if type(default_on_hand) is not int or not 1 <= default_on_hand <= 2**63 - 1:
        raise ValueError("initial stock must be a positive int64")
    profile_hash = hashlib.sha256(
        canonical_json({"seed": seed, "on_hand": default_on_hand})
    ).hexdigest()
    initial_digest = hashlib.sha256(
        canonical_json(
            [
                {"sku": sku, "on_hand": default_on_hand, "reserved": 0, "stock_version": 1}
                for sku in skus
            ]
        )
    ).hexdigest()
    lock_key = f"inventory-seed:{namespace}"
    with db.transaction(statement_timeout_ms=10_000) as tx:
        tx.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))
        previous = tx.execute(
            "SELECT seed_id, manifest_hash, profile_hash FROM inventory_seeds WHERE namespace=%s",
            (namespace,),
        ).fetchone()
        if previous:
            if (
                previous["manifest_hash"] != document.content_sha256
                or previous["profile_hash"] != profile_hash
            ):
                raise ValueError("A different seed or manifest requires a fresh namespace")
            seed_id = previous["seed_id"]
        else:
            if tx.execute(
                "SELECT 1 FROM inventory WHERE namespace=%s LIMIT 1", (namespace,)
            ).fetchone():
                raise ValueError("Initial inventory requires a fresh namespace")
            seed_id = str(uuid4())
            tx.execute(
                "INSERT INTO inventory_seeds "
                "(namespace,seed_id,manifest_hash,profile_hash,sku_count) VALUES (%s,%s,%s,%s,%s)",
                (namespace, seed_id, document.content_sha256, profile_hash, len(skus)),
            )

    inserted = 0
    for chunk_no, start in enumerate(range(0, len(skus), CHUNK_ROWS)):
        chunk = skus[start : start + CHUNK_ROWS]
        with db.transaction(statement_timeout_ms=10_000) as tx:
            tx.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))
            if tx.execute(
                "SELECT 1 FROM inventory_seed_chunks "
                "WHERE namespace=%s AND seed_id=%s AND chunk_no=%s",
                (namespace, seed_id, chunk_no),
            ).fetchone():
                continue
            now = datetime.now(UTC)
            for sku in chunk:
                tx.execute(
                    "INSERT INTO inventory "
                    "(namespace,sku,on_hand,reserved,stock_version,changed_at) "
                    "VALUES (%s,%s,%s,0,1,%s)",
                    (namespace, sku, default_on_hand, now),
                )
                events.append(
                    tx,
                    event_type="STOCK_UPDATED",
                    payload={
                        "sku": sku,
                        "on_hand": default_on_hand,
                        "reserved": 0,
                        "available": default_on_hand,
                        "stock_version": 1,
                        "changed_at": now.isoformat().replace("+00:00", "Z"),
                        "order_id": None,
                        "reservation_id": None,
                        "reason_code": None,
                    },
                    context=context,
                    aggregate_type="sku",
                    aggregate_id=sku,
                    aggregate_version=1,
                    event_time=now,
                    metadata={
                        "dataset_revision": document.dataset_revision,
                        "synthetic": True,
                        "scenario_source": "simulation",
                    },
                )
            tx.execute(
                "INSERT INTO inventory_seed_chunks (namespace,seed_id,chunk_no,sku_count) "
                "VALUES (%s,%s,%s,%s)",
                (namespace, seed_id, chunk_no, len(chunk)),
            )
            tx.execute(
                "UPDATE inventory_seeds SET created_skus=created_skus+%s "
                "WHERE namespace=%s AND seed_id=%s",
                (len(chunk), namespace, seed_id),
            )
        inserted += len(chunk)

    with db.transaction() as tx:
        tx.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (lock_key,))
        tx.execute(
            "UPDATE inventory_seeds SET status='COMPLETE', "
            "completed_at=COALESCE(completed_at,clock_timestamp()) "
            "WHERE namespace=%s AND seed_id=%s AND created_skus=sku_count",
            (namespace, seed_id),
        )
    return {
        "seed_id": str(seed_id),
        "seeded_count": inserted,
        "skipped_count": len(skus) - inserted,
        "sku_count": len(skus),
        "manifest_hash": document.content_sha256,
        "profile_hash": profile_hash,
        "initial_stock_digest": initial_digest,
        "status": "COMPLETE",
    }
