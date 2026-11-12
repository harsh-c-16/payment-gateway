"""Presentation acceptance with explicit HTTP doubles; live runs are separate evidence."""

import argparse
import copy
import json
from datetime import UTC, datetime

import httpx
import pytest

from projectctl import demo, presentation
from tests.contracts.doubles import common_error
from tests.projectctl.test_demo import DemoProviderDouble, arguments, shopper


def options(tmp_path, *extra):
    parser = argparse.ArgumentParser()
    presentation.add_arguments(parser)
    return parser.parse_args(["--out", str(tmp_path / "checks"), *extra])


class PresentationDouble(DemoProviderDouble):
    def __init__(self):
        super().__init__()
        self.bad = None
        self.gold = None
        self.gold_queries = []
        self.order_snapshot = None

    def __call__(self, request):
        if request.url.path == "/health/ready":
            value = {"status": "ready", "mode": "real"}
            if self.bad == "health":
                value["status"] = "unavailable"
            return httpx.Response(200, json=value)
        if request.url.path == "/v1/analytics/gold/order_fact":
            self.gold_queries.append(dict(request.url.params))
            return httpx.Response(
                200,
                json={
                    "generation": 9,
                    "rows": [self.gold],
                    "queried_at": datetime.now(UTC).isoformat(),
                },
            )
        if request.url.path.startswith("/v1/orders/") and self.order_snapshot:
            self.requests.append((request, None))
            return httpx.Response(200, json=self.order_snapshot)
        response = super().__call__(request)
        if request.url.path.endswith("/turns"):
            value = response.json()
            text = json.loads(request.content)["text"]
            intent = {
                "query_text": text,
                "category": None,
                "size": None,
                "colour": None,
                "material": None,
                "max_price_minor": None,
                "occasion": None,
                "currency": "INR",
                "brand": None,
                "category_path_prefix": None,
            }
            if "watches" in text:
                intent.update(category="watches", max_price_minor=99999)
            if "black" in text:
                intent["colour"] = "black"
                value["products"] = []
            else:
                hit = value["products"][0]
                value["products"] = [
                    dict(
                        hit,
                        sku=f"FK-DEMO-{i}",
                        product_id=f"FK-DEMO-{i}",
                        category=intent["category"],
                        price_minor=99900,
                        dataset_revision=presentation.REVISION,
                        stock_available=10,
                    )
                    for i in range(5)
                ]
                if self.bad == "price" and "watches" in text:
                    value["products"][0]["price_minor"] = 100000
                if self.bad == "stock":
                    value["products"][0]["stock_available"] = 0
                if self.bad == "revision":
                    value["products"][0]["dataset_revision"] = "wrong-dataset"
            if self.bad == "filter" and "watches" in text:
                intent["max_price_minor"] = None
            if self.bad == "timeout":
                value["timings_ms"]["total"] = 3001
            value["intent"] = intent
            return httpx.Response(response.status_code, json=value)
        return response


def test_preflight_checks_real_request_shapes_and_never_purchases(tmp_path):
    provider = PresentationDouble()
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        assert presentation.run(options(tmp_path), client=client, tell=lambda _: None) == 0
    result = json.loads((tmp_path / "checks/checks.json").read_text())
    assert result["status"] == "PASS" and len(result["checks"]) == 6
    assert provider.count("/checkout") == provider.count("/quote") == 0
    assert provider.count("/turns") == 3
    assert not any(request.method == "PUT" for request, _ in provider.requests)
    assert len(list((tmp_path / "checks").glob("*-state.json.http.jsonl"))) == 3


@pytest.mark.parametrize("bad", ["health", "filter", "price", "stock", "revision", "timeout"])
def test_preflight_retains_failed_acceptance_instead_of_claiming_ready(tmp_path, bad):
    provider = PresentationDouble()
    provider.bad = bad
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        assert presentation.run(options(tmp_path), client=client, tell=lambda _: None) == 3
    result = json.loads((tmp_path / "checks/checks.json").read_text())
    assert result["status"] == "INCOMPLETE" and any(c["status"] == "FAIL" for c in result["checks"])
    assert provider.count("/checkout") == 0


def completed_order(tmp_path, status="CONFIRMED"):
    provider = DemoProviderDouble()
    provider.status = status
    path = tmp_path / "original-state.json"
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        assert (
            demo.run(arguments(path), ask=shopper(provider), tell=lambda _: None, client=client)
            == 0
        )
    state = json.loads(path.read_text())
    provider = PresentationDouble()
    provider.ids = copy.deepcopy(
        {
            "session": state["session_id"],
            "cart": state["cart_id"],
            "order": state["order_id"],
            "quote": state["quote"]["quote_id"],
        }
    )
    provider.quote = copy.deepcopy(state["quote"])
    provider.order_snapshot = copy.deepcopy(state["snapshot"])
    provider.gold = {key: value for key, value in state["snapshot"].items() if key != "status"}
    provider.gold.update(namespace="dev", order_status=status, publication_generation=8)
    return provider, path, state


@pytest.mark.parametrize("status", ["CONFIRMED", "CANCELLED"])
def test_order_check_uses_order_creation_day_and_never_changes_original_state(tmp_path, status):
    provider, path, state = completed_order(tmp_path, status)
    # Current wall date is deliberately irrelevant to the Gold cohort.
    state["snapshot"]["created_at"] = "2025-12-31T23:59:59Z"
    provider.order_snapshot["created_at"] = state["snapshot"]["created_at"]
    path.write_text(json.dumps(state))
    original = path.read_bytes()
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        assert (
            presentation.run(
                options(tmp_path, "--state", str(path)), client=client, tell=lambda _: None
            )
            == 0
        )
    assert path.read_bytes() == original
    assert provider.gold_queries == [
        {"namespace": "dev", "date_from": "2025-12-31", "date_to": "2026-01-01"}
    ]
    assert all(request.method == "GET" for request, _ in provider.requests)


@pytest.mark.parametrize(
    "field,value",
    [
        ("total_amount_minor", 1),
        ("quote_id", "wrong-quote"),
        ("namespace", "bench-other"),
        ("order_version", 99),
        ("publication_generation", 10),
        ("user_id", "another-user"),
        ("order_version", True),
    ],
)
def test_gold_order_mismatch_fails(tmp_path, field, value):
    provider, _, state = completed_order(tmp_path)
    provider.gold[field] = value
    with pytest.raises(demo.DemoError):
        presentation.validate_gold({"generation": 9, "rows": [provider.gold]}, state)


def test_absent_or_older_gold_is_pending_and_duplicate_is_rejected(tmp_path):
    provider, _, state = completed_order(tmp_path)
    assert not presentation.validate_gold({"generation": 9, "rows": []}, state)
    old = dict(provider.gold, order_version=state["snapshot"]["order_version"] - 1)
    assert not presentation.validate_gold({"generation": 9, "rows": [old]}, state)
    with pytest.raises(demo.DemoError):
        presentation.validate_gold({"generation": 9, "rows": [provider.gold, provider.gold]}, state)


def test_unaccepted_state_cannot_be_used_to_create_or_submit_purchase(tmp_path):
    provider, path, state = completed_order(tmp_path)
    state["phase"] = "checkout"
    path.write_text(json.dumps(state))
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        assert (
            presentation.run(
                options(tmp_path, "--state", str(path)), client=client, tell=lambda _: None
            )
            == 2
        )
    assert provider.requests == []


def test_missing_gold_field_is_not_equivalent_to_explicit_null(tmp_path):
    provider, _, state = completed_order(tmp_path)
    del provider.gold["failure_code"]
    with pytest.raises(demo.DemoError):
        presentation.validate_gold({"generation": 9, "rows": [provider.gold]}, state)


def test_invalid_health_body_is_retained_as_incomplete(tmp_path):
    provider = PresentationDouble()

    def malformed(request):
        if request.url.path == "/health/ready":
            return httpx.Response(200, json=[])
        return provider(request)

    with httpx.Client(transport=httpx.MockTransport(malformed)) as client:
        assert presentation.run(options(tmp_path), client=client, tell=lambda _: None) == 4
    result = json.loads((tmp_path / "checks/checks.json").read_text())
    assert result["status"] == "INCOMPLETE" and len(result["checks"]) == 6


def test_invalid_state_does_not_dispatch_any_request(tmp_path):
    path = tmp_path / "bad-state.json"
    path.write_text("[]")
    provider = PresentationDouble()
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        assert (
            presentation.run(
                options(tmp_path, "--state", str(path)), client=client, tell=lambda _: None
            )
            == 2
        )
    assert provider.requests == []


def test_transport_outage_cannot_pass_preflight(tmp_path):
    def unavailable(request):
        raise httpx.ConnectError("explicit unavailable-provider double", request=request)

    with httpx.Client(transport=httpx.MockTransport(unavailable)) as client:
        # Keep the production retry budget; remove only test waiting.
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(demo.time, "sleep", lambda _: None)
            assert presentation.run(options(tmp_path), client=client, tell=lambda _: None) == 4
    result = json.loads((tmp_path / "checks/checks.json").read_text())
    assert all(check["status"] == "FAIL" for check in result["checks"])


@pytest.mark.parametrize("intent", [None, {}, {"category": "clothing"}, "extra_filter"])
def test_normal_search_cannot_pass_missing_or_changed_intent(tmp_path, intent):
    provider = PresentationDouble()

    def wrong_intent(request):
        response = provider(request)
        if request.url.path.endswith("/turns") and "formal" in json.loads(request.content)["text"]:
            value = response.json()
            if intent == "extra_filter":
                value["intent"]["category"] = "clothing"
            else:
                value["intent"] = intent
            return httpx.Response(200, json=value)
        return response

    with httpx.Client(transport=httpx.MockTransport(wrong_intent)) as client:
        assert presentation.run(options(tmp_path), client=client, tell=lambda _: None) != 0
    result = json.loads((tmp_path / "checks/checks.json").read_text())
    assert next(c for c in result["checks"] if c["name"] == "search-normal")["status"] == "FAIL"


@pytest.mark.parametrize("fault", ["transport", "503", "429"])
def test_gold_observation_recovers_from_one_temporary_failure(tmp_path, monkeypatch, fault):
    provider, path, _ = completed_order(tmp_path)
    attempts = []
    monkeypatch.setattr(presentation.time, "sleep", lambda _: None)

    def flaky(request):
        if request.url.path == "/v1/analytics/gold/order_fact":
            attempts.append(request)
            if len(attempts) == 1:
                if fault == "transport":
                    raise httpx.ConnectError("explicit transport fault", request=request)
                return httpx.Response(
                    int(fault),
                    stream=httpx.ByteStream(json.dumps(common_error()).encode()),
                    headers={"Retry-After": "0", "Content-Type": "application/json"},
                )
        return provider(request)

    with httpx.Client(transport=httpx.MockTransport(flaky)) as client:
        assert (
            presentation.run(
                options(tmp_path, "--state", str(path)), client=client, tell=lambda _: None
            )
            == 0
        )
    assert len(attempts) == 2
    assert attempts[0].headers == attempts[1].headers
    assert all(request.method == "GET" for request in attempts)


@pytest.mark.parametrize(
    "status,retryable,retry_after,count",
    [
        (503, True, "0", 3),
        (429, True, "0", 3),
        (403, True, "0", 1),
        (503, False, "0", 1),
        (429, True, "600", 1),
    ],
)
def test_gold_retries_are_bounded_and_respect_policy(
    tmp_path, monkeypatch, status, retryable, retry_after, count
):
    provider, path, _ = completed_order(tmp_path)
    calls = []
    monkeypatch.setattr(presentation.time, "sleep", lambda _: None)

    def unavailable(request):
        if request.url.path == "/v1/analytics/gold/order_fact":
            calls.append(request)
            return httpx.Response(
                status,
                stream=httpx.ByteStream(json.dumps(common_error(retryable=retryable)).encode()),
                headers={"Retry-After": retry_after, "Content-Type": "application/json"},
            )
        return provider(request)

    with httpx.Client(transport=httpx.MockTransport(unavailable)) as client:
        assert (
            presentation.run(
                options(tmp_path, "--state", str(path), "--wait-seconds", "1"),
                client=client,
                tell=lambda _: None,
            )
            == 4
        )
    assert len(calls) == count


@pytest.mark.parametrize("with_order", [False, True])
def test_valid_origins_with_trailing_slashes_use_the_same_api_paths(tmp_path, with_order):
    if with_order:
        provider, path, _ = completed_order(tmp_path)
        extra = ["--state", str(path)]
    else:
        provider, extra = PresentationDouble(), []
    args = options(
        tmp_path,
        "--conversation-url",
        "http://127.0.0.1:8001/",
        "--orders-url",
        "http://127.0.0.1:8003/",
        "--analytics-url",
        "http://127.0.0.1:8006/",
        *extra,
    )
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        assert presentation.run(args, client=client, tell=lambda _: None) == 0
