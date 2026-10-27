import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from time import monotonic
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from services.conversation.app import create_app
from services.conversation.errors import ServiceError
from services.conversation.state import ConversationState
from services.conversation.workflow import FixedWorkflow, compose_response
from shared.contracts.conversation import (
    CartQuoteRequest,
    CartUpdateRequest,
    CheckoutRequest,
    TurnRequest,
)

from .workflow_doubles import FIXTURE, WorkflowProviderDouble, seed_workflow_fixture


@pytest.fixture
def provider():
    return WorkflowProviderDouble()


@pytest.fixture
def workflow(state, provider):
    return FixedWorkflow(state, provider.gateway())


def setup_cart(state, context):
    created = state.create_session(context, "session")
    state.update_cart(
        created.cart_id,
        "SYN-M-BLUE",
        CartUpdateRequest(quantity=2, expected_cart_version=0),
        context,
        "edit",
    )
    return created


def quoted(workflow, context):
    created = setup_cart(workflow.state, context)
    quote = workflow.request_quote(
        created.cart_id, CartQuoteRequest(expected_cart_version=1), context, "quote"
    )
    body = CheckoutRequest(
        quote_id=quote["quote_id"],
        expected_cart_version=1,
        confirmed=True,
        confirmation_id=str(uuid4()),
    )
    return created, quote, body


def turn(workflow, context, text, *, key="turn"):
    created = workflow.state.create_session(context, "session")
    request = TurnRequest(request_id=context.request_id, text=text)
    return workflow.dispatch_turn(created.session_id, request, context, key)


def assert_code(code, fn):
    with pytest.raises(ServiceError) as error:
        fn()
    assert error.value.body.code == code
    return error.value


def test_turn_persists_authoritative_products_one_search_and_same_request_replay(
    workflow, context, provider, database
):
    first = turn(workflow, context, "blue cotton clothing size M under 500 rupees")
    second = turn(workflow, context, "blue cotton clothing size M under 500 rupees")
    assert first == second
    assert first.products[0]["sku"] == "SYN-M-BLUE"
    assert first.products[0]["price_minor"] == 37900
    assert first.proposed_action is None and first.llm_call_count == 0
    assert first.timings_ms.llm is None
    assert provider.count("/v1/search") == 1 and provider.model.attempts == 0
    with database.transaction() as tx:
        assert tx.execute("SELECT count(*) AS n FROM turns").fetchone()["n"] == 1
        assert (
            tx.execute(
                "SELECT count(*) AS n FROM p6_test_event_capture "
                "WHERE event_type='CONVERSATION_TURN'"
            ).fetchone()["n"]
            == 1
        )


def test_structured_bypasses_extractor_and_zero_bound_stays_zero(
    workflow, context, provider, monkeypatch
):
    def forbidden(*args):
        raise AssertionError("structured controls cannot extract intent")

    monkeypatch.setattr("services.conversation.workflow.extract_intent", forbidden)
    context = context.model_copy(update={"session_id": str(uuid4())})
    result = workflow.structured_search(
        {"category": "clothing", "max_price_minor": 0}, context, key="structured"
    )
    assert result["hits"] == []
    request = next(r for r in provider.requests if r.url.path == "/v1/search")
    assert json.loads(request.content)["intent"]["max_price_minor"] == 0
    assert provider.model.attempts == 0


def test_structured_unknown_filter_never_searches(workflow, context, provider):
    assert_code(
        "UNSUPPORTED_FILTER",
        lambda: workflow.structured_search({"colour": "ultraviolet"}, context, key="structured"),
    )
    assert provider.count("/v1/search") == 0


@pytest.mark.parametrize(
    "attribute,value", [("price_minor", 999999), ("size", None), ("dataset_revision", "other")]
)
def test_provider_violating_hard_filters_fails_closed(
    workflow, context, provider, attribute, value
):
    provider.tamper_search = lambda r: r["hits"][0].update({attribute: value})
    result = turn(workflow, context, "blue cotton clothing size M under 500 rupees")
    assert result.outcome == "dependency_error" and result.products == []
    assert provider.count("/v1/search") == 1


def test_total_deadline_includes_dictionary_time_and_limits_one_search(workflow, context, provider):
    provider.facet_delay = 1.25
    provider.search_delay = 2
    started = monotonic()
    result = turn(workflow, context, "clothing")
    elapsed = monotonic() - started
    assert result.outcome == "dependency_error"
    assert 2.8 <= elapsed < 3.5
    search = next(r for r in provider.requests if r.url.path == "/v1/search")
    assert search.extensions["timeout"]["read"] < 1.8
    assert provider.count("/v1/search") == 1 and result.llm_call_count == 0


def test_authoritative_quote_and_stale_confirmation(workflow, context, provider):
    created, quote, body = quoted(workflow, context)
    assert quote["total_amount_minor"] == 79800  # provider changed price from search 37900
    assert "79800" in compose_response(action_status=quote)
    workflow.state.update_cart(
        created.cart_id,
        "SYN-M-BLUE",
        CartUpdateRequest(quantity=1, expected_cart_version=1),
        context,
        "edit2",
    )
    assert_code(
        "CART_VERSION_CONFLICT",
        lambda: workflow.checkout_cart(created.cart_id, body, context, "checkout"),
    )
    assert provider.count("/v1/orders") == 0


@pytest.mark.parametrize(
    "field,value",
    [("cart_id", str(uuid4())), ("cart_version", 99), ("user_id", "someone-else"), ("lines", [])],
)
def test_mismatched_provider_quote_cannot_bind_confirmation(
    workflow, context, provider, field, value
):
    created = setup_cart(workflow.state, context)
    provider.tamper_quote = lambda q: q.update({field: value})
    assert_code(
        "DEPENDENCY_UNAVAILABLE",
        lambda: workflow.request_quote(
            created.cart_id, CartQuoteRequest(expected_cart_version=1), context, "quote"
        ),
    )
    with workflow.state.database.transaction() as tx:
        assert tx.execute("SELECT quote_id FROM carts").fetchone()["quote_id"] is None


def test_empty_cart_and_wrong_version_quote_never_call_provider(workflow, context, provider):
    created = workflow.state.create_session(context, "session")
    for version, code in [(0, "VALIDATION_ERROR"), (1, "CART_VERSION_CONFLICT")]:
        assert_code(
            code,
            lambda version=version: workflow.request_quote(
                created.cart_id, CartQuoteRequest(expected_cart_version=version), context, "quote"
            ),
        )
    assert provider.count("/v1/quotes") == 0


def test_lost_checkout_response_survives_restart_and_expiry_with_same_order(
    workflow, context, provider, database
):
    created, quote, body = quoted(workflow, context)
    provider.lose_order_response = True
    error = assert_code(
        "DEPENDENCY_UNAVAILABLE",
        lambda: workflow.checkout_cart(created.cart_id, body, context, "checkout"),
    )
    assert error.body.details["outcome"] == "unknown"
    assert len(provider.accepted) == 1
    assert_code(
        "ILLEGAL_STATE",
        lambda: workflow.state.update_cart(
            created.cart_id,
            "SYN-M-BLUE",
            CartUpdateRequest(quantity=1, expected_cart_version=1),
            context,
            "edit2",
        ),
    )
    with database.transaction() as tx:
        old = {**quote, "expires_at": (datetime.now(UTC) - timedelta(minutes=1)).isoformat()}
        tx.execute("UPDATE carts SET quote_payload=%s", (Jsonb(old),))
    restarted = FixedWorkflow(
        ConversationState(database, events=workflow.state.events), provider.gateway()
    )
    accepted = restarted.checkout_cart(created.cart_id, body, context, "checkout")
    assert accepted["status"] == "PENDING"
    assert restarted.checkout_cart(created.cart_id, body, context, "checkout") == accepted
    assert restarted.checkout_cart(created.cart_id, body, context, "new-key") == accepted
    assert len(provider.accepted) == 1 and provider.model.attempts == 0
    requests = [r for r in provider.requests if r.url.path == "/v1/orders"]
    assert len({r.headers["Idempotency-Key"] for r in requests}) == 1
    assert len({r.content for r in requests}) == 1


def test_checkout_input_conflict_and_unconfirmed_rejection(workflow, context, provider):
    created, quote, body = quoted(workflow, context)
    accepted = workflow.checkout_cart(created.cart_id, body, context, "checkout")
    assert_code(
        "IDEMPOTENCY_CONFLICT",
        lambda: workflow.checkout_cart(
            created.cart_id,
            body.model_copy(update={"confirmation_id": str(uuid4())}),
            context,
            "checkout",
        ),
    )
    with pytest.raises(ValidationError):
        CheckoutRequest(**{**body.model_dump(), "confirmed": False})
    assert accepted["status"] == "PENDING" and len(provider.accepted) == 1


def test_quote_expired_before_first_checkout_is_rejected(workflow, context, provider, database):
    created, quote, body = quoted(workflow, context)
    with database.transaction() as tx:
        quote["expires_at"] = (datetime.now(UTC) - timedelta(seconds=1)).isoformat()
        tx.execute("UPDATE carts SET quote_payload=%s", (Jsonb(quote),))
    assert_code(
        "QUOTE_EXPIRED", lambda: workflow.checkout_cart(created.cart_id, body, context, "checkout")
    )
    assert provider.count("/v1/orders") == 0


def test_quote_race_cart_edit_during_provider_call_is_rejected(workflow, context, provider):
    created = setup_cart(workflow.state, context)
    provider.on_quote = lambda: workflow.state.update_cart(
        created.cart_id,
        "SYN-M-BLUE",
        CartUpdateRequest(quantity=1, expected_cart_version=1),
        context,
        "edit2",
    )
    assert_code(
        "CART_VERSION_CONFLICT",
        lambda: workflow.request_quote(
            created.cart_id, CartQuoteRequest(expected_cart_version=1), context, "quote"
        ),
    )


def test_concurrent_checkout_reuses_one_downstream_key(workflow, context, provider):
    created, quote, body = quoted(workflow, context)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: workflow.checkout_cart(created.cart_id, body, context, "checkout"),
                range(4),
            )
        )
    assert len({r["order_id"] for r in results}) == 1 and len(provider.accepted) == 1


def test_retry_under_another_key_resolves_all_pending_aliases(workflow, context, provider):
    created, quote, body = quoted(workflow, context)
    provider.lose_order_response = True
    assert_code(
        "DEPENDENCY_UNAVAILABLE",
        lambda: workflow.checkout_cart(created.cart_id, body, context, "first"),
    )
    result = workflow.checkout_cart(created.cart_id, body, context, "second")
    assert workflow.checkout_cart(created.cart_id, body, context, "first") == result
    assert len(provider.accepted) == 1
    assert (
        workflow.state.update_cart(
            created.cart_id,
            "SYN-M-BLUE",
            CartUpdateRequest(quantity=1, expected_cart_version=1),
            context,
            "edit2",
        ).version
        == 2
    )


def test_confirmation_id_cannot_bind_a_different_quote(workflow, context):
    created, quote, body = quoted(workflow, context)
    workflow.checkout_cart(created.cart_id, body, context, "first")
    new_quote = workflow.request_quote(
        created.cart_id, CartQuoteRequest(expected_cart_version=1), context, "new-quote"
    )
    assert_code(
        "IDEMPOTENCY_CONFLICT",
        lambda: workflow.checkout_cart(
            created.cart_id,
            body.model_copy(update={"quote_id": new_quote["quote_id"]}),
            context,
            "second",
        ),
    )


def test_definitive_orders_rejection_is_durable_and_allows_cart_edit(workflow, context, provider):
    created, quote, body = quoted(workflow, context)
    provider.order_reject = "QUOTE_EXPIRED"
    assert_code(
        "QUOTE_EXPIRED", lambda: workflow.checkout_cart(created.cart_id, body, context, "checkout")
    )
    before = provider.count("/v1/orders")
    assert_code(
        "QUOTE_EXPIRED", lambda: workflow.checkout_cart(created.cart_id, body, context, "checkout")
    )
    assert provider.count("/v1/orders") == before
    assert (
        workflow.state.update_cart(
            created.cart_id,
            "SYN-M-BLUE",
            CartUpdateRequest(quantity=1, expected_cart_version=1),
            context,
            "edit2",
        ).version
        == 2
    )


def test_orders_unavailable_remains_unknown_and_recovers_same_command(workflow, context, provider):
    created, quote, body = quoted(workflow, context)
    provider.orders_unavailable = True
    assert_code(
        "DEPENDENCY_UNAVAILABLE",
        lambda: workflow.checkout_cart(created.cart_id, body, context, "checkout"),
    )
    assert len(provider.accepted) == 0
    provider.orders_unavailable = False
    assert workflow.checkout_cart(created.cart_id, body, context, "checkout")["status"] == "PENDING"


def test_real_gateway_cannot_load_test_schemas_or_test_clock(state, provider):
    from services.conversation.gateway import Gateway

    with pytest.raises(ValueError):
        Gateway("http://catalog.test", "http://orders.test", contracts=provider.gateway().contracts)


def test_service_refuses_enabling_optional_assist(state, monkeypatch):
    monkeypatch.setenv("ALLOW_INTENT_LLM", "true")
    with pytest.raises(ValueError):
        create_app(state=state, mode="stub", purpose="contract_test")


def test_upgrade_from_p6_preserves_existing_state(database, state, context):
    created = state.create_session(context, "session")
    # This fixture owns a fresh isolated schema; recreate only its P6 boundary.
    with database.transaction() as tx:
        tx.execute("DROP TABLE workflow_commands, confirmations")
        tx.execute("ALTER TABLE carts DROP COLUMN quote_payload")
        tx.execute("DELETE FROM conversation_schema_migrations WHERE version=2")
    database.migrate()
    database.migrate()
    database.ready()
    assert state.create_session(context, "session") == created
    assert state.get_cart(created.cart_id, context).version == 0


@pytest.mark.parametrize(
    "change,code",
    [
        ({"user_id": "someone-else"}, "FORBIDDEN"),
        ({"namespace": "bench-another"}, "NOT_FOUND"),
        ({"session_id": str(uuid4())}, "FORBIDDEN"),
    ],
)
def test_workflow_identity_isolation_precedes_provider_call(
    workflow, context, provider, change, code
):
    created, quote, body = quoted(workflow, context)
    before = len(provider.requests)
    other = context.model_copy(update=change)
    assert_code(
        code,
        lambda: workflow.request_quote(
            created.cart_id, CartQuoteRequest(expected_cart_version=1), other, "other-quote"
        ),
    )
    assert_code(
        code, lambda: workflow.checkout_cart(created.cart_id, body, other, "other-checkout")
    )
    assert len(provider.requests) == before


def test_http_smoke_endpoints_and_pending_response(workflow, context, provider):
    with TestClient(
        create_app(state=workflow.state, workflow=workflow, mode="stub", purpose="contract_test")
    ) as client:
        headers = context.headers("session")
        created = client.post("/v1/sessions", headers=headers, json={}).json()
        cart = created["cart_id"]
        headers["Idempotency-Key"] = "add"
        assert (
            client.put(
                f"/v1/carts/{cart}/items/SYN-M-BLUE",
                headers=headers,
                json={"quantity": 1, "expected_cart_version": 0},
            ).status_code
            == 200
        )
        headers["Idempotency-Key"] = "quote"
        quote = client.post(
            f"/v1/carts/{cart}/quote", headers=headers, json={"expected_cart_version": 1}
        )
        assert quote.status_code == 201
        body = {
            "quote_id": quote.json()["quote_id"],
            "expected_cart_version": 1,
            "confirmed": True,
            "confirmation_id": str(uuid4()),
        }
        headers["Idempotency-Key"] = "checkout"
        assert (
            client.post(
                f"/v1/carts/{cart}/checkout", headers=headers, json={**body, "confirmed": False}
            ).status_code
            == 422
        )
        first = client.post(f"/v1/carts/{cart}/checkout", headers=headers, json=body)
        assert first.status_code == 202 and first.json()["status"] == "PENDING"
        assert (
            client.post(f"/v1/carts/{cart}/checkout", headers=headers, json=body).json()
            == first.json()
        )


@pytest.mark.parametrize("scenario", FIXTURE["scenarios"], ids=lambda s: s["scenario_id"])
def test_T10_D05_fixed_scenarios(workflow, context, provider, scenario, record_property):
    """Execute all frozen inputs against explicitly synthetic providers, not labels as code."""
    started_at = datetime.now(UTC).isoformat()
    control, fault = scenario["control"], scenario["fault"]
    if control == "search":
        binding = scenario.get("test_fixture_binding")
        if binding:
            provider.products = [p for p in provider.products if p["sku"] in binding["view_skus"]]
        provider.catalog_unavailable = fault == "catalog_503"
        provider.model_fault = (
            fault if fault and fault.startswith(("model", "invalid_model")) else None
        )
        if scenario.get("untrusted_input"):
            untrusted = scenario["untrusted_input"]
            for product in provider.products:
                if product["sku"] == untrusted["sku"]:
                    product[untrusted["field"]] = untrusted["value"]
            provider.untrusted_titles[untrusted["sku"]] = untrusted["value"]
        result = turn(workflow, context, scenario["text"])
        expected = scenario["expected_outcome"]
        if "clarification" in expected:
            assert result.outcome == "clarification" and provider.count("/v1/search") == 0
        elif fault == "catalog_503":
            assert result.outcome == "dependency_error"
        else:
            assert result.outcome == "success"
            assert [p["sku"] for p in result.products] == scenario["expected_behavior"][
                "expected_hit_skus"
            ]
            assert {f: result.intent[f] for f in scenario["intent_labels"]} == scenario[
                "intent_labels"
            ]
            assert provider.count("/v1/search") == 1
        evidence = result.model_dump(mode="json")
        assert provider.count("/v1/orders") == provider.count("/v1/quotes") == 0
    else:
        fixture = scenario["offline_workflow_fixture"]
        context = seed_workflow_fixture(workflow.state, fixture)
        workflow = FixedWorkflow(
            workflow.state,
            provider.gateway(),
            clock=lambda: datetime.fromisoformat(fixture["clock_utc"].replace("Z", "+00:00")),
        )
        cart_id, quote = fixture["cart"]["cart_id"], fixture["quote"]
        operation = fixture["request"]
        key, raw = operation.get("idempotency_key"), operation["body"]
        provider.quote_override, provider.status_override = quote, fixture["order_snapshot"]
        evidence = {"outcome": "not_executed"}
        if control == "cart_add":
            body = CartUpdateRequest.model_validate(raw)
            cart = workflow.state.update_cart(
                cart_id,
                "SYN-M-BLUE",
                body,
                context,
                key,
            )
            assert workflow.state.update_cart(cart_id, "SYN-M-BLUE", body, context, key) == cart
            assert cart.version == scenario["expected_behavior"]["resulting_cart_version"]
            assert cart.lines[0].quantity == scenario["expected_behavior"]["quantity_after"]
            evidence = {"outcome": "one_cart_effect", "cart_version": cart.version}
        elif control == "stale_cart_version":
            body = CheckoutRequest.model_validate(raw)
            assert_code(
                "CART_VERSION_CONFLICT",
                lambda: workflow.checkout_cart(cart_id, body, context, key),
            )
            assert provider.count("/v1/orders") == 0
            evidence = {"outcome": "conflict", "code": "CART_VERSION_CONFLICT"}
        elif control == "checkout_unconfirmed":
            with pytest.raises(ValidationError):
                CheckoutRequest.model_validate(raw)
            assert provider.count("/v1/orders") == 0
            evidence = {"outcome": "no_purchase"}
        elif control == "checkout_confirmed":
            body = CheckoutRequest.model_validate(raw)
            if fault == "order_create_response_lost":
                provider.lose_order_response = True
                assert_code(
                    "DEPENDENCY_UNAVAILABLE",
                    lambda: workflow.checkout_cart(cart_id, body, context, key),
                )
            accepted = workflow.checkout_cart(cart_id, body, context, key)
            assert workflow.checkout_cart(cart_id, body, context, key) == accepted
            assert accepted["status"] == "PENDING" and len(provider.accepted) == 1
            sent = next(r for r in provider.requests if r.url.path == "/v1/orders")
            expected_provider_body = {
                "quote_id": raw["quote_id"],
                "session_id": context.session_id,
                "confirmation_id": raw["confirmation_id"],
            }
            assert json.loads(sent.content) == expected_provider_body
            evidence = {"outcome": "accepted_pending", **accepted}
        elif control == "quote":
            result = workflow.request_quote(
                cart_id, CartQuoteRequest.model_validate(raw), context, key
            )
            assert result == quote
            assert str(quote["total_amount_minor"]) in compose_response(action_status=result)
            evidence = {"outcome": "authoritative_quote", "quote": result}
        elif control == "order_status":
            provider.orders_unavailable = fault == "orders_503"
            provider.order_status_loss = fault == "order_status_response_lost"
            order_id = operation["path"].rsplit("/", 1)[1]
            if provider.orders_unavailable:
                assert_code(
                    "DEPENDENCY_UNAVAILABLE", lambda: workflow.order_status(order_id, context)
                )
                evidence = {"outcome": "dependency_error"}
            else:
                result = workflow.order_status(order_id, context)
                assert result == fixture["order_snapshot"]
                evidence = {"outcome": "backend_status", "snapshot": result}
        else:
            pytest.fail("unhandled structured control")
    assert provider.model.attempts == 0
    evidence.update(
        scenario_id=scenario["scenario_id"],
        mode="fixed",
        model_attempts=0,
        live_assist="NOT_RUN",
        provider_mode="explicit_http_double",
        search_calls=provider.count("/v1/search"),
        namespace=context.namespace,
        started_at=started_at,
        completed_at=datetime.now(UTC).isoformat(),
    )
    record_property("assistant_turn", json.dumps(evidence, sort_keys=True))
