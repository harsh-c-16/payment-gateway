"""Loopback-only, allowlisted desktop controller. Run with python -m this module.

GET/polling never purchase or replay. Only an explicit confirmed trigger/test can
submit a single saved checkout. Interrupted runs retain evidence and recovery.
"""

import atexit
import copy
import json
import threading
import time
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, StrictBool

from shared.contracts.common import Identifier

from .runtime import ROOT, ResponseLost, Runtime, Unavailable, now, verify_effects

ORIGIN = "http://127.0.0.1:8001"
EVIDENCE = ROOT / "artifacts/failure-demo"
TERMINAL = {"CONFIRMED", "CANCELLED", "MANUAL_REVIEW"}
SCENARIOS = {
    "analytics": "Analytics pause & catch-up",
    "retry": "Duplicate checkout & lost response",
    "decline": "Payment decline & compensation",
    "crash": "Saga crash & restart",
    "late": "Payment after reservation expiry",
    "refund": "Successful debit then reversal",
    "purchase": "End-to-end purchase observation",
}


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Literal["analytics", "retry", "decline", "crash", "late", "refund", "purchase"]
    mode: Literal["manual", "automated"]
    # Only opaque session identity is accepted. URLs, commands, bindings are fixed server-side.
    session_id: UUID | None = None
    run_id: UUID | None = None
    user_id: Identifier | None = None
    correlation_id: UUID | None = None


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: StrictBool = False


class Controller:
    def __init__(self, runtime, evidence=EVIDENCE):
        self.runtime, self.evidence = runtime, Path(evidence)
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.lock, self.state_lock = threading.RLock(), threading.RLock()
        self.stop = threading.Event()
        self.run = None
        self.history = []
        self.tasks = []
        self.lease = None
        self.run_deadline = None
        self.load()

    def load(self):
        path = self.evidence / "current.json"
        if path.is_file():
            self.run = json.loads(path.read_text(encoding="utf-8"))
            if self.run["status"] == "Pending":
                self.run.update(
                    interrupted=True,
                    test_running=False,
                    phase="Interrupted",
                    message=(
                        "Controller restarted. Recover the saved fault; checkout is never "
                        "replayed automatically."
                    ),
                )
        for path in sorted(self.evidence.glob("*/evidence.json"), key=lambda p: p.stat().st_mtime)[
            -15:
        ]:
            run = json.loads(path.read_text(encoding="utf-8"))
            self.history.append(self.summary(run))

    @staticmethod
    def summary(run):
        return {
            k: run.get(k) for k in ("id", "scenario", "mode", "status", "started_at", "order_id")
        }

    def save(self):
        with self.state_lock:
            if not self.run:
                return
            folder = self.evidence / self.run["id"]
            folder.mkdir(exist_ok=True)
            raw = json.dumps(self.run, indent=2)
            for path in (folder / "evidence.json", self.evidence / "current.json"):
                temporary = path.with_suffix(".pending")
                temporary.write_text(raw, encoding="utf-8")
                temporary.replace(path)

    def event(self, phase, text, **facts):
        with self.state_lock:
            self.run["phase"] = phase
            self.run["message"] = text
            self.run["events"].append({"at": now(), "phase": phase, "message": text, **facts})
            self.save()

    def snapshot(self):
        with self.lock, self.state_lock:
            # Saved checkout contains only synthetic public identity; no API credentials.
            return copy.deepcopy(
                {
                    "available": True,
                    "journey_schema": "journey-snapshot-v1",
                    "namespace": self.runtime.namespace,
                    "scenarios": SCENARIOS,
                    "run": self.run,
                    "history": self.history,
                    "observed_at": now(),
                }
            )

    def require(self, run_id):
        if not self.run or self.run["id"] != str(run_id):
            raise HTTPException(409, "The selected run is no longer current")
        return self.run

    def release_lease(self):
        if (
            self.lease
            and (not self.run or self.run["status"] != "Pending")
            and not (self.run and self.run.get("fault_active"))
        ):
            self.lease.close()
            self.lease = None

    def prepare(self, body):
        with self.lock:
            if self.lease is None:
                self.lease = self.runtime.acquire_lease()
            try:
                return self._prepare(body)
            finally:
                self.release_lease()

    def _prepare(self, body):
        with self.lock:
            if self.stop.is_set():
                raise HTTPException(503, "Controller is stopping; restart it before preparing")
            if self.run and (self.run["status"] == "Pending" or self.run.get("fault_active")):
                raise HTTPException(
                    409, "Recover and finish the current run before preparing another"
                )
            if body.mode == "manual" and body.scenario != "analytics":
                raise HTTPException(
                    422,
                    (
                        "Live manual shopping is supported for analytics; use an explicit "
                        "automated test for other cases"
                    ),
                )
            for role in ("store", "catalog", "orders", "inventory", "payments", "analytics"):
                if self.runtime.health(role) is not True:
                    raise Unavailable(f"{role} readiness prerequisite is not met")
            if self.run:
                self.history = (self.history + [self.summary(self.run)])[-15:]
            identity = str(uuid4())
            context = {
                "run_id": identity,
                "user_id": "failure-demo-" + identity[:12],
                "correlation_id": str(uuid4()),
            }
            if body.mode == "manual":
                if not all((body.session_id, body.run_id, body.user_id, body.correlation_id)):
                    raise HTTPException(422, "Open the store in this browser first")
                context.update(
                    session_id=str(body.session_id),
                    run_id=str(body.run_id),
                    user_id=body.user_id,
                    correlation_id=str(body.correlation_id),
                )
                saved = self.runtime.call(
                    "store", "GET", "/v1/sessions/" + context["session_id"], context
                )
            else:
                saved = self.runtime.call(
                    "store", "POST", "/v1/sessions", context, body={}, key=str(uuid4())
                )
                context["session_id"] = saved["session_id"]
            cart_id = saved["cart_id"]
            if body.mode == "manual":
                cart = self.runtime.call("store", "GET", "/v1/carts/" + cart_id, context)
                if not cart["lines"]:
                    raise HTTPException(
                        422,
                        (
                            "Add a product to the store cart before Prepare so independent "
                            "stock baselines can be captured"
                        ),
                    )
                lines = cart["lines"]
                product = None
            else:
                products = self.runtime.call(
                    "store", "GET", "/v1/store/products", context, params={"limit": 12}
                )
                product = next(
                    (p for p in products["items"] if (p.get("stock_available") or 0) > 2), None
                )
                if product is None:
                    raise Unavailable(
                        "No available prepared product in the bounded 12-product page"
                    )
                cart = self.runtime.call(
                    "store",
                    "PUT",
                    f"/v1/carts/{cart_id}/items/{product['sku']}",
                    context,
                    body={"quantity": 1, "expected_cart_version": 0},
                    key=str(uuid4()),
                )
                lines = cart["lines"]
            orders = self.runtime.orders(context)
            baseline = {line["sku"]: self.runtime.stock(context, line["sku"]) for line in lines}
            baseline_at = now()
            # Verify the real target before a mutation can be armed.
            target = self.runtime.container(
                "analytics-worker" if body.scenario == "analytics" else "orders"
            )
            if target["State"]["Paused"] or not target["State"]["Running"]:
                raise Unavailable(
                    "The selected target is already paused/stopped; recover it before preparing"
                )
            self.run_deadline = time.monotonic() + 240
            self.run = {
                "id": identity,
                "scenario": body.scenario,
                "mode": body.mode,
                "context": context,
                "cart_id": cart_id,
                "cart_version": cart["version"],
                "product": {k: product[k] for k in ("sku", "title", "price_minor")}
                if product
                else None,
                "baseline_orders": [r["order_id"] for r in orders],
                "baseline_stock": baseline,
                "started_at": now(),
                "status": "Pending",
                "phase": "Prepare",
                "fault_active": False,
                "triggered": False,
                "recovered": False,
                "order_id": None,
                "order": None,
                "publication": None,
                "events": [],
                "samples": [
                    {
                        "at": baseline_at,
                        "worker_paused": None,
                        "worker_running": None,
                        "analytics_api_ready": None,
                        "order_status": None,
                        "order_version": None,
                        "gold_match": None,
                        "gold_generation": None,
                        "stock_on_hand": sum(s["on_hand"] for s in baseline.values()),
                        "stock_reserved": sum(s["reserved"] for s in baseline.values()),
                        "net_ledger_minor": None,
                    }
                ],
                "checks": [],
                "target_id": target["Id"][:12],
                "limits": {
                    "run_seconds": 240,
                    "sample_seconds": 2,
                    "max_samples": 180,
                    "order_audit_limit": 1000,
                },
                "test_running": False,
            }
            self.event("Prepare", "Baseline captured from owner APIs. No checkout submitted.")
            return self.snapshot()

    def trigger(self, run_id, confirmed):
        with self.lock:
            if self.stop.is_set():
                raise HTTPException(503, "Controller is stopping; no checkout submitted")
            run = self.require(run_id)
            if run["triggered"]:
                raise HTTPException(
                    409, "Trigger is single-use; recovery never starts another purchase"
                )
            if run["status"] != "Pending" or run.get("interrupted"):
                raise HTTPException(409, "Prepare a new run before triggering")
            if run["mode"] == "automated" and confirmed is not True:
                raise HTTPException(
                    422, "Explicit confirmation of one scripted simulated purchase is required"
                )
            run["triggered"] = True  # persist before any uncertain side effect
            run["triggered_at"] = now()
            run["fault_active"] = True
            self.event(
                "Trigger", "Explicit trigger accepted; fault scope saved before service action."
            )
            context = run["context"]
            if run["scenario"] == "analytics":
                self.runtime.process("analytics-worker", "pause")
                if not self.runtime.worker_state()["paused"]:
                    raise Unavailable("Analytics worker pause was not acknowledged")
                self.event(
                    "Observe",
                    "Analytics worker paused. Read API and operational checkout remain separate.",
                )
                if run["mode"] == "manual":
                    self.event(
                        "Observe",
                        (
                            "Place one order in the normal store with its review checkbox. "
                            "Then Watch the order here."
                        ),
                    )
                    return self.snapshot()
            if run["mode"] == "automated":
                plan = run["scenario"] if run["scenario"] in {"decline", "late"} else "success"
                self.runtime.arm("payments", context, plan)
                if run["scenario"] in {"crash", "refund"}:
                    self.runtime.arm("orders", context, run["scenario"])
                try:
                    self.purchase(run)
                except ResponseLost:
                    run["response_lost"] = True
                    self.event(
                        "Observe",
                        (
                            "Injected HTTP 504: the gateway discarded the real committed "
                            "checkout response. Retry the saved request explicitly."
                        ),
                        backend_committed=True,
                        injected_status=504,
                    )
                    raise
                else:
                    self.event(
                        "Observe",
                        (
                            "One explicitly confirmed simulated checkout submitted. Watching "
                            "durable effects."
                        ),
                    )
            return self.snapshot()

    def purchase(self, run):
        context = run["context"]
        quote = self.runtime.call(
            "store",
            "POST",
            f"/v1/carts/{run['cart_id']}/quote",
            context,
            body={"expected_cart_version": run["cart_version"]},
            key=str(uuid4()),
        )
        if quote["total_amount_minor"] != run["product"]["price_minor"]:
            raise Unavailable("Prepared price changed; prepare again before confirming")
        run["quote"] = quote
        run["checkout"] = {
            "path": f"/v1/carts/{run['cart_id']}/checkout",
            "request_id": str(uuid4()),
            "key": str(uuid4()),
            "body": {
                "quote_id": quote["quote_id"],
                "expected_cart_version": run["cart_version"],
                "confirmed": True,
                "confirmation_id": str(uuid4()),
            },
        }
        self.save()  # an interrupted request is retained, never automatically resubmitted
        operation = run["checkout"]
        response = self.runtime.call(
            "store",
            "POST",
            operation["path"],
            context,
            body=operation["body"],
            key=operation["key"],
            request_id=operation["request_id"],
        )
        run["order_id"] = response["order_id"]
        run["commit_ack"] = {"at": now(), "status": 202, "order_id": response["order_id"]}
        self.save()
        if run["scenario"] == "retry":
            # Fail at the server gateway boundary. Neither HTTP nor CLI caller
            # receives checkout success; its committed effect is retained.
            raise ResponseLost("Injected gateway timeout after committed checkout")

    def watch(self, run_id, order_id):
        with self.lock:
            run = self.require(run_id)
            if not run["triggered"] or run["mode"] != "manual" or run["scenario"] != "analytics":
                raise HTTPException(409, "Watch is for the triggered live analytics demonstration")
            order = self.runtime.call(
                "store", "GET", "/v1/store/orders/" + str(order_id), run["context"]
            )
            if order["order_id"] in run["baseline_orders"]:
                raise HTTPException(409, "Select the new order placed after this baseline")
            if run["order_id"] and run["order_id"] != str(order_id):
                raise HTTPException(409, "This run already watches another order")
            if any(line["sku"] not in run["baseline_stock"] for line in order["lines"]):
                raise HTTPException(
                    409,
                    (
                        "Order contains a SKU without a captured baseline; recover and "
                        "prepare its cart first"
                    ),
                )
            run["order_id"] = str(order_id)
            self.event("Observe", "Exact owned order selected; observation never retries checkout.")
        self.observe()
        return self.snapshot()

    def recover(self, run_id, *, replay=False):
        with self.lock:
            run = self.require(run_id)
            if self.lease is None and (run["status"] == "Pending" or run.get("fault_active")):
                self.lease = self.runtime.acquire_lease()
            if run["scenario"] == "retry" and replay:
                if run["status"] != "Pending":
                    raise HTTPException(
                        409, "This run is complete; prepare a new retry demonstration"
                    )
                if not run.get("checkout") or not run.get("response_lost"):
                    raise HTTPException(409, "No committed saved checkout to retry")
                operation = run["checkout"]
                response = self.runtime.call(
                    "store",
                    "POST",
                    operation["path"],
                    run["context"],
                    body=operation["body"],
                    key=operation["key"],
                    request_id=operation["request_id"],
                )
                run["retry_same_order"] = response["order_id"] == run["commit_ack"]["order_id"]
                run["retry_ack"] = {
                    "at": now(),
                    "order_id": response["order_id"],
                    "same_request_id": True,
                    "same_key": True,
                    "same_body": True,
                }
                self.event(
                    "Recover",
                    "Original request ID, idempotency key and body replayed to real checkout.",
                )
            if run["scenario"] == "analytics" and run["triggered"]:
                self.runtime.process("analytics-worker", "unpause")
                state = self.runtime.worker_state()
                if state["paused"] or state["container_id"] != run["target_id"]:
                    raise Unavailable("Retained analytics-worker recovery not established")
            if run["scenario"] == "crash" and run["triggered"]:
                try:
                    marker = self.runtime.checkpoint(run["context"]["run_id"])
                except Unavailable:
                    # Recovery must still start the validated project process if
                    # the intended checkpoint was never acknowledged. It cannot pass.
                    marker = None
                    run["checkpoint_error"] = "No acknowledged saga.after_commit marker"
                if marker:
                    run["checkpoint"] = marker
                self.runtime.process("orders", "start")
                deadline = time.monotonic() + 25
                while self.runtime.health("orders") is not True and time.monotonic() < deadline:
                    time.sleep(0.5)
                if self.runtime.health("orders") is not True:
                    raise Unavailable("Orders restart readiness not established")
                if self.runtime.container("orders")["Id"][:12] != run["target_id"]:
                    raise Unavailable("Orders container changed during recovery")
            if run["triggered"] and run["mode"] == "automated":
                for role in (
                    ["orders", "payments"]
                    if run["scenario"] in {"crash", "refund"}
                    else ["payments"]
                ):
                    self.runtime.clear(role, run["context"])
            run.update(fault_active=False, recovered=True, recovered_at=now())
            if run.get("interrupted") or not run["triggered"] or not run.get("order_id"):
                run["status"] = "Failed"
                self.event(
                    "Recover",
                    "Interrupted or unused run recovered. No purchase replayed; prepare a new run.",
                )
            else:
                self.event(
                    "Recover",
                    "Fault removed and altered controls cleared. Observe catch-up, then Verify.",
                )
            self.release_lease()
            return self.snapshot()

    def observe(self):
        with self.lock:
            run = self.run
            if not run or not run["triggered"] or run["status"] != "Pending":
                return
            context = run["context"]
            worker = self.runtime.worker_state()
            api_ready = self.runtime.health("analytics")
            if run["scenario"] == "crash" and not run.get("checkpoint"):
                marker = self.runtime.checkpoint(context["run_id"])
                if marker:
                    run["checkpoint"] = marker
                    self.event(
                        "Observe",
                        (
                            "Checkpoint acknowledged: saga.after_commit. Orders process exited "
                            "86 after stock commit, before durable step advancement."
                        ),
                        checkpoint=marker,
                    )
            order = None
            if run.get("order_id"):
                order = self.runtime.call(
                    "store", "GET", "/v1/store/orders/" + run["order_id"], context, optional=True
                )
            if order:
                run["order"] = order
                if not run.get("immutable"):
                    run["immutable"] = {
                        k: order[k]
                        for k in (
                            "order_id",
                            "quote_id",
                            "session_id",
                            "user_id",
                            "currency",
                            "total_amount_minor",
                        )
                    }
                publication = self.runtime.call(
                    "store",
                    "GET",
                    "/v1/store/orders/" + run["order_id"] + "/pipeline",
                    context,
                    optional=True,
                )
                run["publication"] = publication
                run["audit"] = self.runtime.audit(context, order)
                if run["scenario"] == "refund":
                    entries = run["audit"]["ledger"]
                    if (
                        entries
                        and sum(e["kind"] == "DEBIT" for e in entries) == 1
                        and not any(e["kind"] == "REVERSAL" for e in entries)
                    ):
                        if not run.get("debit_observed"):
                            run["debit_observed"] = {"at": now(), "entries": entries}
                            self.event(
                                "Observe",
                                "Real debit observed; reservation held before stock commit.",
                            )
                if order["status"] in TERMINAL:
                    run["current_orders"] = self.runtime.orders(context)
                if (
                    worker["paused"]
                    and api_ready is True
                    and order["status"] in TERMINAL
                    and publication
                    and publication["status"] == "pending"
                ):
                    if not run.get("pending_proof"):
                        self.event(
                            "Observe",
                            (
                                "Measured: terminal checkout while analytics worker is paused; "
                                "exact Gold publication remains pending."
                            ),
                            order_id=order["order_id"],
                            order_version=order["order_version"],
                        )
                    run["pending_proof"] = True
                if run["scenario"] == "late":
                    self.observe_late(run)
            sample = {
                "at": now(),
                "worker_paused": worker["paused"],
                "worker_running": worker["running"],
                "analytics_api_ready": api_ready,
                "order_status": order["status"] if order else None,
                "order_version": order["order_version"] if order else None,
                "gold_match": (
                    run["publication"]["status"] == "visible"
                    and run["publication"]["order_version"] == order["order_version"]
                )
                if order and run["publication"] and run["publication"]["status"] != "unavailable"
                else None,
                "gold_generation": run["publication"].get("generation")
                if run.get("publication")
                else None,
                "stock_on_hand": None,
                "stock_reserved": None,
                "net_ledger_minor": None,
            }
            if run.get("audit") and order:
                audit = run["audit"]
                sample["stock_on_hand"] = sum(s["on_hand"] for s in audit["stocks"].values())
                sample["stock_reserved"] = sum(s["reserved"] for s in audit["stocks"].values())
                sample["net_ledger_minor"] = (
                    sum(
                        e["amount_minor"] * (1 if e["kind"] == "DEBIT" else -1)
                        for e in audit["ledger"]
                    )
                    if audit["ledger"] is not None
                    else None
                )
            run["samples"] = (run["samples"] + [sample])[-180:]
            self.save()

    def observe_late(self, run):
        context = run["context"]
        reservation = self.runtime.call(
            "inventory",
            "GET",
            "/internal/v1/reservations/by-order/" + run["order_id"],
            context,
            optional=True,
        )
        schedule = self.runtime.call(
            "payments",
            "GET",
            "/internal/v1/demo-audit/" + context["run_id"],
            context,
            optional=True,
        )
        attempts = (
            [row for row in schedule["items"] if row["order_id"] == run["order_id"]]
            if schedule
            else []
        )
        if len(attempts) != 1 or not reservation:
            return
        plan = attempts[0]
        run["payment_schedule"] = plan
        created = datetime.fromisoformat(plan["created_at"].replace("Z", "+00:00"))
        due = datetime.fromisoformat(plan["completion_due_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(reservation["expires_at"].replace("Z", "+00:00"))
        observed = datetime.now(UTC)
        run["payment_delay_ms"] = round((due - created).total_seconds() * 1000)
        run["payment_due_after_expiry_ms"] = round((due - expires).total_seconds() * 1000)
        if (
            reservation["state"] in {"EXPIRED", "RELEASED"}
            and observed >= expires
            and run["order"]["failure_code"] == "RESERVATION_EXPIRED"
        ):
            if observed < due:
                run["expiry_proof"] = True
            if not run.get("expiry_at"):
                run["expiry_at"] = now()
                run["reservation_expires_at"] = reservation["expires_at"]
                self.event(
                    "Observe",
                    "Reservation expired. Saga quiesces the pending callback and releases stock.",
                )
        run["late_due_observed"] = (observed - due).total_seconds() >= 1

    def verify(self, run_id):
        run = self.require(run_id)
        if run["status"] != "Pending":
            return self.snapshot()  # retain completed evidence and its original timestamp
        self.observe()
        with self.lock:
            run = self.require(run_id)
            run["checks"] = verify_effects(run)
            values = [c["passed"] for c in run["checks"]]
            terminal = run.get("order", {}).get("status") if run.get("order") else None
            waiting = (
                terminal not in TERMINAL
                or (run.get("publication") or {}).get("status") == "pending"
            )
            waiting |= run["scenario"] == "late" and not run.get("late_due_observed")
            waiting |= run["scenario"] == "retry" and not run.get("retry_ack")
            waiting |= bool(run.get("fault_active"))
            if terminal == "MANUAL_REVIEW":
                waiting = False
            if waiting:
                run["status"] = "Pending"
                message = (
                    "Verification pending: complete recovery and wait for terminal "
                    "effects and exact active Gold."
                )
            else:
                run["status"] = (
                    "Passed"
                    if all(v is True for v in values)
                    else "Unavailable"
                    if None in values and False not in values
                    else "Failed"
                )
                incomplete = [c["name"] for c in run["checks"] if c["passed"] is not True]
                message = (
                    "Independent verification passed against real owner APIs."
                    if run["status"] == "Passed"
                    else (
                        "Measurements unavailable: "
                        if run["status"] == "Unavailable"
                        else "Verification failed: "
                    )
                    + "; ".join(incomplete)
                )
                run["completed_at"] = now()
            self.event("Verify", message)
            self.release_lease()
            return self.snapshot()

    def fail(self, message, status="Failed"):
        with self.lock:
            if not self.run:
                return
            identity = self.run["id"]
            try:
                self.recover(identity)
            except (Unavailable, HTTPException):
                self.run["fault_active"] = True
                message += " Recovery is incomplete; use Recover after services return."
            self.run["status"] = status
            self.run["test_running"] = False
            self.event("Verify", message)
            self.release_lease()

    def automate(self, run_id):
        try:
            try:
                self.trigger(run_id, True)
            except ResponseLost:
                pass  # expected fault; the saved-request recovery stage retries
            deadline = time.monotonic() + 165
            while time.monotonic() < deadline and not self.stop.is_set():
                self.observe()
                run = self.require(run_id)
                if run["scenario"] == "retry" and not run.get("retry_ack"):
                    self.recover(run_id, replay=True)
                elif (
                    run["scenario"] == "analytics"
                    and run.get("pending_proof")
                    or run["scenario"] == "crash"
                    and run.get("checkpoint")
                ) and not run["recovered"]:
                    self.recover(run_id)
                order = run.get("order")
                if order and order["status"] in TERMINAL:
                    if run["fault_active"] and run["scenario"] in {
                        "decline",
                        "late",
                        "refund",
                        "purchase",
                    }:
                        self.recover(run_id)
                    result = self.verify(run_id)["run"]
                    if result["status"] != "Pending":
                        break
                time.sleep(1)
            else:
                raise Unavailable("Automated test exceeded its 165-second observation bound")
        except (Unavailable, HTTPException, KeyError, ValueError) as exc:
            self.fail(str(exc), "Unavailable" if isinstance(exc, Unavailable) else "Failed")
        finally:
            with self.lock:
                self.run["test_running"] = False
                self.save()

    def start_test(self, run_id, confirmed):
        with self.lock:
            run = self.require(run_id)
            if (
                not confirmed
                or run["mode"] != "automated"
                or run["triggered"]
                or run["test_running"]
            ):
                raise HTTPException(
                    409,
                    "Prepare an automated run and explicitly confirm its one simulated purchase",
                )
            run["test_running"] = True
            self.save()
            task = threading.Thread(target=self.automate, args=(run_id,), daemon=True)
            self.tasks.append(task)
            task.start()
        return self.snapshot()

    def monitor(self):
        while not self.stop.wait(2):
            try:
                run = self.run
                if not run or run["status"] != "Pending" or run.get("interrupted"):
                    continue
                if self.run_deadline is not None and time.monotonic() > self.run_deadline:
                    self.fail(
                        "Run exceeded 240 seconds; recovery attempted. No request was replayed."
                    )
                elif not run["test_running"]:
                    self.observe()
            except (Unavailable, HTTPException, KeyError, ValueError) as exc:
                if self.run:
                    self.run["observation_error"] = str(exc)
                    self.save()

    def shutdown(self):
        self.stop.set()
        if self.run and (self.run.get("fault_active") or self.run["status"] == "Pending"):
            self.fail("Controller stopped; automatic recovery attempted. Run remains incomplete.")


def create_app(runtime=None, evidence=EVIDENCE):
    controller = Controller(runtime or Runtime(), evidence)
    from benchmarks.windows.infrastructure import Infrastructure

    infrastructure = Infrastructure(controller.runtime.namespace)
    from benchmarks.journey.api import install

    @asynccontextmanager
    async def lifespan(app):
        observer = threading.Thread(target=controller.monitor, daemon=True)
        observer.start()
        recording_monitor = threading.Thread(target=recordings.monitor, daemon=True)
        recording_monitor.start()
        yield
        recordings.shutdown()
        edge_lab.shutdown()
        controller.shutdown()
        recording_monitor.join(timeout=2)

    app = FastAPI(title="Local failure demo controller", lifespan=lifespan)
    app.state.controller = controller
    recordings, edge_lab = install(app, controller, infrastructure)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[ORIGIN],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
        expose_headers=["Content-Disposition"],
    )

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        if (
            request.client.host not in {"127.0.0.1", "::1", "testclient"}
            or request.headers.get("host") not in {"127.0.0.1:8010", "testserver"}
            or request.headers.get("origin") != ORIGIN
        ):
            return JSONResponse(
                {"detail": "Local dashboard origin and loopback host required"}, status_code=403
            )
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(Unavailable)
    async def unavailable(request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.get("/state")
    def state():
        return controller.snapshot()

    @app.get("/infrastructure")
    def infrastructure_snapshot():
        return infrastructure.snapshot()

    @app.post("/shutdown")
    def shutdown():
        controller.shutdown()
        return {"recovered": not controller.run or not controller.run.get("fault_active")}

    @app.post("/prepare")
    def prepare(body: Selection):
        return controller.prepare(body)

    @app.post("/runs/{run_id}/{action}")
    def action(
        run_id: UUID, action: Literal["trigger", "recover", "retry", "verify", "test"], body: Action
    ):
        if action == "trigger":
            try:
                result = controller.trigger(run_id, body.confirmed)
            except ResponseLost:
                return JSONResponse(
                    {
                        "detail": "Injected response loss after backend commit. "
                        "Use Retry identical request."
                    },
                    status_code=504,
                )
            except Unavailable as exc:
                controller.fail(str(exc), "Unavailable")
                raise
            return result
        if action == "recover":
            return controller.recover(run_id)
        if action == "retry":
            return controller.recover(run_id, replay=True)
        if action == "test":
            return controller.start_test(run_id, body.confirmed)
        return controller.verify(run_id)

    @app.post("/runs/{run_id}/watch/{order_id}")
    def watch(run_id: UUID, order_id: UUID):
        return controller.watch(run_id, order_id)

    @app.get("/evidence/{run_id}")
    def evidence_file(run_id: UUID):
        path = controller.evidence / str(run_id) / "evidence.json"
        if not path.is_file():
            raise HTTPException(404, "Evidence not found")
        return FileResponse(
            path, filename=f"failure-demo-{run_id}.json", media_type="application/json"
        )

    atexit.register(controller.shutdown)
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8010, access_log=False)
