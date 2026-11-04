"""Projectctl adapter for inventory seed and audit commands. Owner: Aditya."""

import json
import logging
import os

from projectctl.models import ExitCode
from projectctl.providers import Invocation, ProviderResult

logger = logging.getLogger("inventory.adapter")


def inventory_seed(invocation: Invocation) -> ProviderResult:
    """Seed inventory from a SKU manifest file. Projectctl entry point."""
    ns = invocation.namespace
    args = invocation.arguments
    manifest_path = args.get("sku_manifest")
    profile = args.get("profile", "performance")
    seed_value = args.get("seed", 42)

    if not manifest_path or not os.path.isfile(manifest_path):
        return ProviderResult(
            code=ExitCode.DEPENDENCY_ERROR,
            reasons=(f"SKU manifest not found: {manifest_path}",),
            test_mode="offline",
        )

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as exc:
        return ProviderResult(
            code=ExitCode.DEPENDENCY_ERROR,
            reasons=(f"Failed to load manifest: {exc}",),
            test_mode="offline",
        )

    skus = manifest.get("active_skus", [])
    if not skus:
        return ProviderResult(
            code=ExitCode.DEPENDENCY_ERROR,
            reasons=("Manifest contains no active SKUs.",),
            test_mode="offline",
        )

    db_url = os.environ.get("INVENTORY_DATABASE_URL")
    if not db_url:
        return ProviderResult(
            code=ExitCode.DEPENDENCY_ERROR,
            reasons=("INVENTORY_DATABASE_URL not set.",),
            test_mode="offline",
        )

    try:
        from services.inventory.database import Database
        from services.inventory.events import InventoryEvents
        from services.inventory.seed import seed_inventory

        from shared.contracts.common import RequestContext

        db = Database(db_url, max_connections=4)
        events = InventoryEvents()
        context = RequestContext(
            namespace=ns,
            run_id=invocation.run_id,
            user_id="projectctl",
            correlation_id=invocation.run_id,
            request_id=invocation.run_id,
        )

        on_hand = 10_000 if profile == "performance" else 1
        manifest_hash = manifest.get("digest", manifest.get("hash", "unknown"))

        result = seed_inventory(
            db, events, ns, skus, manifest_hash,
            on_hand=on_hand,
            context=context,
        )

        return ProviderResult(
            code=ExitCode.PASS,
            reasons=(
                f"Seeded {result.get('seeded_count', len(skus))} SKUs with on_hand={on_hand}",
                f"Manifest hash: {manifest_hash}",
            ),
            test_mode="real",
        )
    except Exception as exc:
        logger.exception("inventory seed failed")
        return ProviderResult(
            code=ExitCode.ERROR,
            reasons=(f"Seed failed: {type(exc).__name__}: {exc}",),
            test_mode="real",
        )


def register(registry):
    """Register inventory adapters with the projectctl provider registry."""
    registry.register("inventory seed", inventory_seed)
