"""Projectctl inventory-seed adapter. Owner: Aditya."""

import json
import os
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from projectctl.models import ExitCode
from projectctl.providers import ProviderResult
from services.inventory.database import Database
from services.inventory.errors import ServiceError
from services.inventory.events import InventoryEvents
from services.inventory.seed import seed_inventory
from shared.contracts.common import RequestContext


def inventory_seed(invocation):
    arguments = invocation.arguments
    profile = arguments.get("profile", "performance")
    if profile not in {"performance", "test"} or (
        profile == "test" and not invocation.namespace.startswith("bench-")
    ):
        return ProviderResult(ExitCode.BAD_INPUT, ("Invalid inventory seed profile.",), "real")
    try:
        manifest = json.loads(Path(arguments["sku_manifest"]).read_text(encoding="utf-8"))
    except (KeyError, OSError, ValueError, TypeError) as error:
        return ProviderResult(ExitCode.BAD_INPUT, (type(error).__name__,), "real")
    url = os.environ.get("INVENTORY_DATABASE_URL")
    if not url:
        return ProviderResult(
            ExitCode.DEPENDENCY_FAILURE, ("INVENTORY_DATABASE_URL is required.",), "real"
        )
    try:
        identity = str(uuid4())
        context = RequestContext(
            namespace=invocation.namespace,
            run_id=invocation.run_id,
            user_id="projectctl",
            correlation_id=identity,
            request_id=identity,
            session_id=None,
        )
        report = seed_inventory(
            Database(url, max_connections=4),
            invocation.namespace,
            manifest,
            events=InventoryEvents(),
            context=context,
            seed=arguments.get("seed", 42),
            default_on_hand=10_000 if profile == "performance" else 1,
        )
    except ValidationError:
        return ProviderResult(
            ExitCode.BAD_INPUT, ("Invalid seed manifest or request context.",), "real"
        )
    except ValueError as error:
        return ProviderResult(ExitCode.BAD_INPUT, (str(error),), "real")
    except ServiceError as error:
        return ProviderResult(
            ExitCode.DEPENDENCY_FAILURE if error.status == 503 else ExitCode.CORRECTNESS_FAILURE,
            (str(error.body.code),),
            "real",
        )
    return ProviderResult(ExitCode.COMPLETED, (json.dumps(report, sort_keys=True),), "real")


def register(registry):
    registry.register("inventory seed", inventory_seed)
