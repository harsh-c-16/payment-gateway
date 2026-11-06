"""Live checkout: real PostgreSQL 18 and real HTTP between Orders, Inventory and Payments.

Mocked unit tests cannot see driver types, transaction scope, envelope rules or cross-service
headers. Requires INVENTORY_TEST_DATABASE_URL (the same login as test_seed); each service gets
its own throwaway schema, dropped afterwards. Catalogue quotes and the payment roll are doubles.
"""

import hashlib
import json
import os
import socket
import threading
import time
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
import pytest
import uvicorn
from psycopg import sql
from psycopg.conninfo import make_conninfo

import services.inventory.app as inventory_app
import services.orders.app as orders_app
import services.orders.commands as commands
import services.payments.app as payments_app
import services.payments.authorize as authorize
import shared.event_transport as sdk
from services.inventory.database import Database as InventoryDatabase
from services.inventory.events import InventoryEvents
from services.inventory.seed import seed_inventory
from services.orders.events import OrderEvents
from services.payments.events import PaymentEvents
from shared.contracts.common import RequestContext
from shared.event_transport.codec import EventCodec
from shared.event_transport.schemas import canonical_json
from tests.pipelines.transport_doubles import offline_cache

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ("orders", "inventory", "payments")
TERMINAL = {"CONFIRMED", "CANCELLED", "MANUAL_REVIEW"}


class PaymentRoll:
    value = 0.9

    def random(self):
        return self.value

    def choice(self, options):
        return options[0]


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def serve(app):
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "service did not start"
        time.sleep(0.02)
    return server, f"http://127.0.0.1:{port}"


def configured(events):
    events.configured = True
    return events


@pytest.fixture(scope="module")
def stack():
    url = os.environ.get("INVENTORY_TEST_DATABASE_URL")
    if not url:
        pytest.skip("NOT_RUN: INVENTORY_TEST_DATABASE_URL required for real PostgreSQL 18 checks")
    suffix = uuid4().hex
    schemas = {name: f"m3_live_{name}_{suffix}" for name in SERVICES}
    urls = {}
    with psycopg.connect(url, autocommit=True) as admin:
        assert 180000 <= admin.info.server_version < 190000
        for schema in schemas.values():
            admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    servers = []
    patch = pytest.MonkeyPatch()
    try:
        for name, schema in schemas.items():
            urls[name] = make_conninfo(url, options=f"-c search_path={schema}")
            with psycopg.connect(urls[name]) as tx:
                for path in sorted((ROOT / f"migrations/{name}").glob("*.sql")):
                    tx.execute(path.read_text())
            patch.setenv(f"{name.upper()}_DATABASE_URL", urls[name])
        patch.setattr(
            sdk, "_codec", EventCodec(offline_cache(), dataset_revision="live-test-revision")
        )
        quotes, roll = {}, PaymentRoll()
        patch.setattr(commands, "_fetch_quote", lambda _url, quote_id, *_: quotes[quote_id])
        patch.setattr(authorize, "random", roll)

        inventory, inventory_url = serve(
            inventory_app.create_app(events=configured(InventoryEvents()))
        )
        payments, payments_url = serve(payments_app.create_app(events=configured(PaymentEvents())))
        servers += [inventory, payments]
        patch.setenv("INVENTORY_URL", inventory_url)
        patch.setenv("PAYMENTS_URL", payments_url)
        orders, orders_url = serve(orders_app.create_app(events=configured(OrderEvents())))
        servers.append(orders)
        with httpx.Client(base_url=orders_url, timeout=5) as client:
            yield {
                "client": client,
                "urls": urls,
                "quotes": quotes,
                "roll": roll,
                "inventory_url": inventory_url,
                "payments_url": payments_url,
            }
    finally:
        for server in servers:
            server.should_exit = True
        patch.undo()
        time.sleep(0.3)
        with psycopg.connect(url, autocommit=True) as admin:
            for schema in schemas.values():
                assert schema.startswith("m3_live_")
                admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


@pytest.fixture
def namespace(stack):
    value = "bench-live-" + uuid4().hex[:12]
    context = RequestContext(
        namespace=value,
        run_id="live",
        user_id="live-user",
        correlation_id=str(uuid4()),
        request_id=str(uuid4()),
        session_id=None,
    )
    document = json.loads(
        (ROOT / "contracts/fixtures/catalog/sku_manifest.example.json").read_text()
    )
    document.update(namespace=value, sku_count=3)
    document["sorted_skus"] = [
        {
            "sku": f"FK-LIVE-{i}",
            "product_id": f"FK-LIVE-{i}",
            "source_pid": str(i),
            "source_observation_id": f"obs-{i}",
        }
        for i in range(3)
    ]
    content = {key: item for key, item in document.items() if key != "content_sha256"}
    document["content_sha256"] = hashlib.sha256(canonical_json(content)).hexdigest()
    seed_inventory(
        InventoryDatabase(stack["urls"]["inventory"]),
        value,
        document,
        events=configured(InventoryEvents()),
        context=context,
        default_on_hand=5,
    )
    return value


def headers(namespace):
    return {
        "X-Namespace": namespace,
        "X-Run-ID": "live",
        "X-User-ID": "live-user",
        "X-Correlation-ID": str(uuid4()),
        "X-Request-ID": str(uuid4()),
    }


def checkout(stack, namespace, lines):
    quote_id = str(uuid4())
    quote_lines = [
        {
            "sku": sku,
            "quantity": quantity,
            "unit_price_minor": price,
            "line_total_minor": price * quantity,
            "catalog_version": 1,
        }
        for sku, quantity, price in lines
    ]
    stack["quotes"][quote_id] = {
        "lines": quote_lines,
        "total_amount_minor": sum(line["line_total_minor"] for line in quote_lines),
    }
    body = {"quote_id": quote_id, "session_id": str(uuid4()), "confirmation_id": str(uuid4())}
    response = stack["client"].post("/v1/orders", json=body, headers=headers(namespace))
    assert response.status_code == 202, response.text
    return response.json()["order_id"], body


def settle(stack, namespace, order_id, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = stack["client"].get(f"/v1/orders/{order_id}", headers=headers(namespace)).json()
        if snapshot["status"] in TERMINAL:
            return snapshot
        time.sleep(0.1)
    raise AssertionError(f"order did not settle: {snapshot}")


def rows(stack, service, query, *args):
    with psycopg.connect(stack["urls"][service]) as tx:
        return tx.execute(query, args).fetchall()


def test_happy_path_confirms_commits_stock_and_debits_once(stack, namespace):
    stack["roll"].value = 0.9
    order_id, body = checkout(stack, namespace, [("FK-LIVE-0", 2, 1000), ("FK-LIVE-1", 1, 500)])
    again = stack["client"].post("/v1/orders", json=body, headers=headers(namespace))
    assert again.json()["order_id"] == order_id

    snapshot = settle(stack, namespace, order_id)

    assert snapshot["status"] == "CONFIRMED"
    assert snapshot["reservation_id"] and snapshot["payment_id"]
    stock = rows(
        stack,
        "inventory",
        "SELECT sku, on_hand, reserved FROM inventory WHERE namespace=%s ORDER BY sku",
        namespace,
    )
    assert stock == [("FK-LIVE-0", 3, 0), ("FK-LIVE-1", 4, 0), ("FK-LIVE-2", 5, 0)]
    ledger = rows(
        stack,
        "payments",
        "SELECT kind, amount_minor FROM ledger_entries WHERE namespace=%s",
        namespace,
    )
    assert ledger == [("DEBIT", 2500)]
    stream = stack["client"].get(f"/v1/orders/{order_id}/events", headers=headers(namespace))
    assert f"id:{snapshot['order_version']}" in stream.text and "CONFIRMED" in stream.text


def test_two_failed_payments_release_stock_then_cancel(stack, namespace):
    stack["roll"].value = 0.05
    order_id, _ = checkout(stack, namespace, [("FK-LIVE-2", 3, 700)])

    snapshot = settle(stack, namespace, order_id)

    assert snapshot["status"] == "CANCELLED"
    attempts = rows(
        stack,
        "payments",
        "SELECT attempt_number, status FROM payment_attempts WHERE namespace=%s "
        "ORDER BY attempt_number",
        namespace,
    )
    assert attempts == [(1, "FAILED"), (2, "FAILED")]
    assert rows(
        stack, "payments", "SELECT quiesced FROM payment_orders WHERE namespace=%s", namespace
    ) == [(True,)]
    reservation = rows(
        stack, "inventory", "SELECT state FROM reservations WHERE namespace=%s", namespace
    )
    assert reservation == [("RELEASED",)]
    stock = rows(
        stack,
        "inventory",
        "SELECT on_hand, reserved FROM inventory WHERE namespace=%s AND sku=%s",
        namespace,
        "FK-LIVE-2",
    )
    assert stock == [(5, 0)]


def test_out_of_stock_cancels_without_payment(stack, namespace):
    stack["roll"].value = 0.9
    order_id, _ = checkout(stack, namespace, [("FK-LIVE-0", 9, 1000)])

    assert settle(stack, namespace, order_id)["status"] == "CANCELLED"
    assert (
        rows(stack, "payments", "SELECT 1 FROM payment_attempts WHERE namespace=%s", namespace)
        == []
    )


def test_every_service_writes_valid_outbox_events_in_the_order_namespace(stack, namespace):
    stack["roll"].value = 0.9
    order_id, _ = checkout(stack, namespace, [("FK-LIVE-1", 1, 500)])
    settle(stack, namespace, order_id)

    for service in SERVICES:
        events = rows(
            stack,
            service,
            "SELECT convert_from(payload, 'UTF8')::jsonb FROM outbox WHERE namespace=%s",
            namespace,
        )
        assert events, service
        for (event,) in events:
            assert event["namespace"] == namespace
            assert event["metadata"]["synthetic"] is True
            assert event["metadata"]["scenario_source"] == "simulation"
            assert event["metadata"]["dataset_revision"]
    order_types = {
        event["event_type"]
        for (event,) in rows(
            stack,
            "orders",
            "SELECT convert_from(payload, 'UTF8')::jsonb FROM outbox WHERE namespace=%s",
            namespace,
        )
    }
    assert order_types == {"ORDER_CREATED", "ORDER_CONFIRMED"}


@pytest.mark.parametrize(
    ("service", "path"),
    [
        ("orders", "/internal/v1/audit/orders"),
        ("orders", "/internal/v1/audit/saga-jobs"),
        ("inventory", "/internal/v1/audit/stock"),
        ("inventory", "/internal/v1/audit/reservations"),
        ("payments", "/internal/v1/audit/payments"),
        ("payments", "/internal/v1/audit/ledger"),
    ],
)
def test_audit_exports_answer(stack, namespace, service, path):
    base = {
        "orders": str(stack["client"].base_url),
        "inventory": stack["inventory_url"],
        "payments": stack["payments_url"],
    }[service]
    response = httpx.get(base.rstrip("/") + path, headers=headers(namespace), timeout=5)
    assert response.status_code == 200, response.text
    assert set(response.json()) >= {"items", "count"}
