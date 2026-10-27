import asyncio
import copy
import json
import socket
import time

import httpx
import pytest

from services.conversation.clients import (
    AnalyticsClient,
    CatalogClient,
    DependencyUnavailable,
    OrdersClient,
    ProviderHTTP,
    RemoteError,
    TransportConfig,
)
from services.conversation.provider_contracts import (
    ENDPOINTS,
    ContractUnavailable,
    ContractViolation,
    OpenAPIContracts,
)

from .doubles import Chunks, LostOrderResponse, ScriptedProvider, common_error, sse
from .provisional import ROOT, ProvisionalContracts, uid


def http_for(double, **config):
    return ProviderHTTP(
        TransportConfig("http://explicit-p2.test", mode="stub", purpose="contract_test", **config),
        ProvisionalContracts(),
        transport=httpx.MockTransport(double),
        internal_token="synthetic-test-token",
    )


@pytest.mark.parametrize("deadline", [float("nan"), float("inf"), True])
def test_invalid_deadline_never_reaches_transport(deadline, context, pairs):
    double = ScriptedProvider((200, pairs["order-pending"]["response"]))

    async def run():
        async with http_for(double) as http:
            await OrdersClient(http).status(uid(6), context, deadline=deadline)

    with pytest.raises(ValueError, match="deadline"):
        asyncio.run(run())
    assert double.requests == []


def test_retry_snapshots_nested_query_values(context, pairs):
    params = {"synthetic_filter": ["original"]}
    requests = []

    async def changing_caller(request):
        requests.append(str(request.url))
        if len(requests) == 1:
            params["synthetic_filter"].append("changed")
            return httpx.Response(503, json=common_error())
        return httpx.Response(200, json=pairs["order-pending"]["response"])

    async def run():
        async with http_for(changing_caller) as http:
            await http.request("order_status", context, order_id=uid(6), params=params)

    asyncio.run(run())
    assert len(requests) == 2 and requests[0] == requests[1]


async def invoke(http, pair, context):
    catalog, orders, analytics = CatalogClient(http), OrdersClient(http), AnalyticsClient(http)
    body, name = pair["request"], pair["endpoint"]
    if name == "search":
        return await catalog.search(body, context, key="p2-search")
    if name == "product":
        return await catalog.product(pair["response"]["product"]["sku"], context)
    if name == "facets":
        return await catalog.facets(context, dataset_revision="p2-synthetic-not-dataset")
    if name == "quote":
        return await catalog.quote(body, context, key="p2-quote")
    if name == "order_create":
        return await orders.create(body, context, key="p2-order")
    if name == "order_status":
        return await orders.status(uid(6), context)
    if name == "active_manifest":
        return await analytics.active_manifest("gold", context)
    if name == "gold":
        return await analytics.gold(
            "daily_conversion", "2026-10-25", "2026-10-26", context, currency="INR"
        )
    if name == "receipts":
        return await analytics.receipts(context, after_cursor="previous", limit=100)
    if name == "quarantine":
        return await analytics.quarantine(context, cursor="previous", limit=100)
    if name == "replay_create":
        return await analytics.replay(body, context, key="p2-replay")
    if name == "replay_status":
        return await analytics.replay_status(uid(9), context)
    if name == "quote_lookup":
        return await http.request(
            name, context, quote_id=uid(4), params={"user_id": context.user_id}
        )
    if name == "price":
        return await http.request(
            name, context, sku="FK-P2-SYNTHETIC-001", body=body, key="p2-price"
        )
    raise AssertionError("uncovered client method")


PAIR_NAMES = [
    "fewer-than-five-null-facets",
    "no-results",
    "five-hits",
    "product-unknown-stock",
    "empty-facet-coverage",
    "changed-price-authoritative-quote",
    "internal-quote",
    "internal-price",
    "accepted-pending",
    "order-pending",
    "order-confirmed",
    "order-cancelled",
    "order-manual_review",
    "active-generation",
    "gold-empty",
    "receipts-missing-timing",
    "quarantine-empty",
    "replay-accepted",
    "replay-pending",
]


@pytest.mark.parametrize("name", PAIR_NAMES)
def test_each_client_wire_pair(name, pairs, context, tmp_path):
    pair = pairs[name]
    double = ScriptedProvider((ENDPOINTS[pair["endpoint"]].status, pair["response"]))

    async def run():
        async with http_for(double) as http:
            return await invoke(http, pair, context)

    observed = asyncio.run(run())
    assert observed == pair["response"]
    assert len(double.requests) == 1
    sent = double.requests[0]
    assert sent.method == ENDPOINTS[pair["endpoint"]].method
    assert sent.headers["X-Request-ID"] == context.request_id
    assert sent.headers["X-Correlation-ID"] == context.correlation_id
    assert sent.headers["X-Run-ID"] == context.run_id
    assert sent.headers["X-Namespace"] == context.namespace
    assert sent.headers["X-User-ID"] == context.user_id
    assert sent.headers["X-Session-ID"] == context.session_id
    assert sent.headers["X-Trace-ID"] == context.trace_id
    if pair["request"] is not None:
        assert json.loads(sent.content) == pair["request"]
        assert sent.headers["Idempotency-Key"]
    if ENDPOINTS[pair["endpoint"]].internal:
        assert sent.headers["Authorization"] == "Bearer synthetic-test-token"
    if pair["endpoint"] in {"facets", "active_manifest", "gold", "receipts", "quarantine"}:
        assert sent.url.params["namespace"] == context.namespace
    if pair["endpoint"] == "facets":
        assert sent.url.params["dataset_revision"] == "p2-synthetic-not-dataset"
    if pair["endpoint"] == "receipts":
        assert sent.url.params["after_cursor"] == "previous" and sent.url.params["limit"] == "100"
    if pair["endpoint"] == "quote":
        assert observed["total_amount_minor"] == 39900
        assert pair["request"]["lines"][0]["display_price_minor"] == 37900
    journal = {
        "mode": "stub",
        "endpoint": pair["endpoint"],
        "method": sent.method,
        "url": str(sent.url),
        "headers": {key: value for key, value in sent.headers.items() if key != "authorization"},
        "request": pair["request"],
        "response": observed,
    }
    (tmp_path / "request-response.json").write_text(json.dumps(journal, indent=2), encoding="utf-8")


@pytest.mark.parametrize(
    "status,code",
    [
        (409, "CART_VERSION_CONFLICT"),
        (409, "PRODUCT_NOT_SELLABLE"),
        (404, "NOT_FOUND"),
        (503, "DEPENDENCY_UNAVAILABLE"),
    ],
)
def test_business_and_dependency_errors_are_visible(status, code, context):
    double = ScriptedProvider((status, common_error(code, status == 503)))

    async def run():
        async with http_for(double, get_retries=0) as http:
            await OrdersClient(http).status(uid(6), context)

    with pytest.raises(RemoteError) as failure:
        asyncio.run(run())
    assert failure.value.status == status and failure.value.payload.error.code == code
    assert len(double.requests) == 1


def test_get_retry_is_bounded_and_preserves_identity(context, pairs):
    response = pairs["order-pending"]["response"]
    double = ScriptedProvider(
        (503, common_error()), httpx.ConnectError("explicit unavailable"), (200, response)
    )

    async def run():
        async with http_for(double) as http:
            return await OrdersClient(http).status(uid(6), context)

    assert asyncio.run(run()) == response
    assert len(double.requests) == 3
    assert len({tuple(item.headers.items()) for item in double.requests}) == 1
    assert len({str(item.url) for item in double.requests}) == 1


@pytest.mark.parametrize("automatic", [False, True])
def test_lost_response_duplicate_key_and_conflict(automatic, context, pairs):
    pair = pairs["accepted-pending"]
    double = LostOrderResponse(pair["response"])

    async def run():
        async with http_for(double, mutation_retries=int(automatic)) as http:
            client = OrdersClient(http)
            if not automatic:
                with pytest.raises(DependencyUnavailable) as failure:
                    await client.create(pair["request"], context, key="same-purchase")
                assert failure.value.outcome_unknown is True
            first = await client.create(pair["request"], context, key="same-purchase")
            duplicate = await client.create(pair["request"], context, key="same-purchase")
            assert first == duplicate == pair["response"]
            changed = {**pair["request"], "quote_id": uid(99)}
            with pytest.raises(RemoteError) as conflict:
                await client.create(changed, context, key="same-purchase")
            assert conflict.value.status == 409

    asyncio.run(run())
    assert double.effects == 1
    assert len({request.headers["Idempotency-Key"] for request in double.requests}) == 1
    assert len({request.content for request in double.requests[:3]}) == 1


@pytest.mark.parametrize("operation", ["get", "search"])
def test_absolute_deadline_includes_body_and_never_extends_for_retry(operation, context, pairs):
    async def slow(request):
        await asyncio.sleep(0.2)
        return httpx.Response(200, json=pairs["five-hits"]["response"])

    double = ScriptedProvider(slow)

    async def run():
        async with http_for(double) as http:
            deadline = time.monotonic() + 0.025
            if operation == "get":
                await OrdersClient(http).status(uid(6), context, deadline=deadline)
            else:
                await CatalogClient(http).search(
                    pairs["five-hits"]["request"], context, key="search", deadline=deadline
                )

    start = time.monotonic()
    with pytest.raises(DependencyUnavailable):
        asyncio.run(run())
    assert time.monotonic() - start < 0.15
    assert len(double.requests) == 1


def test_retry_after_cannot_be_shortened_to_fit_deadline(context):
    double = ScriptedProvider((429, common_error("RATE_LIMITED"), {"Retry-After": "10"}))

    async def run():
        async with http_for(double) as http:
            await OrdersClient(http).status(uid(6), context)

    with pytest.raises(RemoteError) as failure:
        asyncio.run(run())
    assert failure.value.retry_after == 10 and len(double.requests) == 1


@pytest.mark.parametrize("purpose", ["integration", "benchmark"])
def test_stubs_cannot_be_configured_for_real_runs(purpose):
    with pytest.raises(ValueError, match="contract tests"):
        TransportConfig("http://explicit-p2.test", mode="stub", purpose=purpose)


def test_real_mode_rejects_injected_transport_or_provisional_contracts():
    with pytest.raises(ValueError, match="real transport"):
        ProviderHTTP(TransportConfig("http://localhost:1"), ProvisionalContracts())
    with pytest.raises(ValueError, match="real transport"):
        ProviderHTTP(
            TransportConfig("http://localhost:1"),
            OpenAPIContracts(ROOT / "contracts/http"),
            transport=httpx.MockTransport(ScriptedProvider()),
        )


def test_real_mode_stopped_provider_never_returns_fixture(context):
    # A bound, non-listening TCP socket reserves the port and deterministically refuses connections.
    with socket.socket() as stopped:
        stopped.bind(("127.0.0.1", 0))
        port = stopped.getsockname()[1]

        async def run():
            config = TransportConfig(f"http://127.0.0.1:{port}", timeout_seconds=0.1, get_retries=0)
            async with ProviderHTTP(config, OpenAPIContracts(ROOT / "contracts/http")) as http:
                await CatalogClient(http).product("FK-P2-SYNTHETIC-001", context)

        with pytest.raises(DependencyUnavailable, match="no fallback"):
            asyncio.run(run())


def test_real_success_without_canonical_contract_is_rejected():
    contracts = OpenAPIContracts(ROOT / "contracts/http")
    with pytest.raises(ContractUnavailable):
        contracts.validate(ENDPOINTS["order_status"], "response", {"status": "CONFIRMED"})


@pytest.mark.parametrize("alteration", ["user", "request", "session", "key"])
def test_invalid_identity_or_missing_key_never_sends(alteration, context, pairs):
    body = copy.deepcopy(pairs["five-hits"]["request"])
    key = "p2-search"
    if alteration == "user":
        body["user_id"] = "another-principal"
    elif alteration in {"request", "session"}:
        body[alteration + "_id"] = uid(99)
    else:
        key = None
    double = ScriptedProvider()

    async def run():
        async with http_for(double) as http:
            await CatalogClient(http).search(body, context, key=key)

    with pytest.raises(ValueError):
        asyncio.run(run())
    assert double.requests == []


@pytest.mark.parametrize("limit", [0, 1001, "10", True])
def test_analytics_bounds_before_transport(limit, context):
    double = ScriptedProvider()

    async def run():
        async with http_for(double) as http:
            await AnalyticsClient(http).receipts(context, limit=limit)

    with pytest.raises(ValueError):
        asyncio.run(run())
    assert double.requests == []


def test_sse_current_snapshot_version_updates_and_reconnect(context, pairs):
    pending = pairs["sse-pending"]["response"]
    confirmed = pairs["sse-confirmed"]["response"]
    frames = sse(pending) + sse(confirmed) + sse(confirmed) + sse(pending)
    streams = [Chunks([frames[:40], frames[40:]]), Chunks([sse(confirmed)])]
    requests = []

    async def provider(request):
        requests.append(request)
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=streams[len(requests) - 1]
        )

    async def run():
        async with http_for(provider) as http:
            client = OrdersClient(http)
            first = [item async for item in client.events(uid(6), context)]
            second = [item async for item in client.events(uid(6), context, last_event_id=1)]
            return first, second

    first, second = asyncio.run(run())
    assert [item["order_version"] for item in first] == [1, 4]
    assert [item["status"] for item in second] == ["CONFIRMED"]
    assert "Last-Event-ID" not in requests[0].headers
    assert requests[1].headers["Last-Event-ID"] == "1"
    assert all(stream.closed for stream in streams)


@pytest.mark.parametrize("corruption", ["bad-version", "bad-json", "too-large", "wrong-order"])
def test_sse_rejects_corruption(corruption, context, pairs):
    snapshot = copy.deepcopy(pairs["sse-pending"]["response"])
    if corruption == "wrong-order":
        snapshot["order_id"] = uid(99)
    frame = sse(snapshot, event_id=99 if corruption == "bad-version" else None)
    if corruption == "bad-json":
        frame = b"id: 1\ndata: {bad}\n\n"
    if corruption == "too-large":
        frame = b"data: " + b"x" * 65537

    async def provider(request):
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=Chunks([frame])
        )

    async def run():
        async with http_for(provider) as http:
            return [item async for item in OrdersClient(http).events(uid(6), context)]

    with pytest.raises(ContractViolation):
        asyncio.run(run())


@pytest.mark.parametrize("corruption", ["missing-field", "money-string", "money-float"])
def test_client_rejects_corrupt_success_response(corruption, context, pairs):
    response = copy.deepcopy(pairs["changed-price-authoritative-quote"]["response"])
    if corruption == "missing-field":
        response["total_amunt_minor"] = response.pop("total_amount_minor")
    else:
        response["total_amount_minor"] = "39900" if corruption == "money-string" else 39900.0
    double = ScriptedProvider((201, response))

    async def run():
        async with http_for(double) as http:
            await CatalogClient(http).quote(
                pairs["changed-price-authoritative-quote"]["request"], context, key="quote"
            )

    with pytest.raises(ContractViolation):
        asyncio.run(run())
    assert len(double.requests) == 1


def test_hard_size_constraint_is_sent_once_and_never_relaxed(context, pairs):
    request = copy.deepcopy(pairs["five-hits"]["request"])
    request["intent"].update(category="clothing", size="M")
    double = ScriptedProvider((200, pairs["no-results"]["response"]))

    async def run():
        async with http_for(double) as http:
            return await CatalogClient(http).search(request, context, key="strict-size")

    assert asyncio.run(run())["hits"] == []
    assert len(double.requests) == 1
    assert json.loads(double.requests[0].content)["intent"]["size"] == "M"


def test_mutation_503_is_not_retried_by_default(context, pairs):
    double = ScriptedProvider((503, common_error()))

    async def run():
        async with http_for(double) as http:
            await OrdersClient(http).create(
                pairs["accepted-pending"]["request"], context, key="same-key"
            )

    with pytest.raises(RemoteError) as failure:
        asyncio.run(run())
    assert failure.value.status == 503 and len(double.requests) == 1


def test_deadline_bounds_slow_body_stream(context, pairs):
    class SlowBody(Chunks):
        async def __aiter__(self):
            for chunk in self.chunks:
                await asyncio.sleep(0.025)
                yield chunk

    payload = json.dumps(pairs["order-pending"]["response"]).encode()
    stream = SlowBody([payload[:10], payload[10:]])

    async def provider(request):
        return httpx.Response(200, headers={"content-type": "application/json"}, stream=stream)

    async def run():
        async with http_for(provider) as http:
            await OrdersClient(http).status(uid(6), context, deadline=time.monotonic() + 0.04)

    with pytest.raises(DependencyUnavailable):
        asyncio.run(run())
    assert stream.closed


def test_expired_sse_deadline_never_opens_transport(context):
    double = ScriptedProvider()

    async def run():
        async with http_for(double) as http:
            return [
                item async for item in http.events(uid(6), context, deadline=time.monotonic() - 1)
            ]

    with pytest.raises(DependencyUnavailable):
        asyncio.run(run())
    assert double.requests == []


@pytest.mark.parametrize("frame", [b"", b'id: 1\ndata: {"status":'])
def test_empty_or_truncated_sse_is_not_a_success(frame, context):
    async def provider(request):
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, stream=Chunks([frame])
        )

    async def run():
        async with http_for(provider) as http:
            return [item async for item in http.events(uid(6), context)]

    with pytest.raises((DependencyUnavailable, ContractViolation)):
        asyncio.run(run())


@pytest.mark.parametrize(
    "headers,params",
    [
        ({"x-user-id": "override"}, None),
        ({"X-Request-ID": uid(99)}, None),
        ({"Idempotency-Key": "override"}, None),
        ({"Authorization": "Bearer override"}, None),
        (None, {"namespace": "dev"}),
        (None, {"user_id": "override"}),
    ],
)
def test_extra_transport_fields_cannot_override_identity(headers, params, context):
    double = ScriptedProvider()

    async def run():
        async with http_for(double) as http:
            await http.request(
                "order_status", context, order_id=uid(6), headers=headers, params=params
            )

    with pytest.raises(ValueError, match="identity|authorization"):
        asyncio.run(run())
    assert double.requests == []
