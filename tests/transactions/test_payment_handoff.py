"""Real Orders/Inventory/Payments HTTP; explicit catalogue and registry doubles."""

from uuid import uuid4

import pytest

from benchmarks.workloads import generate_workload
from tests.transactions.test_checkout_live import (
    headers,
    quote,
    rows,
    settle,
)
from tests.transactions.test_checkout_live import (
    namespace as namespace,
)
from tests.transactions.test_checkout_live import (
    stack as stack,
)


@pytest.mark.parametrize("outcome", ["success", "decline"])
def test_scenario_reaches_payments_and_all_workers_preserve_checkout_identity(
    stack, namespace, monkeypatch, outcome
):
    monkeypatch.setenv("BENCHMARK_MODE", "true")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    workload = generate_workload("W-CHECKOUT", 42, {"active_skus": ["FK-LIVE-0"]}, key_count=1)
    scenario = next(
        row["scenario_id"]
        for row in workload.records()
        if row["payload"]["payment_outcome"] == outcome
    )
    control = {"X-Benchmark-Scenario-ID": scenario, "X-Benchmark-Seed": "42"}
    original = headers(namespace) | control
    original["X-Run-ID"] = "original-checkout-run"
    body = {
        "quote_id": quote(stack, [("FK-LIVE-0", 1, 1000)]),
        "session_id": str(uuid4()),
        "confirmation_id": str(uuid4()),
    }
    response = stack["client"].post("/v1/orders", json=body, headers=original)
    assert response.status_code == 202, response.text
    order_id = response.json()["order_id"]
    snapshot = settle(stack, namespace, order_id)
    assert snapshot["status"] == ("CONFIRMED" if outcome == "success" else "CANCELLED")
    assert snapshot["failure_code"] == (None if outcome == "success" else "DECLINED")
    attempts = rows(
        stack,
        "payments",
        "SELECT attempt_number,benchmark_headers,origin_context "
        "FROM payment_attempts WHERE namespace=%s",
        namespace,
    )
    assert len(attempts) == 1
    assert attempts[0][0:2] == (1, control)
    assert attempts[0][2]["run_id"] == original["X-Run-ID"]
    assert attempts[0][2]["request_id"] == original["X-Request-ID"]
    for service in ("orders", "inventory", "payments"):
        events = rows(
            stack,
            service,
            "SELECT convert_from(payload,'UTF8')::jsonb FROM outbox WHERE namespace=%s",
            namespace,
        )
        relevant = [event for (event,) in events if event["payload"].get("order_id") == order_id]
        assert relevant, service
        for event in relevant:
            assert event["run_id"] == original["X-Run-ID"]
            assert event["correlation_id"] == original["X-Correlation-ID"]


@pytest.mark.parametrize(
    "benchmark,faults,scope",
    [
        ("false", "true", "bench-control"),
        ("true", "false", "bench-control"),
        ("true", "true", "dev"),
        ("true", "true", "bench-production-test"),
    ],
)
def test_scenario_controls_refused_at_both_service_ingresses(
    stack, monkeypatch, benchmark, faults, scope
):
    import httpx

    monkeypatch.setenv("BENCHMARK_MODE", benchmark)
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", faults)
    control = {"X-Benchmark-Scenario-ID": "measurement:000001:cart", "X-Benchmark-Seed": "42"}
    for service, path, body in [
        (
            "orders",
            "/v1/orders",
            {"quote_id": str(uuid4()), "session_id": str(uuid4()), "confirmation_id": str(uuid4())},
        ),
        (
            "payments",
            "/internal/v1/payments/authorize",
            {
                "order_id": str(uuid4()),
                "attempt_number": 1,
                "amount_minor": 1000,
                "currency": "INR",
            },
        ),
    ]:
        origin = str(stack["client"].base_url) if service == "orders" else stack["payments_url"]
        response = httpx.post(
            origin.rstrip("/") + path,
            json=body,
            headers=headers(scope, token="live-test-service-token") | control,
        )
        assert response.status_code == 403, response.text
