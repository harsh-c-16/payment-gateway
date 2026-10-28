from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient

from services.conversation.app import create_app
from services.conversation.database import Database
from services.conversation.errors import ServiceError
from services.conversation.events import SharedEvents
from services.conversation.state import ConversationState
from shared.contracts.common import ErrorCode, ErrorResponse

from .doubles import EventCaptureDouble, TurnOutcomeDouble


class UnavailableStateDouble:
    """Offline request-validation double; no successful state operations exist."""

    events = EventCaptureDouble()

    def create_session(self, *args):
        raise ServiceError(503, ErrorCode.STORAGE_UNAVAILABLE, "Storage double unavailable.")

    def ready(self):
        raise ServiceError(503, ErrorCode.STORAGE_UNAVAILABLE, "Storage double unavailable.")


def headers(**updates):
    return {
        "X-Namespace": "bench-p6-http",
        "X-Run-ID": str(uuid4()),
        "X-User-ID": "p6-http-user",
        "X-Correlation-ID": str(uuid4()),
        "X-Request-ID": str(uuid4()),
        "Idempotency-Key": "new",
        **updates,
    }


@pytest.fixture
def offline_client():
    with TestClient(
        create_app(state=UnavailableStateDouble(), mode="stub", purpose="contract_test")
    ) as client:
        yield client


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    error = ErrorResponse.model_validate(response.json())
    assert error.error.code == code
    assert error.error.retryable == (status == 503)
    assert "postgresql://" not in response.text


@pytest.mark.parametrize("value", ["user_id", "namespace", "unknown"])
def test_create_session_rejects_identity_override(offline_client, value):
    response = offline_client.post("/v1/sessions", headers=headers(), json={value: "override"})
    assert_error(response, 400, "BAD_REQUEST")


@pytest.mark.parametrize("body", [b"[]", b"null", b"false", b'"text"', b"{broken"])
def test_create_session_requires_empty_object(offline_client, body):
    assert_error(
        offline_client.post("/v1/sessions", headers=headers(), content=body), 400, "BAD_REQUEST"
    )


@pytest.mark.parametrize("quantity", [-1, 11, 1.5, "1", True, None])
def test_quantity_validation_precedes_database(offline_client, quantity):
    response = offline_client.put(
        f"/v1/carts/{uuid4()}/items/FK-P6-001",
        headers=headers(),
        json={"quantity": quantity, "expected_cart_version": 0},
    )
    assert_error(response, 422, "VALIDATION_ERROR")


@pytest.mark.parametrize("version", [-1, 2**63, 0.5, "0", False, None])
def test_version_validation_precedes_database(offline_client, version):
    response = offline_client.put(
        f"/v1/carts/{uuid4()}/items/FK-P6-001",
        headers=headers(),
        json={"quantity": 1, "expected_cart_version": version},
    )
    assert_error(response, 422, "VALIDATION_ERROR")


@pytest.mark.parametrize(
    "missing,status,code",
    [
        ("X-User-ID", 401, "UNAUTHORIZED"),
        ("X-Namespace", 422, "VALIDATION_ERROR"),
        ("X-Request-ID", 422, "VALIDATION_ERROR"),
        ("X-Run-ID", 422, "VALIDATION_ERROR"),
        ("X-Correlation-ID", 422, "VALIDATION_ERROR"),
        ("Idempotency-Key", 400, "BAD_REQUEST"),
    ],
)
def test_required_context_and_key(offline_client, missing, status, code):
    request_headers = headers()
    request_headers.pop(missing)
    assert_error(offline_client.post("/v1/sessions", headers=request_headers), status, code)


@pytest.mark.parametrize("key", ["", "x" * 129])
def test_invalid_idempotency_key(offline_client, key):
    assert_error(
        offline_client.post("/v1/sessions", headers=headers(**{"Idempotency-Key": key})),
        400,
        "BAD_REQUEST",
    )


def test_health_metrics_and_error_do_not_expose_ids_as_labels(offline_client):
    assert offline_client.get("/health/live").status_code == 200
    assert_error(offline_client.get("/health/ready"), 503, "STORAGE_UNAVAILABLE")
    identity = headers()
    response = offline_client.post("/v1/sessions", headers=identity)
    assert response.headers["X-Correlation-ID"] == identity["X-Correlation-ID"]
    assert_error(response, 503, "STORAGE_UNAVAILABLE")
    metrics = offline_client.get("/metrics").text
    assert 'route="/v1/sessions"' in metrics
    assert identity["X-User-ID"] not in metrics and identity["X-Run-ID"] not in metrics


def test_missing_storage_configuration_cannot_connect_to_default_database():
    with pytest.raises(ServiceError):
        with Database("").transaction():
            pytest.fail("must fail before connecting")


def test_real_app_rejects_double_injection():
    with pytest.raises(ValueError):
        create_app(state=UnavailableStateDouble())
    with pytest.raises(ValueError):
        create_app(mode="stub", purpose="service")
    with pytest.raises(ValueError):
        create_app(turn_handler=TurnOutcomeDouble())


def test_missing_shared_event_implementation_is_visible():
    # This repository has no real implementations; never patch their namespaces.
    with pytest.raises(ServiceError) as error:
        SharedEvents().ready()
    assert error.value.body.code == "DEPENDENCY_UNAVAILABLE"


def test_shared_adapter_preserves_storage_failure_classification(monkeypatch):
    # Explicit binding doubles exercise the M1 adapter, not provider behavior.
    events = SharedEvents()

    def builder(**kwargs):
        return {"test_double": True}

    def append(tx, event):
        raise psycopg.OperationalError("synthetic unavailable storage")

    monkeypatch.setattr(events, "_bindings", lambda: (builder, append))
    from shared.contracts.common import RequestContext

    context = RequestContext(
        namespace="bench-p6-unit",
        run_id="unit",
        user_id="unit",
        correlation_id=str(uuid4()),
        request_id=str(uuid4()),
        session_id=str(uuid4()),
    )
    with pytest.raises(psycopg.OperationalError):
        events.append(
            None, event_type="ADD_TO_CART", payload={}, context=context, version=1, event_time=None
        )


def test_http_cart_checkpoint_real_postgresql_with_explicit_event_double(state, database):
    with TestClient(create_app(state=state, mode="stub", purpose="contract_test")) as client:
        identity = headers()
        created = client.post("/v1/sessions", headers=identity, json={})
        assert created.status_code == 201
        assert client.post("/v1/sessions", headers=identity).json() == created.json()
        cart_id = created.json()["cart_id"]
        path = f"/v1/carts/{cart_id}/items/FK-P6-001"
        identity["Idempotency-Key"] = "edit"
        body = {"quantity": 1, "expected_cart_version": 0}
        added = client.put(path, headers=identity, json=body)
        assert added.status_code == 200
        assert client.put(path, headers=identity, json=body).json() == added.json()
        assert_error(
            client.put(path, headers=identity, json={**body, "quantity": 2}),
            409,
            "IDEMPOTENCY_CONFLICT",
        )
        identity["Idempotency-Key"] = "stale"
        assert_error(client.put(path, headers=identity, json=body), 409, "CART_VERSION_CONFLICT")
        other = {**identity, "X-User-ID": "other"}
        assert_error(client.get(f"/v1/carts/{cart_id}", headers=other), 403, "FORBIDDEN")
        other = {**identity, "X-Namespace": "bench-other"}
        assert_error(client.get(f"/v1/carts/{cart_id}", headers=other), 404, "NOT_FOUND")
        assert client.get("/health/ready").json()["mode"] == "stub"
        assert added.json()["lines"][0]["display_price_minor"] is None


def test_real_service_missing_events_cannot_mutate_or_report_ready(database, context):
    state = ConversationState(database)
    created = state.create_session(context, "new")
    with TestClient(create_app(state=state)) as client:
        assert_error(client.get("/health/ready"), 503, "DEPENDENCY_UNAVAILABLE")
        response = client.put(
            f"/v1/carts/{created.cart_id}/items/FK-P6-001",
            headers=context.headers("edit"),
            json={"quantity": 1, "expected_cart_version": 0},
        )
        assert_error(response, 503, "DEPENDENCY_UNAVAILABLE")
    assert state.get_cart(created.cart_id, context).version == 0


def test_p7_endpoints_remain_explicitly_unavailable(state, context):
    created = state.create_session(context, "new")
    with TestClient(create_app(state=state, mode="stub", purpose="contract_test")) as client:
        cases = [
            (
                f"/v1/sessions/{created.session_id}/turns",
                {"request_id": context.request_id, "text": "hello"},
            ),
            (f"/v1/carts/{created.cart_id}/quote", {"expected_cart_version": 0}),
            (
                f"/v1/carts/{created.cart_id}/checkout",
                {
                    "quote_id": str(uuid4()),
                    "expected_cart_version": 0,
                    "confirmed": True,
                    "confirmation_id": str(uuid4()),
                },
            ),
        ]
        for path, body in cases:
            assert_error(
                client.post(path, headers=context.headers("p7"), json=body),
                503,
                "DEPENDENCY_UNAVAILABLE",
            )


def test_http_turn_persistence_accepts_only_explicit_test_handler(state, context):
    created = state.create_session(context, "new")
    handler = TurnOutcomeDouble()
    with TestClient(
        create_app(state=state, mode="stub", purpose="contract_test", turn_handler=handler)
    ) as client:
        path = f"/v1/sessions/{created.session_id}/turns"
        identity = context.headers("turn")
        body = {"request_id": context.request_id, "text": "synthetic"}
        first = client.post(path, headers=identity, json=body)
        assert first.status_code == 200 and first.json()["llm_call_count"] == 0
        assert client.post(path, headers=identity, json=body).json() == first.json()
        assert handler.calls == 1
        assert_error(
            client.post(
                path,
                headers={**identity, "Idempotency-Key": "bad"},
                json={**body, "request_id": str(uuid4())},
            ),
            400,
            "BAD_REQUEST",
        )
