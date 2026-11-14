"""Explicit local desktop hooks. No benchmark policy or ordinary payment changes.

The host controller arms one expiring run through authenticated owner APIs. Files
survive a process/container restart; business recovery still uses the owner's DB.
Never enable this opt-in feature in a public deployment.
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict

from shared.contracts.common import Identifier


class DemoControl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    run_id: UUID
    namespace: Identifier
    scenario: Literal["success", "decline", "late", "crash", "refund"]
    expires_at: datetime


def directory(role):
    if role not in {"orders", "payments"}:
        raise ValueError("Unsupported demo owner")
    return Path(os.environ.get("LOCAL_DEMO_CONTROL_ROOT", "/tmp/shoptalk-failure-demo")) / role


def read_control(role, run_id, namespace=None):
    if os.environ.get("LOCAL_FAILURE_DEMOS_ENABLED") != "true":
        return None
    try:
        path = directory(role) / (str(UUID(str(run_id))) + ".json")
        value = json.loads(path.read_text(encoding="utf-8"))
        if datetime.fromisoformat(value["expires_at"]) > datetime.now(UTC) and (
            namespace is None or value.get("namespace") == namespace
        ):
            return value
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def install_routes(app, *, role, dependencies):
    """Token checks belong to the service; fail closed unless explicitly enabled."""

    @app.post("/internal/v1/demo-control", dependencies=dependencies)
    def arm_demo(body: DemoControl, request: Request):
        if os.environ.get("LOCAL_FAILURE_DEMOS_ENABLED") != "true":
            raise HTTPException(403, "Local failure demos are disabled")
        if request.headers.get("X-Namespace") != body.namespace or request.headers.get(
            "X-Run-ID"
        ) != str(body.run_id):
            raise HTTPException(409, "Local demo context differs from its selected run")
        seconds = (
            (body.expires_at - datetime.now(UTC)).total_seconds() if body.expires_at.tzinfo else -1
        )
        if not 0 < seconds <= 300 or (
            role == "orders" and body.scenario not in {"crash", "refund"}
        ):
            raise HTTPException(422, "Unsupported plan or expiry (maximum 300 seconds)")
        folder = directory(role)
        folder.mkdir(parents=True, exist_ok=True)
        for path in folder.glob("*.json"):
            if read_control(role, path.stem) and path.stem != str(body.run_id):
                raise HTTPException(409, "Another local demo is armed")
        path = folder / (str(body.run_id) + ".json")
        value = body.model_dump(mode="json")
        if not path.exists():
            with path.open("x", encoding="utf-8") as stream:
                json.dump(value, stream)
        else:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if any(existing[k] != value[k] for k in ("run_id", "namespace", "scenario")):
                raise HTTPException(409, "Run identity already used")
        return value

    @app.delete("/internal/v1/demo-control/{run_id}", dependencies=dependencies)
    def clear_demo(run_id: UUID):
        directory(role).joinpath(str(run_id) + ".json").unlink(missing_ok=True)
        return {"cleared": True}


def crash_after_commit(context, order_id, status_code):
    control = read_control("orders", context.run_id, context.namespace)
    if not control or control["scenario"] != "crash" or status_code != 200:
        return
    marker = directory("orders") / (str(UUID(context.run_id)) + ".checkpoint")
    if marker.exists():
        return  # one crash per run, including restarts with an interrupted controller
    value = {
        "run_id": context.run_id,
        "order_id": order_id,
        "checkpoint": "saga.after_commit",
        "inventory_http_status": status_code,
        "observed_at": datetime.now(UTC).isoformat(),
    }
    with marker.open("x", encoding="utf-8") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os._exit(86)  # exact boundary: stock committed, saga advancement not yet persisted


def refund_hold_until(context, expires_at):
    """Scoped pre-stock-commit barrier; the real debit already exists at this step.

    Recomputed from the owner's immutable reservation deadline after restart.
    No SQL state is fabricated, no worker sleeps and unrelated orders keep running.
    """
    control = read_control("orders", context.run_id, context.namespace)
    if not control or control["scenario"] != "refund":
        return None
    from datetime import timedelta

    deadline = datetime.fromisoformat(expires_at.replace("Z", "+00:00")) + timedelta(seconds=2)
    return deadline if datetime.now(UTC) < deadline else None
