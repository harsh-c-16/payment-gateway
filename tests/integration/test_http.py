import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from benchmarks.integration_clients import ConversationHTTP
from services.conversation.clients import DependencyUnavailable, TransportConfig
from services.conversation.provider_contracts import ContractViolation
from shared.contracts.common import RequestContext


class ContractSpyDouble:
    """Only records validation calls; no real contract compatibility claim."""

    mode = "stub"

    def __init__(self):
        self.calls = []

    def validate(self, endpoint, direction, value):
        self.calls.append((endpoint, direction, value))


def principal():
    return RequestContext(
        namespace="bench-http-test",
        run_id="integration-test",
        user_id="test-user",
        correlation_id="test-correlation",
        request_id=str(uuid4()),
        session_id=str(uuid4()),
    )


def config():
    return TransportConfig(
        "http://explicit-m1-double.invalid", mode="stub", purpose="contract_test"
    )


def test_real_http_rejects_test_transport_or_stub_contracts():
    with pytest.raises(ValueError):
        ConversationHTTP(
            TransportConfig("http://127.0.0.1:1"),
            ContractSpyDouble(),
            transport=httpx.MockTransport(lambda _: httpx.Response(200)),
        )


def test_wire_requests_preserve_identity_keys_and_explicit_confirmation():
    seen, contracts, context = [], ContractSpyDouble(), principal()

    def handler(request):
        seen.append(request)
        statuses = {
            "/v1/sessions": 201,
            "/v1/carts/cart/quote": 201,
            "/v1/carts/cart/checkout": 202,
        }
        return httpx.Response(statuses.get(request.url.path, 200), json={"explicit_double": True})

    async def exercise():
        async with ConversationHTTP(
            config(), contracts, transport=httpx.MockTransport(handler)
        ) as api:
            await api.create_session(context, key="session-key")
            await api.turn(context, text="blue shirt", mode="fixed", key="turn-key")
            await api.update(
                context, "cart", "SKU", quantity=1, expected_cart_version=0, key="cart-key"
            )
            await api.quote(context, "cart", expected_cart_version=1, key="quote-key")
            for _ in range(2):
                await api.checkout(
                    context,
                    "cart",
                    quote_id="quote",
                    expected_cart_version=1,
                    confirmed=True,
                    confirmation_id="confirmation",
                    key="checkout-key",
                )

    asyncio.run(exercise())
    assert len(seen) == 6 and len(contracts.calls) == 12
    assert all(request.headers["X-Namespace"] == context.namespace for request in seen)
    assert all(request.headers["X-Request-ID"] == context.request_id for request in seen)
    assert (
        seen[-1].headers["Idempotency-Key"] == seen[-2].headers["Idempotency-Key"] == "checkout-key"
    )
    assert seen[-1].content == seen[-2].content
    assert json.loads(seen[-1].content)["confirmed"] is True


def test_lost_response_is_unknown_and_not_automatically_retried():
    seen = []

    def handler(request):
        seen.append(request)
        raise httpx.ReadError("explicit response loss", request=request)

    async def exercise():
        async with ConversationHTTP(
            config(), ContractSpyDouble(), transport=httpx.MockTransport(handler)
        ) as api:
            with pytest.raises(DependencyUnavailable) as exc:
                await api.create_session(principal(), key="unchanged-key")
            assert exc.value.outcome_unknown

    asyncio.run(exercise())
    assert len(seen) == 1


def test_redirect_cannot_be_presented_as_a_successful_order():
    async def exercise():
        async with ConversationHTTP(
            config(),
            ContractSpyDouble(),
            transport=httpx.MockTransport(
                lambda _: httpx.Response(307, json={"order_id": "invented"})
            ),
        ) as api:
            with pytest.raises(ContractViolation):
                await api.create_session(principal(), key="key")

    asyncio.run(exercise())
