"""Workload consumers. All side effects go through public clients/owner adapters."""

import json
import time
from pathlib import Path
from uuid import UUID, uuid5

from benchmarks.scheduler import Packet, Receipt, journal, utc_now
from projectctl.artifacts import canonical_json
from shared.contracts.common import RequestContext


def request_context(context):
    request_id = context["request_id"]
    return RequestContext(
        namespace=context["namespace"],
        run_id=context["run_id"],
        user_id="benchmark-" + request_id,
        correlation_id=request_id,
        request_id=request_id,
        session_id=str(uuid5(UUID(request_id), "session")),
    )


def record_request(context, principal, method, path, body, key):
    """Flush exact public request input before awaiting its response, even on loss."""
    if "evidence_directory" in context:
        with (Path(context["evidence_directory"]) / "api_requests.jsonl").open(
            "a", encoding="utf-8"
        ) as stream:
            journal(
                stream,
                {
                    "record_id": context["record"]["logical_record_id"],
                    "at": utc_now(),
                    "method": method,
                    "path": path,
                    "body": body,
                    "headers": principal.headers(key),
                },
            )


class JSONDriver:
    def materialize(self, record, context):
        return Packet(context["request_id"], canonical_json(record["payload"]), "api")


class PipelineDriver:
    """SDK materializer/publisher bindings must preserve exact bytes on retry.

    The reviewed Vichitr adapter owns envelope/schema/header encoding and ack
    projection. This consumer does not implement transport or an event builder.
    """

    def __init__(self, materializer, publisher):
        self.materializer, self.publisher = materializer, publisher

    def materialize(self, record, context):
        return self.materializer(record, context)

    async def send(self, packet, context, mark_send):
        mark_send()
        return await self.publisher(packet, context)


class SearchDriver(JSONDriver):
    def __init__(self, catalog):
        self.catalog = catalog

    def materialize(self, record, context):
        principal = request_context(context)
        request = record["payload"]["request"] | {
            "request_id": principal.request_id,
            "session_id": principal.session_id,
        }
        if "parameters" in context:
            request["mode"] = context["parameters"]["retrieval_mode"]
        return Packet(context["request_id"], canonical_json(request), "api")

    async def send(self, packet, context, mark_send):
        request = json.loads(packet.body)
        principal = request_context(context)
        record_request(context, principal, "POST", "/v1/search", request, packet.identity)
        mark_send()
        result = await self.catalog.search(request, principal, key=packet.identity)
        return Receipt(packet.identity, "accepted", details={"search": result})


class CheckoutDriver(JSONDriver):
    """Quote immediately before submission. Finality remains a separate timer."""

    def __init__(self, catalog, orders, *, poll_seconds=0.1):
        if poll_seconds <= 0:
            raise ValueError("positive declared status polling interval required")
        self.catalog, self.orders, self.poll_seconds = catalog, orders, poll_seconds

    async def send(self, packet, context, mark_send):

        payload = json.loads(packet.body)
        principal = request_context(context)
        cart_id = str(uuid5(UUID(packet.identity), "cart"))
        before_quote = time.perf_counter()
        quote_request = {
            "cart_id": cart_id,
            "cart_version": 1,
            "lines": [{"sku": payload["sku"], "quantity": 1, "display_price_minor": None}],
        }
        record_request(
            context, principal, "POST", "/v1/quotes", quote_request, packet.identity + ":quote"
        )
        quote = await self.catalog.quote(
            quote_request,
            principal,
            key=packet.identity + ":quote",
        )
        quote_seconds = time.perf_counter() - before_quote
        order_request = {
            "quote_id": quote["quote_id"],
            "session_id": principal.session_id,
            "confirmation_id": str(uuid5(UUID(packet.identity), "confirmation")),
        }
        record_request(
            context, principal, "POST", "/v1/orders", order_request, packet.identity + ":order"
        )
        mark_send()
        submitted = time.perf_counter()
        accepted = await self.orders.create(
            order_request,
            principal,
            key=packet.identity + ":order",
        )
        acceptance = time.perf_counter() - submitted
        # Return admission promptly. The drain/audit binding observes finality for
        # the entire accepted cohort, without serializing new submissions on it.
        return Receipt(
            packet.identity,
            "accepted",
            details={
                "order": accepted,
                "quote": quote,
                "requests": {
                    "quote": quote_request,
                    "order": order_request,
                    "headers": principal.headers(packet.identity + ":order"),
                },
                "quote_preparation_seconds": quote_seconds,
                "acceptance_seconds": acceptance,
                "finality_seconds": None,
                "status_poll_interval_seconds": self.poll_seconds,
                "payment_scenario": payload["payment_outcome"],
            },
        )


class IntegratedDriver(JSONDriver):
    """Exercise M1's public API. Never fabricate downstream business events.

    conversation is a public HTTP adapter with create_session/turn/update/quote/
    checkout methods; order finality is collected by the lifecycle drain/audit.
    The workload fixture specifies which SKU to add, never a model-selected action.
    """

    def __init__(self, conversation):
        self.conversation = conversation

    async def send(self, packet, context, mark_send):
        payload = json.loads(packet.body)
        principal = request_context(context)
        record_request(context, principal, "POST", "/v1/sessions", {}, packet.identity + ":session")
        mark_send()
        started = time.perf_counter()
        session = await self.conversation.create_session(
            principal, key=packet.identity + ":session"
        )
        principal = principal.model_copy(update={"session_id": session["session_id"]})
        record_request(
            context,
            principal,
            "POST",
            f"/v1/sessions/{session['session_id']}/turns",
            {"request_id": principal.request_id, "text": payload["text"], "mode": "fixed"},
            packet.identity + ":turn",
        )
        turn = await self.conversation.turn(
            principal, text=payload["text"], mode="fixed", key=packet.identity + ":turn"
        )
        if turn["llm_call_count"] != 0 or turn["outcome"] != "success":
            return Receipt(packet.identity, "rejected", details={"turn": turn})
        if payload["sku"] not in {product["sku"] for product in turn["products"]}:
            return Receipt(
                packet.identity,
                "rejected",
                details={
                    "turn": turn,
                    "reason": "frozen cart SKU was absent from search results",
                },
            )
        record_request(
            context,
            principal,
            "PUT",
            f"/v1/carts/{session['cart_id']}/items/{payload['sku']}",
            {"quantity": 1, "expected_cart_version": session["cart_version"]},
            packet.identity + ":cart",
        )
        cart = await self.conversation.update(
            principal,
            session["cart_id"],
            payload["sku"],
            quantity=1,
            expected_cart_version=session["cart_version"],
            key=packet.identity + ":cart",
        )
        record_request(
            context,
            principal,
            "POST",
            f"/v1/carts/{session['cart_id']}/quote",
            {"expected_cart_version": cart["version"]},
            packet.identity + ":quote",
        )
        quote = await self.conversation.quote(
            principal,
            session["cart_id"],
            expected_cart_version=cart["version"],
            key=packet.identity + ":quote",
        )
        confirmation_id = str(uuid5(UUID(packet.identity), "confirmation"))
        record_request(
            context,
            principal,
            "POST",
            f"/v1/carts/{session['cart_id']}/checkout",
            {
                "quote_id": quote["quote_id"],
                "expected_cart_version": cart["version"],
                "confirmed": True,
                "confirmation_id": confirmation_id,
            },
            packet.identity + ":checkout",
        )
        order = await self.conversation.checkout(
            principal,
            session["cart_id"],
            quote_id=quote["quote_id"],
            expected_cart_version=cart["version"],
            confirmed=True,
            confirmation_id=confirmation_id,
            key=packet.identity + ":checkout",
        )
        return Receipt(
            packet.identity,
            "accepted",
            details={
                "order": order,
                "quote": quote,
                "confirmation_id": confirmation_id,
                "cart_version": cart["version"],
                "workflow_acceptance_seconds": time.perf_counter() - started,
                "finality_seconds": None,
            },
        )


class ImportDriver(JSONDriver):
    def __init__(self, importer):
        self.importer = importer

    async def send(self, packet, context, mark_send):
        mark_send()
        report = await self.importer(context)
        # Harsh owns raw-open/read/archive/normalize/stage/promote readiness timers.
        if not all(key in report for key in ("raw_to_ready_seconds", "stages", "logical_digest")):
            raise ValueError("import stage/total/digest evidence missing")
        return Receipt(packet.identity, "accepted", details={"import_timings": report})


class QueryDriver(JSONDriver):
    def __init__(self, query_adapter):
        self.query_adapter = query_adapter

    async def send(self, packet, context, mark_send):
        mark_send()
        result = await self.query_adapter(json.loads(packet.body), context)
        return Receipt(packet.identity, "accepted", details={"query": result})


class AgentDriver(JSONDriver):
    def __init__(self, workflow_adapter):
        self.workflow_adapter = workflow_adapter

    async def send(self, packet, context, mark_send):
        mark_send()
        result = await self.workflow_adapter(json.loads(packet.body), context)
        return Receipt(packet.identity, "accepted", details={"assistant_turn": result})
