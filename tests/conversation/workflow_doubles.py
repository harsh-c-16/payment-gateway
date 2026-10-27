"""Explicit synthetic HTTP provider, never a real catalogue/Orders implementation."""

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx

from services.conversation.gateway import Gateway
from shared.contracts.common import RequestContext
from tests.contracts.doubles import common_error
from tests.contracts.provisional import ProvisionalContracts, examples

FIXTURE = json.loads(
    (Path(__file__).resolve().parents[2] / "contracts/fixtures/assistant/scenarios.json").read_text(
        encoding="utf-8"
    )
)


def example(endpoint):
    return copy.deepcopy(
        next(p["response"] for p in examples()["pairs"] if p["endpoint"] == endpoint)
    )


class ModelSpy:
    def __init__(self):
        self.attempts = 0

    def __call__(self, *args, **kwargs):
        self.attempts += 1
        raise AssertionError("fixed mode must never invoke a model")


class WorkflowProviderDouble:
    """A small scripted HTTP boundary, including acceptance followed by response loss."""

    def __init__(self):
        source = FIXTURE["test_catalogue"]["dictionary"]
        self.facets = {
            "dataset_revision": "p7-explicit-synthetic",
            "dictionary_version": "p7-test-v1",
            "roots": [{"id": v, "label": v.title()} for v in source["category"]],
            "path_prefixes": [],
            "brands": [],
            "colours": source["colour"],
            "materials": source["material"],
            "allowed_apparel_sizes": source["allowed_apparel_sizes"],
            "observed_apparel_sizes": ["M", "L", "S"],
            "coverage_by_category": {},
        }
        self.products = copy.deepcopy(FIXTURE["test_catalogue"]["products"])
        self.requests, self.keys, self.accepted = [], {}, {}
        self.model = ModelSpy()
        self.lose_order_response = False
        self.catalog_unavailable = self.orders_unavailable = False
        self.tamper_quote = self.tamper_search = None
        self.search_delay = self.facet_delay = 0
        self.order_status_loss = False
        self.on_quote = None
        self.quote_override = self.status_override = None
        self.model_fault = None
        self.untrusted_titles = {}
        self.order_reject = None

    def gateway(self):
        return Gateway(
            "http://catalog.test",
            "http://orders.test",
            mode="stub",
            purpose="contract_test",
            contracts=ProvisionalContracts(),
            transport=httpx.MockTransport(self),
        )

    async def __call__(self, request):
        import asyncio

        self.requests.append(request)
        path = request.url.path
        body = json.loads(request.content) if request.content else None
        if request.url.host == "catalog.test" and self.catalog_unavailable:
            return httpx.Response(503, json=common_error())
        if request.url.host == "orders.test" and self.orders_unavailable:
            return httpx.Response(503, json=common_error())
        if path == "/v1/catalog/facets":
            await asyncio.sleep(self.facet_delay)
            return httpx.Response(200, json=self.facets)
        if path == "/v1/search":
            await asyncio.sleep(self.search_delay)
            intent = body["intent"]
            hits = []
            for product in self.products:
                if not product["active"] or not product["stock_available"]:
                    continue
                if any(
                    intent.get(f) is not None and intent[f] != product[f]
                    for f in ("category", "size", "colour", "material")
                ):
                    continue
                if (
                    intent["max_price_minor"] is not None
                    and product["price_minor"] > intent["max_price_minor"]
                ):
                    continue
                hit = example("search")["hits"][0]
                hit.update(
                    {
                        f: product[f]
                        for f in (
                            "sku",
                            "category",
                            "size",
                            "colour",
                            "material",
                            "price_minor",
                            "stock_available",
                        )
                    }
                )
                hit.update(
                    product_id=product["sku"],
                    title=self.untrusted_titles.get(product["sku"], "Synthetic " + product["sku"]),
                    dataset_revision=self.facets["dataset_revision"],
                    rank=len(hits) + 1,
                )
                hits.append(hit)
            response = example("search")
            response.update(
                search_id=str(uuid4()),
                hits=hits[: body["top_k"]],
                candidate_count=len(self.products),
                eligible_count=len(hits),
                returned_count=min(len(hits), body["top_k"]),
                exhausted=len(hits) <= body["top_k"],
            )
            if self.tamper_search:
                self.tamper_search(response)
            return httpx.Response(200, json=response)
        if path in {"/v1/quotes", "/v1/orders"}:
            if path == "/v1/orders" and self.order_reject:
                return httpx.Response(409, json=common_error(self.order_reject, False))
            scope = tuple(
                request.headers[f] for f in ("X-Namespace", "X-User-ID", "Idempotency-Key")
            )
            if scope in self.keys:
                previous_body, response = self.keys[scope]
                assert previous_body == body, "consumer changed downstream command identity"
            elif path == "/v1/quotes":
                response = example("quote")
                lines = [
                    {
                        "sku": line["sku"],
                        "quantity": line["quantity"],
                        "unit_price_minor": 39900,
                        "line_total_minor": line["quantity"] * 39900,
                        "catalog_version": 2,
                    }
                    for line in body["lines"]
                ]
                response.update(
                    quote_id=str(uuid4()),
                    user_id=request.headers["X-User-ID"],
                    cart_id=body["cart_id"],
                    cart_version=body["cart_version"],
                    lines=lines,
                    total_amount_minor=sum(x["line_total_minor"] for x in lines),
                    created_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                    expires_at=(datetime.now(UTC) + timedelta(seconds=60))
                    .isoformat()
                    .replace("+00:00", "Z"),
                )
                if self.quote_override:
                    response = copy.deepcopy(self.quote_override)
                if self.tamper_quote:
                    self.tamper_quote(response)
                self.keys[scope] = (body, response)
            else:
                quote = body["quote_id"]
                response = self.accepted.setdefault(
                    quote, {"order_id": str(uuid4()), "status": "PENDING"}
                )
                response["status_url"] = "/v1/orders/" + response["order_id"]
                self.keys[scope] = (body, response)
            if path == "/v1/orders" and self.lose_order_response:
                self.lose_order_response = False
                raise httpx.ReadTimeout("explicit loss after double acceptance", request=request)
            if path == "/v1/quotes" and self.on_quote:
                self.on_quote()
            return httpx.Response(201 if path == "/v1/quotes" else 202, json=response)
        if path.startswith("/v1/orders/"):
            if self.order_status_loss:
                self.order_status_loss = False
                raise httpx.ReadTimeout("explicit lost read", request=request)
            response = example("order_status")
            if self.status_override:
                response = copy.deepcopy(self.status_override)
            response.update(
                order_id=path.rsplit("/", 1)[1],
                user_id=request.headers["X-User-ID"],
                session_id=request.headers["X-Session-ID"],
            )
            return httpx.Response(200, json=response)
        raise AssertionError("unexpected provider/tool/model call: " + path)

    def count(self, path):
        return sum(request.url.path == path for request in self.requests)


def seed_workflow_fixture(state, fixture):
    """Test-only local M1 setup from the frozen business inputs; no provider DB writes."""
    from psycopg.types.json import Jsonb

    context = RequestContext.model_validate(fixture["context"])
    cart, quote = fixture["cart"], fixture["quote"]
    with state.database.transaction() as tx:
        tx.execute(
            "INSERT INTO sessions(namespace,session_id,user_id,created_at) VALUES (%s,%s,%s,%s)",
            (context.namespace, context.session_id, context.user_id, cart["updated_at"]),
        )
        tx.execute(
            "INSERT INTO carts(namespace,cart_id,session_id,user_id,version,updated_at) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (
                context.namespace,
                cart["cart_id"],
                context.session_id,
                context.user_id,
                cart["version"],
                cart["updated_at"],
            ),
        )
        for line in cart["lines"]:
            tx.execute(
                "INSERT INTO cart_items(namespace,cart_id,sku,quantity,display_price_minor) "
                "VALUES (%s,%s,%s,%s,%s)",
                (
                    context.namespace,
                    cart["cart_id"],
                    line["sku"],
                    line["quantity"],
                    line["display_price_minor"],
                ),
            )
        if quote and quote["cart_version"] == cart["version"]:
            tx.execute(
                "UPDATE carts SET quote_id=%s,quote_cart_version=%s,quote_payload=%s "
                "WHERE namespace=%s AND cart_id=%s",
                (
                    quote["quote_id"],
                    quote["cart_version"],
                    Jsonb(quote),
                    context.namespace,
                    cart["cart_id"],
                ),
            )
    return context
