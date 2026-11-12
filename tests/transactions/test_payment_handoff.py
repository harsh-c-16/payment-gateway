"""Real Orders/Inventory/Payments HTTP; explicit catalogue and registry doubles."""

import json
import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from benchmarks.workloads import generate_workload
from tests.transactions.test_checkout_live import (
    TOKEN,
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


CASES = {
    "success": {"status": "CONFIRMED", "reservation": "COMMITTED", "attempt": "SUCCESS"},
    "decline": {"status": "CANCELLED", "reservation": "RELEASED", "attempt": "FAILED"},
}


@pytest.mark.parametrize("outcome", sorted(CASES))
def test_transaction_case(stack, namespace, monkeypatch, outcome):
    """One repeatable presentation case, read back through the existing M3 audit endpoints.

    The isolated test deployment is this module's stack: fresh PostgreSQL schemas and a fresh
    bench- namespace, with both benchmark flags set only inside this process. The catalogue
    quote and the schema registry are explicit doubles. With TRANSACTION_CASE_EVIDENCE_DIR set,
    the evidence is written to <dir>/<outcome>.json.
    """
    monkeypatch.setenv("BENCHMARK_MODE", "true")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    seed, sku, quantity, unit_price = 42, "FK-LIVE-0", 2, 54900
    workload = generate_workload("W-CHECKOUT", seed, {"active_skus": [sku]}, key_count=1)
    scenario = next(
        row["scenario_id"]
        for row in workload.records()
        if row["payload"]["payment_outcome"] == outcome
    )
    origins = {
        "orders": str(stack["client"].base_url),
        "inventory": stack["inventory_url"],
        "payments": stack["payments_url"],
    }

    def audit(service, path):
        response = httpx.get(
            origins[service].rstrip("/") + path,
            headers=headers(namespace, user="auditor", token=TOKEN),
        )
        assert response.status_code == 200, response.text
        return response.json()

    def stock():
        return next(
            row
            for row in audit("inventory", "/internal/v1/audit/stock")["items"]
            if row["sku"] == sku
        )

    opening = stock()
    quote_id = quote(stack, [(sku, quantity, unit_price)])
    run_id = f"transaction-case-{outcome}-{uuid4().hex[:8]}"
    control = {"X-Benchmark-Scenario-ID": scenario, "X-Benchmark-Seed": str(seed)}
    sent = headers(namespace) | control | {"X-Run-ID": run_id}
    body = {"quote_id": quote_id, "session_id": str(uuid4()), "confirmation_id": str(uuid4())}
    response = stack["client"].post("/v1/orders", json=body, headers=sent)
    assert response.status_code == 202, response.text
    order_id = response.json()["order_id"]
    snapshot = settle(stack, namespace, order_id)

    def mine(page):
        return [row for row in page["items"] if row["order_id"] == order_id]

    orders = mine(audit("orders", "/internal/v1/audit/orders"))
    reservations = mine(audit("inventory", "/internal/v1/audit/reservations"))
    payments = mine(audit("payments", "/internal/v1/audit/payments"))
    ledger = mine(audit("payments", "/internal/v1/audit/ledger"))
    closing = stock()
    signed = [
        {**entry, "signed_minor": entry["amount_minor"] * (1 if entry["kind"] == "DEBIT" else -1)}
        for entry in ledger
    ]
    net = sum(entry["signed_minor"] for entry in signed)
    total = quantity * unit_price
    expected = CASES[outcome]

    assert snapshot["status"] == expected["status"]
    assert [
        (o["status"], o["quote_id"], o["total_amount_minor"], o["currency"]) for o in orders
    ] == [(expected["status"], quote_id, total, "INR")]
    assert [(r["state"], r["items"]) for r in reservations] == [
        (expected["reservation"], [{"sku": sku, "quantity": quantity}])
    ]
    attempts = [attempt for payment in payments for attempt in payment["attempts"]]
    assert [(a["attempt_number"], a["status"], a["amount_minor"]) for a in attempts] == [
        (1, expected["attempt"], total)
    ]
    assert opening["reserved"] == closing["reserved"] == 0
    if outcome == "success":
        assert attempts[0]["failure_code"] is None
        assert [(e["kind"], e["amount_minor"], e["currency"]) for e in ledger] == [
            ("DEBIT", total, "INR")
        ]
        assert ledger[0]["entry_id"] == attempts[0]["debit_id"] and net == total
        assert closing["on_hand"] == opening["on_hand"] - quantity
    else:
        assert attempts[0]["failure_code"] == "DECLINED" and snapshot["failure_code"] == "DECLINED"
        assert ledger == [] and net == 0
        assert closing["on_hand"] == opening["on_hand"]

    directory = os.environ.get("TRANSACTION_CASE_EVIDENCE_DIR")
    if directory:
        evidence = {
            "case": outcome,
            "deployment": "isolated test stack: real PostgreSQL 18 and real Orders/Inventory/"
            "Payments HTTP; catalogue quote and schema registry are explicit doubles",
            "namespace": namespace,
            "run_id": run_id,
            "scenario_id": scenario,
            "seed": seed,
            "order_id": order_id,
            "quote_id": quote_id,
            "total_amount_minor": total,
            "currency": "INR",
            "order": orders[0],
            "order_snapshot": snapshot,
            "reservation": reservations[0],
            "payment_attempts": attempts,
            "ledger_entries": signed,
            "net_debit_minor": net,
            "opening_stock": opening,
            "closing_stock": closing,
        }
        Path(directory).mkdir(parents=True, exist_ok=True)
        (Path(directory) / f"{outcome}.json").write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
