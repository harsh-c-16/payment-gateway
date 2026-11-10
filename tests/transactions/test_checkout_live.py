"""Live checkout: real PostgreSQL 18 and real HTTP between Orders, Inventory and Payments.

Mocked unit tests cannot see driver types, transaction scope, envelope rules or cross-service
headers. Requires INVENTORY_TEST_DATABASE_URL (the same login as test_seed); each service gets
its own throwaway schema, dropped afterwards, migrated through services.orders.m3_setup.

Explicit doubles: the catalogue is a small HTTP server speaking the real
GET /internal/v1/quotes/{id} contract (service token, 404 unknown, 403 another user's
quote, canonical Quote JSON with expires_at), so Orders' real HTTP quote path runs; and
the payment roll. The real catalogue service is not part of this test.
"""

import hashlib
import json
import os
import socket
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from psycopg import sql
from psycopg.conninfo import make_conninfo

import services.inventory.app as inventory_app
import services.orders.app as orders_app
import services.payments.app as payments_app
import services.payments.authorize as authorize
import shared.event_transport as sdk
from services.inventory.database import Database as InventoryDatabase
from services.inventory.events import InventoryEvents
from services.inventory.seed import seed_inventory
from services.orders import m3_setup
from services.orders.events import OrderEvents
from services.payments.events import PaymentEvents
from shared.contracts.common import RequestContext
from shared.event_transport.codec import EventCodec
from shared.event_transport.schemas import canonical_json
from tests.pipelines.transport_doubles import offline_cache

ROOT = Path(__file__).resolve().parents[2]
SERVICES = ("orders", "inventory", "payments")
TERMINAL = {"CONFIRMED", "CANCELLED", "MANUAL_REVIEW"}
TOKEN = "live-test-service-token"


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


def catalogue_double(quotes):
    """Explicit double of Harsh's GET /internal/v1/quotes/{quote_id} contract."""
    app = FastAPI()

    @app.get("/internal/v1/quotes/{quote_id}")
    def quote(quote_id: str, request: Request):
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            return JSONResponse({"error": {"code": "UNAUTHORIZED"}}, status_code=401)
        if quote_id not in quotes:
            return JSONResponse({"error": {"code": "NOT_FOUND"}}, status_code=404)
        if quotes[quote_id]["user_id"] != request.headers.get("X-User-ID"):
            return JSONResponse({"error": {"code": "FORBIDDEN"}}, status_code=403)
        return quotes[quote_id]

    return app


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
            m3_setup.setup(name, urls[name])
            patch.setenv(f"{name.upper()}_DATABASE_URL", urls[name])
        patch.setattr(
            sdk, "_codec", EventCodec(offline_cache(), dataset_revision="live-test-revision")
        )
        quotes, roll = {}, PaymentRoll()
        patch.setattr(authorize, "random", roll)
        patch.setenv("INTERNAL_API_TOKEN", TOKEN)
        catalogue, catalogue_url = serve(catalogue_double(quotes))
        servers.append(catalogue)
        patch.setenv("CATALOG_URL", catalogue_url)

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
    value = "bench-transaction-" + uuid4().hex[:12]
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


def headers(namespace, user="live-user", token=None):
    result = {
        "X-Namespace": namespace,
        "X-Run-ID": "live",
        "X-User-ID": user,
        "X-Correlation-ID": str(uuid4()),
        "X-Request-ID": str(uuid4()),
    }
    if token:
        result["Authorization"] = f"Bearer {token}"
    return result


def utc(moment):
    return moment.isoformat().replace("+00:00", "Z")


def quote(stack, lines, *, owner="live-user", expires_in=60):
    quote_id = str(uuid4())
    now = datetime.now(UTC)
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
        "quote_id": quote_id,
        "user_id": owner,
        "cart_id": str(uuid4()),
        "cart_version": 1,
        "lines": quote_lines,
        "total_amount_minor": sum(line["line_total_minor"] for line in quote_lines),
        "currency": "INR",
        "created_at": utc(now),
        "expires_at": utc(now + timedelta(seconds=expires_in)),
    }
    return quote_id


def submit(stack, namespace, quote_id, user="live-user"):
    body = {"quote_id": quote_id, "session_id": str(uuid4()), "confirmation_id": str(uuid4())}
    response = stack["client"].post("/v1/orders", json=body, headers=headers(namespace, user))
    return response, body


def checkout(stack, namespace, lines):
    response, body = submit(stack, namespace, quote(stack, lines))
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


def test_business_decline_is_not_retried_and_releases_stock_then_cancel(stack, namespace):
    stack["roll"].value = 0.0
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
    assert attempts == [(1, "FAILED")]
    assert snapshot["failure_code"] == "DECLINED"
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


def base_url(stack, service):
    return {
        "orders": str(stack["client"].base_url).rstrip("/"),
        "inventory": stack["inventory_url"],
        "payments": stack["payments_url"],
    }[service]


def order_rows(stack, namespace):
    return rows(stack, "orders", "SELECT order_id FROM orders WHERE namespace=%s", namespace)


def test_expired_quote_is_rejected_without_an_order(stack, namespace):
    response, _ = submit(stack, namespace, quote(stack, [("FK-LIVE-0", 1, 100)], expires_in=-1))

    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "QUOTE_EXPIRED"
    assert order_rows(stack, namespace) == []


def test_another_users_quote_is_forbidden_without_an_order(stack, namespace):
    foreign = quote(stack, [("FK-LIVE-0", 1, 100)], owner="someone-else")

    response, _ = submit(stack, namespace, foreign)

    assert response.status_code == 403, response.text
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert order_rows(stack, namespace) == []


def test_unknown_quote_is_not_found(stack, namespace):
    response, _ = submit(stack, namespace, str(uuid4()))

    assert response.status_code == 404, response.text
    assert order_rows(stack, namespace) == []


def test_retry_of_accepted_quote_returns_same_order_after_expiry(stack, namespace):
    stack["roll"].value = 0.9
    quote_id = quote(stack, [("FK-LIVE-1", 1, 500)])
    first, body = submit(stack, namespace, quote_id)
    assert first.status_code == 202, first.text
    stack["quotes"][quote_id]["expires_at"] = utc(datetime.now(UTC) - timedelta(seconds=5))

    retry = stack["client"].post("/v1/orders", json=body, headers=headers(namespace))

    assert retry.status_code == 202, retry.text
    assert retry.json()["order_id"] == first.json()["order_id"]
    assert len(order_rows(stack, namespace)) == 1


def test_only_the_owner_can_read_status_and_events(stack, namespace):
    stack["roll"].value = 0.9
    order_id, _ = checkout(stack, namespace, [("FK-LIVE-2", 1, 300)])
    settle(stack, namespace, order_id)

    for path in (f"/v1/orders/{order_id}", f"/v1/orders/{order_id}/events"):
        stranger = stack["client"].get(path, headers=headers(namespace, "intruder"))
        assert stranger.status_code == 404, (path, stranger.text)
        assert order_id not in stranger.text
        owner = stack["client"].get(path, headers=headers(namespace))
        assert owner.status_code == 200, (path, owner.text)


INTERNAL_READS = [
    ("orders", "/internal/v1/audit/orders"),
    ("orders", "/internal/v1/audit/saga-jobs"),
    ("inventory", "/internal/v1/audit/stock"),
    ("inventory", "/internal/v1/audit/reservations"),
    ("inventory", "/internal/v1/inventory/FK-LIVE-0"),
    ("inventory", "/internal/v1/reservations/by-order/{order_id}"),
    ("payments", "/internal/v1/audit/payments"),
    ("payments", "/internal/v1/audit/ledger"),
    ("payments", "/internal/v1/payments/by-order/{order_id}"),
]


@pytest.mark.parametrize(("service", "path"), INTERNAL_READS)
def test_internal_reads_require_the_service_token(stack, namespace, service, path):
    url = base_url(stack, service) + path.format(order_id=uuid4())
    for token in (None, "wrong-token"):
        refused = httpx.get(url, headers=headers(namespace, token=token), timeout=5)
        assert refused.status_code == 401, (token, refused.text)
    allowed = httpx.get(url, headers=headers(namespace, token=TOKEN), timeout=5)
    assert allowed.status_code in (200, 404), allowed.text


@pytest.mark.parametrize(
    ("service", "path", "body"),
    [
        ("inventory", "/internal/v1/reservations", {"order_id": str(uuid4()), "items": []}),
        ("inventory", "/internal/v1/reservations/by-order/{order_id}/commit", {}),
        ("inventory", "/internal/v1/reservations/by-order/{order_id}/release", {}),
        ("payments", "/internal/v1/payments/authorize", {}),
        ("payments", "/internal/v1/payments/by-order/{order_id}/reverse", {}),
        ("orders", "/internal/v1/fault-barriers", {}),
    ],
)
def test_internal_commands_refuse_missing_token_before_anything_else(
    stack, namespace, service, path, body
):
    url = base_url(stack, service) + path.format(order_id=uuid4())
    response = httpx.post(url, json=body, headers=headers(namespace), timeout=5)
    assert response.status_code == 401, response.text


def test_fault_barriers_need_both_flags_and_a_bench_namespace(stack, namespace, monkeypatch):
    url = base_url(stack, "orders") + "/internal/v1/fault-barriers"
    body = {"barrier_name": "live.unused-barrier", "enabled": False}
    auth = headers(namespace, token=TOKEN)

    for benchmark, faults in (("false", "true"), ("true", "false")):
        monkeypatch.setenv("BENCHMARK_MODE", benchmark)
        monkeypatch.setenv("FAULT_INJECTION_ENABLED", faults)
        assert httpx.post(url, json=body, headers=auth, timeout=5).status_code == 403

    monkeypatch.setenv("BENCHMARK_MODE", "true")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    dev = httpx.post(url, json=body, headers=headers("dev", token=TOKEN), timeout=5)
    assert dev.status_code == 403
    allowed = httpx.post(url, json=body, headers=auth, timeout=5)
    assert allowed.status_code == 200, allowed.text
    assert rows(
        stack, "orders", "SELECT enabled FROM fault_barriers WHERE namespace=%s", namespace
    ) == [(False,)]


def test_setup_is_repeatable_and_records_checksums(stack):
    for name in SERVICES:
        again = m3_setup.setup(name, stack["urls"][name])
        assert again["applied"] == []
        recorded = rows(stack, name, "SELECT filename FROM m3_schema_migrations ORDER BY version")
        assert [row[0] for row in recorded] == again["verified"]


@pytest.mark.parametrize(
    ("service", "path"), [read for read in INTERNAL_READS if "/audit/" in read[1]]
)
def test_audit_exports_answer(stack, namespace, service, path):
    response = httpx.get(
        base_url(stack, service) + path, headers=headers(namespace, token=TOKEN), timeout=5
    )
    assert response.status_code == 200, response.text
    assert set(response.json()) >= {"items", "count"}
