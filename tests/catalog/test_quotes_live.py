"""Quote pricing, idempotency and the internal lookup Orders relies on."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from starlette.testclient import TestClient

from services.catalog.app import create_app
from tests.catalog.helpers import import_rows, row
from tests.catalog.service_helpers import TOKEN, headers, lookup, quote


def test_quote_uses_authoritative_prices_not_display_prices(world):
    client, namespace, _ = world
    result = quote(
        client,
        namespace,
        [
            {"sku": "FK-SHIRT1", "quantity": 2, "display_price_minor": 1},
            {"sku": "FK-WATCH1", "quantity": 1},
        ],
    )
    by_sku = {line["sku"]: line for line in result["lines"]}
    assert by_sku["FK-SHIRT1"]["unit_price_minor"] == 50000
    assert by_sku["FK-SHIRT1"]["line_total_minor"] == 100000
    assert result["total_amount_minor"] == 600000
    assert result["currency"] == "INR"


def test_quote_is_idempotent_and_conflicts_on_changed_input(world):
    client, namespace, _ = world
    key, cart = str(uuid4()), str(uuid4())
    lines = [{"sku": "FK-SHIRT1", "quantity": 1}]
    first = quote(client, namespace, lines, key=key, cart=cart)
    assert quote(client, namespace, lines, key=key, cart=cart)["quote_id"] == first["quote_id"]
    conflict = quote(client, namespace, lines, key=key, cart=cart, version=2, expect=409)
    assert conflict["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    other_user = quote(client, namespace, lines, key=key, cart=cart, user="other-user")
    assert other_user["quote_id"] != first["quote_id"]


def test_concurrent_same_key_creates_one_quote(world):
    client, namespace, _ = world
    key, cart = str(uuid4()), str(uuid4())
    lines = [{"sku": "FK-SHIRT1", "quantity": 1}]
    with ThreadPoolExecutor(6) as pool:
        results = list(
            pool.map(lambda _: quote(client, namespace, lines, key=key, cart=cart), range(6))
        )
    assert len({result["quote_id"] for result in results}) == 1


@pytest.mark.parametrize(
    "lines,status,code",
    [
        ([{"sku": "FK-NOPRICE", "quantity": 1}], 409, "PRODUCT_NOT_SELLABLE"),
        ([{"sku": "FK-ABSENT", "quantity": 1}], 404, "NOT_FOUND"),
        ([{"sku": "FK-SHIRT1", "quantity": 11}], 422, "VALIDATION_ERROR"),
        ([{"sku": "FK-SHIRT1", "quantity": 0}], 422, "VALIDATION_ERROR"),
        ([{"sku": "FK-SHIRT1", "quantity": "1"}], 422, "VALIDATION_ERROR"),
        ([{"sku": "FK-SHIRT1", "quantity": 1.5}], 422, "VALIDATION_ERROR"),
        ([], 422, "VALIDATION_ERROR"),
        ([{"sku": "FK-SHIRT1", "quantity": 1}] * 2, 422, "VALIDATION_ERROR"),
    ],
)
def test_quote_rejections(world, lines, status, code):
    client, namespace, _ = world
    assert quote(client, namespace, lines, expect=status)["error"]["code"] == code


def test_failed_quote_can_retry_with_same_key(world):
    client, namespace, _ = world
    key = str(uuid4())
    cart = str(uuid4())
    quote(client, namespace, [{"sku": "FK-ABSENT", "quantity": 1}], key=key, cart=cart, expect=404)
    quote(client, namespace, [{"sku": "FK-ABSENT", "quantity": 1}], key=key, cart=cart, expect=404)


def test_quote_maximum_total_fits_common_bounds(world, db):
    client, namespace, _ = world
    with db.transaction() as tx:
        tx.execute(
            "UPDATE products SET price_minor=1000000000 WHERE namespace=%s AND sku='FK-SHIRT1'",
            (namespace,),
        )
    result = quote(client, namespace, [{"sku": "FK-SHIRT1", "quantity": 10}])
    assert result["total_amount_minor"] == 10_000_000_000


def test_internal_quote_lookup_binds_user_and_requires_token(world):
    client, namespace, _ = world
    created = quote(client, namespace, [{"sku": "FK-SHIRT1", "quantity": 2}])
    found = lookup(client, namespace, created["quote_id"])
    assert found.status_code == 200 and found.json() == created
    assert lookup(client, namespace, created["quote_id"], user="stranger").status_code == 403
    assert lookup(client, namespace, created["quote_id"], internal=False).status_code == 401
    assert lookup(client, namespace, str(uuid4())).status_code == 404
    other = "bench-h-" + uuid4().hex[:16]
    assert lookup(client, other, created["quote_id"]).status_code == 404


def test_expired_quote_stays_visible_as_expired(tmp_path, database_url, db, events, monkeypatch):
    monkeypatch.setenv("INTERNAL_API_TOKEN", TOKEN)
    monkeypatch.setenv("QUOTE_TTL_SECONDS", "1")
    namespace = "bench-h-" + uuid4().hex[:16]
    import_rows(tmp_path, database_url, namespace, [row("A1")])
    client = TestClient(create_app(db=db, events=events))
    created = quote(client, namespace, [{"sku": "FK-A1", "quantity": 1}])
    with db.transaction() as tx:
        tx.execute(
            "UPDATE quotes SET created_at=created_at-interval '1 hour',"
            "expires_at=expires_at-interval '1 hour' WHERE namespace=%s",
            (namespace,),
        )
    found = lookup(client, namespace, created["quote_id"]).json()
    assert found["expires_at"] < created["created_at"]


def test_quote_requires_an_idempotency_key(world):
    client, namespace, _ = world
    response = client.post(
        "/v1/quotes",
        json={
            "cart_id": str(uuid4()),
            "cart_version": 1,
            "lines": [{"sku": "FK-SHIRT1", "quantity": 1}],
        },
        headers=headers(namespace),
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BAD_REQUEST"
