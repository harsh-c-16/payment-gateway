"""Independent exact seed membership through existing SELECT-only audit bindings."""

import asyncio
import hashlib
import re

from projectctl.artifacts import canonical_json
from projectctl.providers import DependencyError

MEMBERSHIPS = ("catalog_skus", "inventory_skus", "projected_skus")


def sku_set(values):
    if (
        not isinstance(values, list)
        or not values
        or any(not isinstance(s, str) or not re.fullmatch(r"[!-~]{1,64}", s) for s in values)
        or len(set(values)) != len(values)
    ):
        raise DependencyError(
            "complete unique seed SKU lists required; counts alone are insufficient"
        )
    return set(values)


def verify_seed_membership(seed, projection):
    """Compare every active listing and stock key with the independently pinned input."""
    expected = sku_set(projection.get("active_skus"))
    counts = {}
    for field in MEMBERSHIPS:
        observed = sku_set(seed.get(field))
        if observed != expected:
            raise DependencyError("seed SKU membership differs from frozen manifest: " + field)
        counts[field] = len(observed)
    return {
        "status": "PASS",
        "expected_count": len(expected),
        "observed_counts": counts,
        "sorted_skus_sha256": hashlib.sha256(canonical_json(sorted(expected))).hexdigest(),
    }


def collect_membership(namespace):
    """Never connect during registration; use the provider's existing restricted reader."""
    if (
        not isinstance(namespace, str)
        or not re.fullmatch(r"bench-[a-z0-9][a-z0-9-]{0,55}", namespace)
        or re.match(r"bench-(dev|live|prod|production)(-|$)", namespace)
    ):
        raise DependencyError("exact seed audit requires an isolated benchmark namespace")
    from infra.analytics_runtime import read_connection

    with read_connection("INVENTORY_AUDIT_DATABASE_URL") as tx, tx.transaction():
        tx.execute("SET LOCAL statement_timeout='5000ms'")
        inventory = tx.execute(
            "SELECT sku FROM inventory WHERE namespace=%s ORDER BY sku", (namespace,)
        ).fetchall()
    with read_connection("CATALOG_AUDIT_DATABASE_URL") as tx, tx.transaction():
        tx.execute("SET LOCAL statement_timeout='5000ms'")
        catalog = tx.execute(
            "SELECT sku FROM products WHERE namespace=%s AND active ORDER BY sku", (namespace,)
        ).fetchall()
        projected = tx.execute(
            "SELECT sku FROM stock_projection WHERE namespace=%s ORDER BY sku", (namespace,)
        ).fetchall()
    return {
        name: [row[0] for row in rows]
        for name, rows in zip(MEMBERSHIPS, (catalog, inventory, projected), strict=True)
    }


def with_seed_membership(callback):
    """Extend an existing reviewed seed callback; never replace its provenance checks."""

    async def audit(context):
        seed = await callback(context)
        if not isinstance(seed, dict):
            raise DependencyError("owner seed callback must return an evidence object")
        membership = await asyncio.to_thread(collect_membership, seed.get("namespace"))
        if any(field in seed and seed[field] != membership[field] for field in MEMBERSHIPS):
            raise DependencyError("owner seed membership conflicts with read-only snapshot")
        return {**seed, **membership}

    return audit
