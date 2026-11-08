"""Adapter lifecycle spies; canonical HTTP behavior is tested in contract suites."""

import asyncio

import pytest

from benchmarks import http_adapters as adapters


@pytest.mark.parametrize(
    "name,operation",
    [
        ("CatalogRequests", "search"),
        ("CatalogRequests", "quote"),
        ("OrdersRequests", "create"),
        ("ConversationRequests", "create_session"),
        ("ConversationRequests", "turn"),
        ("ConversationRequests", "update"),
        ("ConversationRequests", "quote"),
        ("ConversationRequests", "checkout"),
    ],
)
def test_each_call_uses_a_closed_short_lived_client_and_preserves_identity(
    monkeypatch, name, operation
):
    calls = []
    principal, body = object(), {"explicit_input": True}

    class ClientDouble:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            calls.append("open")
            return self

        async def __aexit__(self, *args):
            calls.append("close")

        def __getattr__(self, requested):
            async def invoke(*args, **kwargs):
                assert requested == operation and args == (body, principal)
                assert kwargs == {"key": "same-key"}
                calls.append("request")
                return {"explicit_response": True}

            return invoke

    monkeypatch.setattr(adapters, "ProviderHTTP", ClientDouble)
    monkeypatch.setattr(adapters, "ConversationHTTP", ClientDouble)
    monkeypatch.setattr(adapters, "CatalogClient", lambda http: http)
    monkeypatch.setattr(adapters, "OrdersClient", lambda http: http)
    client = getattr(adapters, name)()
    for _ in range(2):
        result = asyncio.run(getattr(client, operation)(body, principal, key="same-key"))
        assert result == {"explicit_response": True}
    assert calls == ["open", "request", "close"] * 2
