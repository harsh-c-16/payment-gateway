import asyncio
import json
from uuid import uuid4

from benchmarks.drivers import (
    AgentDriver,
    CheckoutDriver,
    ImportDriver,
    IntegratedDriver,
    QueryDriver,
    SearchDriver,
)


def context():
    return {"request_id": str(uuid4()), "run_id": str(uuid4()), "namespace": "bench-driver"}


class PublicAPIDouble:
    def __init__(self):
        self.calls = []

    async def quote(self, request, principal, *, key):
        self.calls.append(("quote", request, principal, key))
        return {"quote_id": str(uuid4()), "total_amount_minor": 39900}

    async def create(self, request, principal, *, key):
        self.calls.append(("order", request, principal, key))
        return {"order_id": str(uuid4()), "status": "PENDING"}

    async def search(self, request, principal, *, key):
        self.calls.append(("search", request, principal, key))
        return {"hits": [], "returned_count": 0}


def test_checkout_prepares_quote_before_mark_and_preserves_authority_and_identity(tmp_path):
    api = PublicAPIDouble()
    driver = CheckoutDriver(api, api)
    ctx = context()
    ctx |= {"evidence_directory": str(tmp_path), "record": {"logical_record_id": "source-000000"}}
    record = {"payload": {"sku": "FK-one", "payment_outcome": "success"}}
    packet = driver.materialize(record, ctx)
    marks = []

    def mark():
        marks.append([call[0] for call in api.calls])

    receipt = asyncio.run(driver.send(packet, ctx, mark))
    assert marks == [["quote"]]
    assert [call[0] for call in api.calls] == ["quote", "order"]
    assert receipt.details["quote"]["total_amount_minor"] == 39900
    assert set(api.calls[1][1]) == {"quote_id", "session_id", "confirmation_id"}
    assert api.calls[0][2].request_id == ctx["request_id"]
    assert api.calls[1][3] == ctx["request_id"] + ":order"
    assert receipt.details["finality_seconds"] is None
    from jsonschema import Draft202012Validator

    from tests.contracts.provisional import CREATE_ORDER, QUOTE_REQUEST

    Draft202012Validator(QUOTE_REQUEST).validate(api.calls[0][1])
    Draft202012Validator(CREATE_ORDER).validate(api.calls[1][1])
    journal = [
        json.loads(line) for line in (tmp_path / "api_requests.jsonl").read_text().splitlines()
    ]
    assert [row["body"] for row in journal] == [call[1] for call in api.calls]
    assert journal[-1]["headers"]["Idempotency-Key"] == api.calls[-1][3]


def test_http_response_loss_preserves_exact_attempted_body(tmp_path):
    api, ctx = PublicAPIDouble(), context()
    ctx |= {"evidence_directory": str(tmp_path), "record": {"logical_record_id": "source-000000"}}

    async def lost_response(*args, **kwargs):
        raise TimeoutError("explicit response-loss double")

    api.create = lost_response
    driver = CheckoutDriver(api, api)
    packet = driver.materialize({"payload": {"sku": "FK-one", "payment_outcome": "success"}}, ctx)
    import pytest

    with pytest.raises(TimeoutError):
        asyncio.run(driver.send(packet, ctx, lambda: None))
    journal = [
        json.loads(line) for line in (tmp_path / "api_requests.jsonl").read_text().splitlines()
    ]
    assert journal[-1]["path"] == "/v1/orders"
    assert set(journal[-1]["body"]) == {"quote_id", "session_id", "confirmation_id"}


def test_search_sends_exact_frozen_filters_without_relaxation():
    api, ctx = PublicAPIDouble(), context()
    driver = SearchDriver(api)
    request = {"intent": {"size": "M", "max_price_minor": 10000}, "top_k": 5, "mode": "lexical"}
    packet = driver.materialize({"payload": {"request": request}}, ctx)
    receipt = asyncio.run(driver.send(packet, ctx, lambda: None))
    assert api.calls[0][1] == json.loads(packet.body)
    assert api.calls[0][1]["intent"] == request["intent"]
    assert receipt.status == "accepted"  # accepted no-results is not recommendation success


def test_import_query_and_agent_delegate_without_domain_implementation():
    calls = []

    async def importer(ctx):
        calls.append(ctx)
        return {"raw_to_ready_seconds": 0.025, "stages": {"staging": 0.01}, "logical_digest": "abc"}

    async def adapter(payload, ctx):
        calls.append((payload, ctx))
        return {"observed": True}

    for driver in (ImportDriver(importer), QueryDriver(adapter), AgentDriver(adapter)):
        ctx = context()
        packet = driver.materialize({"payload": {"query_id": "Q1"}}, ctx)
        receipt = asyncio.run(driver.send(packet, ctx, lambda: None))
        assert receipt.status == "accepted"
    assert len(calls) == 3


def test_integrated_workflow_only_uses_public_apis_and_explicit_confirmation():
    calls = []

    class ConversationDouble:
        async def create_session(self, principal, **kwargs):
            calls.append(("session", kwargs))
            return {"session_id": str(uuid4()), "cart_id": str(uuid4()), "cart_version": 0}

        async def turn(self, principal, **kwargs):
            calls.append(("turn", kwargs))
            return {"outcome": "success", "llm_call_count": 0, "products": [{"sku": "FK-one"}]}

        async def update(self, principal, *args, **kwargs):
            calls.append(("cart", kwargs))
            return {"version": 1}

        async def quote(self, principal, *args, **kwargs):
            calls.append(("quote", kwargs))
            return {"quote_id": str(uuid4()), "total_amount_minor": 39900}

        async def checkout(self, principal, *args, **kwargs):
            calls.append(("checkout", kwargs))
            return {"order_id": str(uuid4()), "status": "PENDING"}

    driver = IntegratedDriver(ConversationDouble())
    ctx = context()
    packet = driver.materialize({"payload": {"text": "shirt", "sku": "FK-one"}}, ctx)
    receipt = asyncio.run(driver.send(packet, ctx, lambda: None))
    assert [call[0] for call in calls] == ["session", "turn", "cart", "quote", "checkout"]
    assert calls[-1][1]["confirmed"] is True
    assert calls[-1][1]["expected_cart_version"] == 1
    assert calls[1][1]["mode"] == "fixed"
    assert receipt.details["finality_seconds"] is None
