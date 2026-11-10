"""Canonical wire schemas with explicit HTTP doubles; no live-provider claim."""

import argparse
import copy
import json
import os
import threading
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from projectctl import demo
from services.conversation.provider_contracts import ContractViolation
from tests.contracts.doubles import common_error
from tests.conversation.workflow_doubles import example


class DemoProviderDouble:
    def __init__(self):
        self.ids = {name: str(uuid4()) for name in ("session", "cart", "quote", "order")}
        self.requests, self.effects = [], {}
        self.lost, self.status, self.search_outcome = {}, "CONFIRMED", "success"
        self.model_calls = 0
        self.cart_version = 0
        self.expired, self.wrong_user, self.bad_hit = False, False, False
        self.quote_count = 0
        self.order_version = 2
        self.on_cart_read = None
        self.sku = "FIXTURE-DEMO-SKU"

    def __call__(self, request):
        body = json.loads(request.content) if request.content else None
        self.requests.append((request, body))
        path, code = request.url.path, 200
        now = datetime.now(UTC)
        timestamp = now.isoformat().replace("+00:00", "Z")
        user = request.headers["X-User-ID"]
        kind = next((name for name in self.lost if name in path), None)
        scope = (path, request.headers.get("Idempotency-Key"))
        if request.method != "GET" and scope in self.effects:
            prior_body, code, value = self.effects[scope]
            assert body == prior_body
        elif path == "/v1/sessions":
            code, value = (
                201,
                {"session_id": self.ids["session"], "cart_id": self.ids["cart"], "cart_version": 0},
            )
        elif path.endswith("/turns"):
            assert body["mode"] == "fixed"
            assert body["request_id"] == request.headers["X-Request-ID"]
            hit = example("search")["hits"][0]
            hit.update(sku=self.sku, product_id=self.sku, title="Synthetic demo product")
            if self.bad_hit:
                hit.pop("price_minor")
            value = {
                "turn_id": str(uuid4()),
                "response_text": "Explicit demo double",
                "intent": None,
                "search_id": str(uuid4()),
                "products": [hit] if self.search_outcome == "success" else [],
                "outcome": self.search_outcome,
                "extractor_source": "rules",
                "llm_call_count": self.model_calls,
                "proposed_action": None,
                "timings_ms": {
                    "parse": 0.1,
                    "llm": None,
                    "search": 0.1,
                    "compose": 0.1,
                    "total": 0.3,
                },
            }
        elif "/items/" in path or path == "/v1/carts/" + self.ids["cart"]:
            if request.method == "PUT":
                assert body["expected_cart_version"] == self.cart_version
                self.cart_version += 1
            elif self.on_cart_read:
                self.on_cart_read()
            value = {
                "cart_id": self.ids["cart"],
                "session_id": self.ids["session"],
                "user_id": user,
                "version": self.cart_version,
                "lines": [{"sku": self.sku, "quantity": 1, "display_price_minor": None}],
                "updated_at": timestamp,
            }
        elif path.endswith("/quote"):
            self.quote_count += 1
            if self.quote_count > 1:
                self.ids["quote"] = str(uuid4())
            code = 201
            value = {
                "quote_id": self.ids["quote"],
                "cart_id": self.ids["cart"],
                "cart_version": body["expected_cart_version"],
                "user_id": user,
                "lines": [
                    {
                        "sku": self.sku,
                        "quantity": 1,
                        "unit_price_minor": 37900,
                        "line_total_minor": 37900,
                        "catalog_version": 1,
                    }
                ],
                "currency": "INR",
                "total_amount_minor": 37900,
                "created_at": timestamp,
                "expires_at": (now + timedelta(seconds=-1 if self.expired else 60)).isoformat(),
            }
            self.quote = copy.deepcopy(value)
        elif path.endswith("/checkout"):
            assert body["confirmed"] is True
            assert body["quote_id"] == self.ids["quote"]
            assert body["expected_cart_version"] == self.cart_version
            code, value = (
                202,
                {
                    "order_id": self.ids["order"],
                    "status": "PENDING",
                    "status_url": "/v1/orders/" + self.ids["order"],
                },
            )
        elif path.startswith("/v1/orders/"):
            value = {
                "order_id": self.ids["order"],
                "quote_id": self.ids["quote"],
                "session_id": self.ids["session"],
                "user_id": "other" if self.wrong_user else user,
                "status": self.status,
                "order_version": self.order_version,
                "lines": self.quote["lines"],
                "total_amount_minor": self.quote["total_amount_minor"],
                "currency": "INR",
                "created_at": timestamp,
                "updated_at": timestamp,
                "reservation_id": str(uuid4()),
                "payment_id": str(uuid4()),
                "failure_code": "DECLINED" if self.status == "CANCELLED" else None,
            }
        else:
            raise AssertionError("unplanned demo endpoint: " + path)
        if request.method != "GET":
            self.effects[scope] = copy.deepcopy((body, code, value))
        if kind and self.lost[kind]:
            self.lost[kind] -= 1
            raise httpx.ReadTimeout("explicit lost response", request=request)
        return httpx.Response(code, json=value)

    def count(self, suffix):
        return sum(request.url.path.endswith(suffix) for request, _ in self.requests)


def arguments(path, *extra):
    parser = argparse.ArgumentParser()
    demo.add_arguments(parser)
    return parser.parse_args(["--state", str(path), "--query", "shirt", *extra])


def resume(path, *extra):
    parser = argparse.ArgumentParser()
    demo.add_arguments(parser)
    return parser.parse_args(["--resume", str(path), *extra])


def shopper(provider, *, confirm=True):
    def ask(prompt):
        if "Select product" in prompt or "Quantity" in prompt:
            return "1"
        if "Type CONFIRM" in prompt:
            assert provider.count("/checkout") == 0
            return "CONFIRM " + provider.ids["quote"] if confirm else ""
        if "Search products" in prompt:
            return "shirt"
        raise AssertionError("unexpected prompt: " + prompt)

    return ask


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(demo.time, "sleep", lambda _: None)
    provider = DemoProviderDouble()
    with httpx.Client(transport=httpx.MockTransport(provider)) as client:
        yield tmp_path / "state.json", provider, client


@pytest.mark.parametrize("status", ["CONFIRMED", "CANCELLED"])
def test_connected_flow_identity_quote_and_explicit_confirmation(setup, status):
    path, provider, client = setup
    provider.status = status
    output = []
    assert demo.run(arguments(path), ask=shopper(provider), tell=output.append, client=client) == 0
    state = json.loads(path.read_text())
    assert state["phase"] == "done" and state["final_status"] == status
    assert any("TOTAL: INR 379.00" in line for line in output)
    assert provider.count("/checkout") == 1 and provider.count("/quote") == 1
    requests = [request for request, _ in provider.requests]
    for name in ("X-User-ID", "X-Namespace", "X-Run-ID", "X-Correlation-ID"):
        assert len({request.headers[name] for request in requests}) == 1
    assert all(
        request.headers["X-Session-ID"] == provider.ids["session"] for request in requests[1:]
    )
    assert requests[-1].url.port == 8003
    assert "Authorization" not in path.with_suffix(".json.http.jsonl").read_text()
    assert (
        demo.run(
            resume(path),
            ask=lambda _: pytest.fail("completed demo prompted"),
            tell=output.append,
            client=client,
        )
        == 0
    )
    assert provider.count("/checkout") == 1


def test_declining_confirmation_never_submits_checkout(setup):
    path, provider, client = setup
    assert (
        demo.run(
            arguments(path),
            ask=shopper(provider, confirm=False),
            tell=lambda _: None,
            client=client,
        )
        == 0
    )
    assert provider.count("/checkout") == 0
    assert json.loads(path.read_text())["phase"] == "confirm"


@pytest.mark.parametrize("lost_step", ["sessions", "items", "quote", "checkout"])
def test_lost_mutation_response_resumes_exact_identity_body_and_key(setup, lost_step):
    path, provider, client = setup
    provider.lost[lost_step] = 3
    with pytest.raises(demo.DemoError, match="Resume this state"):
        demo.run(arguments(path), ask=shopper(provider), tell=lambda _: None, client=client)
    saved = json.loads(path.read_text())
    if lost_step == "checkout":
        # Acceptance uncertainty remains recoverable after quote expiry, without
        # a second confirmation or a new purchase identity.
        saved["quote"]["expires_at"] = "2020-01-01T00:00:00Z"
        path.write_text(json.dumps(saved))
    assert demo.run(resume(path), ask=shopper(provider), tell=lambda _: None, client=client) == 0
    retries = [
        (request, body)
        for request, body in provider.requests
        if lost_step in request.url.path
        and request.method != "GET"
        and not request.url.path.endswith("/turns")
    ]
    assert len(retries) == 4
    assert all(
        dict(request.headers) == dict(retries[0][0].headers) and body == retries[0][1]
        for request, body in retries
    )
    assert provider.cart_version == 1
    assert len([scope for scope in provider.effects if scope[0].endswith("/checkout")]) == 1


def test_semantic_search_failure_is_visible_and_next_search_gets_new_identity(setup):
    path, provider, client = setup
    provider.search_outcome = "dependency_error"
    with pytest.raises(demo.DemoError, match="Catalogue unavailable"):
        demo.run(arguments(path), ask=shopper(provider), tell=lambda _: None, client=client)
    assert provider.count("/checkout") == 0
    provider.search_outcome = "success"
    assert demo.run(resume(path), ask=shopper(provider), tell=lambda _: None, client=client) == 0
    turns = [request for request, _ in provider.requests if request.url.path.endswith("/turns")]
    assert len(turns) == 2
    assert turns[0].headers["Idempotency-Key"] != turns[1].headers["Idempotency-Key"]


def test_stale_cart_cannot_reuse_quote_confirmation(setup):
    path, provider, client = setup
    provider.on_cart_read = lambda: setattr(provider, "cart_version", provider.cart_version + 1)
    with pytest.raises(demo.DemoError, match="Cart changed"):
        demo.run(arguments(path), ask=shopper(provider), tell=lambda _: None, client=client)
    assert provider.count("/checkout") == 0


def test_expiry_requires_new_quote_and_fresh_human_confirmation(setup):
    path, provider, client = setup
    provider.expired = True
    expired_quote = provider.ids["quote"]
    confirmations = []

    def ask(prompt):
        if "Type REQUOTE" in prompt:
            provider.expired = False
            return "REQUOTE"
        if "Type CONFIRM" in prompt:
            confirmations.append(provider.ids["quote"])
        return shopper(provider)(prompt)

    assert demo.run(arguments(path), ask=ask, tell=lambda _: None, client=client) == 0
    assert provider.quote_count == 2 and confirmations == [provider.ids["quote"]]
    assert confirmations[0] != expired_quote


def test_expiry_during_human_confirmation_requires_requote_and_new_confirmation(setup):
    path, provider, _ = setup
    confirmations, rejected = [], []

    def response(request):
        if request.url.path.endswith("/checkout") and not rejected:
            rejected.append(request)
            return httpx.Response(409, json=common_error("QUOTE_EXPIRED", False))
        return provider(request)

    def ask(prompt):
        if "Type REQUOTE" in prompt:
            return "REQUOTE"
        if "Type CONFIRM" in prompt:
            confirmations.append(provider.ids["quote"])
            return "CONFIRM " + provider.ids["quote"]
        return shopper(provider)(prompt)

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        assert demo.run(arguments(path), ask=ask, tell=lambda _: None, client=client) == 0
    assert len(rejected) == 1 and len(set(confirmations)) == 2
    accepted = next(r for r, _ in provider.requests if r.url.path.endswith("/checkout"))
    assert accepted.headers["Idempotency-Key"] != rejected[0].headers["Idempotency-Key"]
    assert (
        json.loads(accepted.content)["confirmation_id"]
        != json.loads(rejected[0].content)["confirmation_id"]
    )


@pytest.mark.parametrize("outcome", ["success", "clarification"])
def test_empty_results_and_clarification_allow_leaving_without_purchase(setup, outcome):
    path, provider, _ = setup

    def response(request):
        result = provider(request)
        if request.url.path.endswith("/turns"):
            value = result.json()
            value.update(outcome=outcome, products=[])
            return httpx.Response(200, json=value)
        return result

    with httpx.Client(transport=httpx.MockTransport(response)) as client:
        assert demo.run(arguments(path), ask=lambda _: "q", tell=lambda _: None, client=client) == 0
    assert provider.count("/checkout") == provider.count("/quote") == 0


@pytest.mark.parametrize("problem", ["wrong_user", "bad_hit", "model_calls"])
def test_provider_identity_schema_and_zero_model_policy_fail_closed(setup, problem):
    path, provider, client = setup
    setattr(provider, problem, 1 if problem == "model_calls" else True)
    with pytest.raises((demo.DemoError, ContractViolation)):
        demo.run(arguments(path), ask=shopper(provider), tell=lambda _: None, client=client)
    if problem != "wrong_user":
        assert provider.count("/checkout") == 0


def test_manual_review_remains_unresolved_and_resume_only_observes(setup):
    path, provider, client = setup
    provider.status = "MANUAL_REVIEW"
    with pytest.raises(demo.DemoError, match="manual review"):
        demo.run(arguments(path), ask=shopper(provider), tell=lambda _: None, client=client)
    assert json.loads(path.read_text())["phase"] == "status"
    provider.status = "CONFIRMED"
    provider.order_version += 1
    assert (
        demo.run(
            resume(path),
            ask=lambda _: pytest.fail("status resume prompted"),
            tell=lambda _: None,
            client=client,
        )
        == 0
    )
    assert provider.count("/checkout") == 1


def test_resume_cannot_change_principal_or_overwrite_state(setup):
    path, provider, client = setup
    demo.run(
        arguments(path), ask=shopper(provider, confirm=False), tell=lambda _: None, client=client
    )
    with pytest.raises(demo.DemoError, match="cannot change"):
        demo.run(resume(path, "--user-id", "other"), client=client)
    with pytest.raises(demo.DemoError, match="already exists"):
        demo.run(arguments(path), client=client)


def test_mutation_conflict_is_not_retried(setup):
    path, provider, _ = setup

    def conflict(request):
        if "/items/" in request.url.path:
            provider.requests.append((request, json.loads(request.content)))
            return httpx.Response(409, json=common_error("CART_VERSION_CONFLICT", False))
        return provider(request)

    with httpx.Client(transport=httpx.MockTransport(conflict)) as client:
        with pytest.raises(demo.DemoError, match="CART_VERSION_CONFLICT"):
            demo.run(arguments(path), ask=shopper(provider), tell=lambda _: None, client=client)
    assert len([r for r, _ in provider.requests if "/items/" in r.url.path]) == 1


def test_demo_entry_point_help(capsys):
    from projectctl.cli import main

    with pytest.raises(SystemExit) as result:
        main(["demo", "--help"])
    assert result.value.code == 0
    assert "--resume" in capsys.readouterr().out


@pytest.mark.skipif(os.name != "nt", reason="Windows file-sharing semantics only")
def test_state_save_survives_a_brief_real_windows_reader(tmp_path):
    path = tmp_path / "state.json"
    journal = demo.Journal(path, {"phase": "checkout", "key": "original-retry-key"})
    journal.save()
    reader = path.open("r", encoding="utf-8")
    release = threading.Timer(0.08, reader.close)
    release.start()
    try:
        journal.advance("status", order_id="original-order")
    finally:
        reader.close()
        release.join()
    assert json.loads(path.read_text()) == {
        "phase": "status",
        "key": "original-retry-key",
        "order_id": "original-order",
    }
    assert not path.with_suffix(".json.tmp").exists()


def test_state_save_permission_failure_cannot_dispatch_a_mutation(setup, monkeypatch):
    path, provider, client = setup

    def denied(*args):
        raise PermissionError("explicit persistent permission failure")

    monkeypatch.setattr(demo.Path, "replace", denied)
    with pytest.raises(PermissionError):
        demo.run(arguments(path), client=client)
    assert provider.requests == []
