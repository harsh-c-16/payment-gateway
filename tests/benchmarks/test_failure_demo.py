"""Explicit controller/owner doubles; these are not real-service integration claims."""

import copy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from benchmarks.failure_demo.controller import ORIGIN, Controller, Selection, create_app
from benchmarks.failure_demo.runtime import Runtime, Unavailable, verify_effects
from shared.local_diagnostics import demo_controls as hooks


class OwnerDouble:
    namespace = "dev"

    def __init__(self):
        self.calls = []

    def health(self, role):
        return True

    def acquire_lease(self):
        return SimpleNamespace(close=lambda: None)

    def container(self, role):
        return {"Id": "a" * 64, "State": {"Paused": False, "Running": True}}

    def orders(self, context):
        return []

    def stock(self, context, sku):
        return {"sku": sku, "on_hand": 10, "reserved": 0, "stock_version": 1}

    def call(self, role, method, path, context, **kwargs):
        self.calls.append((role, method, path, kwargs))
        if path == "/v1/sessions":
            return {"session_id": str(uuid4()), "cart_id": str(uuid4())}
        if path == "/v1/store/products":
            return {
                "items": [
                    {"sku": "SKU", "title": "Double", "price_minor": 100, "stock_available": 10}
                ]
            }
        if "/items/" in path:
            return {"version": 1, "lines": [{"sku": "SKU", "quantity": 1}]}
        raise AssertionError("Unexpected double call " + path)


@pytest.fixture
def correct_run():
    order = {
        "order_id": "order",
        "status": "CONFIRMED",
        "order_version": 6,
        "session_id": "session",
        "user_id": "user",
        "total_amount_minor": 1200,
        "currency": "INR",
        "quote_id": "quote",
        "lines": [{"sku": "SKU", "quantity": 1}],
    }
    return {
        "scenario": "retry",
        "context": {"user_id": "user", "session_id": "session"},
        "order": order,
        "current_orders": [order],
        "baseline_orders": [],
        "immutable": {"quote_id": "quote", "total_amount_minor": 1200},
        "baseline_stock": {"SKU": {"on_hand": 10, "reserved": 0, "stock_version": 1}},
        "audit": {
            "reservation": {"state": "COMMITTED"},
            "payments": {"attempts": [{"status": "SUCCESS"}]},
            "ledger": [{"kind": "DEBIT", "amount_minor": 1200, "currency": "INR"}],
            "stocks": {"SKU": {"on_hand": 9, "reserved": 0, "stock_version": 3}},
        },
        "publication": {"status": "visible", "order_version": 6},
        "response_lost": True,
        "retry_same_order": True,
    }


def test_independent_oracle_accepts_reconciled_effects(correct_run):
    assert all(c["passed"] is True for c in verify_effects(correct_run))


@pytest.mark.parametrize("corruption", ["debit", "stock", "version", "identity", "order", "review"])
def test_independent_oracle_detects_corruption(correct_run, corruption):
    run = copy.deepcopy(correct_run)
    if corruption == "debit":
        run["audit"]["ledger"] *= 2
    elif corruption == "stock":
        run["audit"]["stocks"]["SKU"]["stock_version"] += 1
    elif corruption == "version":
        run["publication"]["order_version"] = 5
    elif corruption == "identity":
        run["order"]["quote_id"] = "another-quote"
    elif corruption == "order":
        run["current_orders"].append({**run["order"], "order_id": "duplicate-purchase"})
    elif corruption == "review":
        run["order"]["status"] = "MANUAL_REVIEW"
    assert any(c["passed"] is False for c in verify_effects(run))


def test_missing_measurements_stay_null(correct_run):
    correct_run["audit"]["ledger"] = None
    correct_run["audit"]["reservation"] = None
    correct_run["publication"] = {"status": "unavailable", "order_version": 6}
    checks = verify_effects(correct_run)
    assert next(c for c in checks if c["name"] == "Signed net ledger amount")["observed"] is None
    assert next(c for c in checks if c["name"].startswith("Reservation has"))["observed"] is None
    assert next(c for c in checks if c["name"].startswith("Exact active Gold"))["passed"] is None


@pytest.mark.parametrize("debited", [False, True])
def test_late_payment_allows_no_debit_or_one_matching_refund(correct_run, debited):
    run = correct_run
    run.update(
        scenario="late",
        payment_delay_ms=35000,
        payment_due_after_expiry_ms=5000,
        expiry_proof=True,
        late_due_observed=True,
    )
    run["order"]["status"] = "CANCELLED"
    run["audit"]["reservation"]["state"] = "EXPIRED"
    run["audit"]["stocks"]["SKU"]["on_hand"] = 10
    run["audit"]["payments"] = {
        "quiesced": True,
        "attempts": [{"status": "REVERSED" if debited else "CANCELLED"}],
    }
    run["audit"]["ledger"] = (
        [
            {"payment_id": "payment", "kind": kind, "currency": "INR", "amount_minor": 1200}
            for kind in ("DEBIT", "REVERSAL")
        ]
        if debited
        else []
    )
    assert all(c["passed"] is True for c in verify_effects(run))
    if debited:
        run["audit"]["ledger"][1]["payment_id"] = "wrong-payment"
        assert any(c["passed"] is False for c in verify_effects(run))


def test_prepare_observe_and_recover_never_purchase_or_overlap(tmp_path):
    runtime = OwnerDouble()
    controller = Controller(runtime, tmp_path)
    run = controller.prepare(Selection(scenario="retry", mode="automated"))["run"]
    assert not any(call[2].endswith("/checkout") for call in runtime.calls)
    for _ in range(3):
        controller.snapshot()
        controller.observe()
    with pytest.raises(HTTPException) as exc:
        controller.prepare(Selection(scenario="decline", mode="automated"))
    assert exc.value.status_code == 409
    with pytest.raises(HTTPException):
        controller.trigger(run["id"], False)
    assert controller.run["triggered"] is False
    controller.recover(run["id"])
    assert controller.run["status"] == "Failed"
    assert not any(call[2].endswith("/checkout") for call in runtime.calls)


def test_interrupted_controller_never_replays_saved_checkout(tmp_path):
    runtime = OwnerDouble()
    first = Controller(runtime, tmp_path)
    first.prepare(Selection(scenario="retry", mode="automated"))
    first.run["checkout"] = {"path": "/v1/carts/saved/checkout"}
    first.run["test_running"] = True
    first.save()
    restarted = Controller(runtime, tmp_path)
    assert restarted.run["interrupted"] is True
    assert restarted.run["test_running"] is False
    assert len(runtime.calls) == 3
    assert not any(call[2].endswith("/checkout") for call in runtime.calls)


def test_run_timeout_recovers_without_purchase_using_monotonic_deadline(tmp_path, monkeypatch):
    runtime = OwnerDouble()
    controller = Controller(runtime, tmp_path)
    controller.prepare(Selection(scenario="retry", mode="automated"))
    controller.run_deadline = -1
    ticks = iter([False, True])
    controller.stop = SimpleNamespace(wait=lambda _: next(ticks))
    monkeypatch.setattr("benchmarks.failure_demo.controller.time.monotonic", lambda: 1)
    controller.monitor()
    assert controller.run["status"] == "Failed"
    assert controller.run["recovered"] is True
    assert not any(call[2].endswith("/checkout") for call in runtime.calls)


@pytest.mark.parametrize(
    "headers",
    [{}, {"Origin": "https://attacker.example"}, {"Origin": ORIGIN, "Host": "attacker.example"}],
)
def test_controller_refuses_cross_origin_or_rebinding(tmp_path, headers):
    with TestClient(create_app(OwnerDouble(), tmp_path)) as client:
        assert client.get("/state", headers=headers).status_code == 403


def test_controller_refuses_arbitrary_actions_and_coerced_confirmation(tmp_path):
    with TestClient(create_app(OwnerDouble(), tmp_path)) as client:
        headers = {"Origin": ORIGIN}
        assert client.get("/state", headers=headers).status_code == 200
        assert (
            client.post(
                "/prepare",
                headers=headers,
                json={"scenario": "analytics", "mode": "automated", "command": "docker stop"},
            ).status_code
            == 422
        )


def test_gateway_discards_committed_response_then_retries_identical_operation(tmp_path):
    class CheckoutDouble(OwnerDouble):
        def arm(self, *args):
            pass

        def clear(self, *args):
            pass

        def call(self, role, method, path, context, **kwargs):
            if path.endswith("/quote") or path.endswith("/checkout"):
                self.calls.append((role, method, path, kwargs))
                return (
                    {"quote_id": str(uuid4()), "total_amount_minor": 100}
                    if path.endswith("/quote")
                    else {"order_id": "committed-order"}
                )
            return super().call(role, method, path, context, **kwargs)

    runtime = CheckoutDouble()
    with TestClient(create_app(runtime, tmp_path)) as client:
        headers = {"Origin": ORIGIN}
        run = client.post(
            "/prepare", json={"scenario": "retry", "mode": "automated"}, headers=headers
        ).json()["run"]
        path = "/runs/" + run["id"]
        lost = client.post(path + "/trigger", json={"confirmed": True}, headers=headers)
        assert lost.status_code == 504 and "order_id" not in lost.json()
        saved = client.get("/state", headers=headers).json()["run"]
        assert saved["commit_ack"]["order_id"] == "committed-order"
        assert saved["response_lost"] is True
        assert client.post(path + "/retry", json={}, headers=headers).status_code == 200
        purchases = [c for c in runtime.calls if c[2].endswith("/checkout")]
        assert len(purchases) == 2 and purchases[0] == purchases[1]
        assert client.get("/state", headers=headers).json()["run"]["retry_same_order"] is True
        identity = str(uuid4())
        assert client.post(f"/runs/{identity}/shell", headers=headers, json={}).status_code == 422
        assert (
            client.post(
                f"/runs/{identity}/trigger", headers=headers, json={"confirmed": "true"}
            ).status_code
            == 422
        )


def test_docker_actions_are_allowlisted_before_execution():
    runtime = Runtime.__new__(Runtime)
    with pytest.raises(Unavailable):
        runtime.process("postgres", "stop")
    with pytest.raises(Unavailable):
        runtime.container("kafka")


@pytest.fixture
def hook_client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_DEMO_CONTROL_ROOT", str(tmp_path))
    monkeypatch.setenv("LOCAL_FAILURE_DEMOS_ENABLED", "true")
    app = FastAPI()
    hooks.install_routes(app, role="orders", dependencies=[])
    return TestClient(app)


def arm(client, run_id=None, **overrides):
    identity = run_id or str(uuid4())
    body = {
        "namespace": "dev",
        "run_id": identity,
        "scenario": "crash",
        "expires_at": (datetime.now(UTC) + timedelta(seconds=60)).isoformat(),
        **overrides,
    }
    return client.post(
        "/internal/v1/demo-control", json=body, headers={"X-Namespace": "dev", "X-Run-ID": identity}
    )


def test_hooks_are_disabled_by_default(hook_client, monkeypatch):
    monkeypatch.delenv("LOCAL_FAILURE_DEMOS_ENABLED")
    assert arm(hook_client).status_code == 403


def test_hooks_scope_expiry_overlap_and_one_crash_checkpoint(hook_client, monkeypatch):
    identity = str(uuid4())
    assert arm(hook_client, identity).status_code == 200
    assert arm(hook_client).status_code == 409
    assert hooks.read_control("orders", identity, "another-namespace") is None
    assert hooks.read_control("orders", str(uuid4()), "dev") is None
    assert arm(hook_client, identity, namespace="bench-other").status_code == 409
    exits = []
    monkeypatch.setattr(hooks.os, "_exit", exits.append)
    context = SimpleNamespace(run_id=identity, namespace="dev")
    hooks.crash_after_commit(context, "order", 409)
    assert exits == []
    hooks.crash_after_commit(context, "order", 200)
    hooks.crash_after_commit(context, "order", 200)
    assert exits == [86]
    assert (hooks.directory("orders") / (identity + ".checkpoint")).is_file()
    assert hook_client.delete("/internal/v1/demo-control/" + identity).status_code == 200
    assert hooks.read_control("orders", identity, "dev") is None


@pytest.mark.parametrize(
    "override",
    [
        {"scenario": "success"},
        {"expires_at": (datetime.now(UTC) + timedelta(seconds=600)).isoformat()},
        {"expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()},
        {"expires_at": "2026-11-14T00:00:00"},
    ],
)
def test_hooks_reject_unsupported_or_unbounded_plans(hook_client, override):
    assert arm(hook_client, **override).status_code == 422
