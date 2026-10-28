from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest
from psycopg.types.json import Jsonb

from services.conversation.database import Database
from services.conversation.errors import ServiceError
from services.conversation.state import ConversationState, canonical_hash
from shared.contracts.conversation import CartUpdateRequest, TurnRequest

from .doubles import EventCaptureDouble, TurnOutcomeDouble


def update(state, context, created, *, version=0, quantity=1, sku="FK-P6-001", key="edit"):
    return state.update_cart(
        created.cart_id,
        sku,
        CartUpdateRequest(quantity=quantity, expected_cart_version=version),
        context,
        key,
    )


def counts(database):
    with database.transaction() as tx:
        return {
            name: tx.execute(f"SELECT count(*) AS n FROM {name}").fetchone()["n"]
            for name in (
                "sessions",
                "carts",
                "cart_items",
                "turns",
                "operation_keys",
                "p6_test_event_capture",
            )
        }


def test_session_idempotency_and_transport_identity(state, context, database):
    created = state.create_session(context, "new")
    replay = state.create_session(
        context.model_copy(
            update={
                "run_id": "another-run",
                "correlation_id": str(uuid4()),
                "request_id": str(uuid4()),
            }
        ),
        "new",
    )
    assert replay == created
    assert state.get_cart(created.cart_id, context).lines == []
    assert counts(database) == {
        "sessions": 1,
        "carts": 1,
        "cart_items": 0,
        "turns": 0,
        "operation_keys": 1,
        "p6_test_event_capture": 0,
    }


def test_cart_replay_returns_original_snapshot_even_after_later_edit(state, context, database):
    created = state.create_session(context, "new")
    first = update(state, context, created)
    newer = update(state, context, created, version=1, quantity=4, key="edit-2")
    assert newer.version == 2
    assert update(state, context, created) == first
    assert state.get_cart(created.cart_id, context) == newer
    assert counts(database)["p6_test_event_capture"] == 2


@pytest.mark.parametrize("change", ["quantity", "version", "sku", "cart_id"])
def test_changed_business_input_conflicts_with_same_key(state, context, change):
    created = state.create_session(context, "new")
    update(state, context, created)
    options = {"quantity": 2} if change == "quantity" else {}
    if change == "version":
        options["version"] = 1
    if change == "sku":
        options["sku"] = "FK-P6-OTHER"
    if change == "cart_id":
        created = state.create_session(context, "new-2")
    with pytest.raises(ServiceError) as error:
        update(state, context, created, **options)
    assert error.value.status == 409
    assert error.value.body.code == "IDEMPOTENCY_CONFLICT"


def test_stale_version_is_conflict_without_effect_or_consumed_key(state, context, database):
    created = state.create_session(context, "new")
    update(state, context, created)
    before = counts(database)
    with pytest.raises(ServiceError) as error:
        update(state, context, created, quantity=2, key="stale")
    assert error.value.body.code == "CART_VERSION_CONFLICT"
    assert counts(database) == before
    assert update(state, context, created, version=1, quantity=2, key="stale").version == 2


def test_quantity_zero_removes_last_line_and_absent_remove_is_versioned(state, context, database):
    created = state.create_session(context, "new")
    update(state, context, created)
    removed = update(state, context, created, version=1, quantity=0, key="remove")
    assert removed.version == 2 and removed.lines == []
    assert update(state, context, created, version=1, quantity=0, key="remove") == removed
    absent = update(state, context, created, version=2, quantity=0, key="absent")
    assert absent.version == 3 and absent.lines == []
    assert counts(database)["p6_test_event_capture"] == 3


def test_max_lines_and_existing_line_update_and_unknown_display_price(state, context):
    created = state.create_session(context, "new")
    for n in range(20):
        cart = update(state, context, created, version=n, sku=f"FK-P6-{n:03}", key=f"line-{n}")
    assert len(cart.lines) == 20
    assert all(line.display_price_minor is None for line in cart.lines)
    with pytest.raises(ServiceError) as error:
        update(state, context, created, version=20, sku="FK-P6-OVER", key="overflow")
    assert error.value.status == 422
    changed = update(
        state, context, created, version=20, quantity=10, sku="FK-P6-000", key="change"
    )
    assert changed.lines[0].quantity == 10 and len(changed.lines) == 20


@pytest.mark.parametrize(
    "change,status",
    [
        ({"user_id": "other"}, 403),
        ({"namespace": "bench-other"}, 404),
        ({"session_id": str(uuid4())}, 403),
    ],
)
def test_principal_namespace_session_isolation(state, context, database, change, status):
    created = state.create_session(context, "new")
    before = counts(database)
    other = context.model_copy(update=change)
    for action in [
        lambda: state.get_cart(created.cart_id, other),
        lambda: update(state, other, created),
    ]:
        with pytest.raises(ServiceError) as error:
            action()
        assert error.value.status == status
    assert counts(database) == before


def test_same_key_is_scoped_by_principal_namespace_and_operation(state, context, database):
    created = state.create_session(context, "shared-key")
    update(state, context, created, key="shared-key")
    other = context.model_copy(update={"user_id": "other"})
    assert state.create_session(other, "shared-key") != created
    isolated = context.model_copy(update={"namespace": "bench-other"})
    assert state.create_session(isolated, "shared-key") != created
    assert counts(database)["operation_keys"] == 4


def test_edit_invalidates_quote_and_confirmation(state, context, database):
    created = state.create_session(context, "new")
    with database.transaction() as tx:
        tx.execute(
            "UPDATE carts SET quote_id=%s,quote_cart_version=0,confirmation_id=%s",
            (str(uuid4()), str(uuid4())),
        )
    update(state, context, created)
    with database.transaction() as tx:
        row = tx.execute("SELECT quote_id,quote_cart_version,confirmation_id FROM carts").fetchone()
        assert all(value is None for value in row.values())


def test_reconnect_new_state_preserves_cart_and_idempotent_response(state, context, database):
    created = state.create_session(context, "new")
    snapshot = update(state, context, created)
    restarted = ConversationState(Database(database.url), events=EventCaptureDouble())
    assert restarted.get_cart(created.cart_id, context) == snapshot
    assert update(restarted, context, created) == snapshot


@pytest.mark.parametrize("operation", ["cart", "turn"])
def test_failure_after_test_outbox_append_rolls_back_every_effect(
    state, context, database, operation
):
    created = state.create_session(context, "new")
    before = counts(database)
    failing = ConversationState(database, events=EventCaptureDouble(fail_after_append=True))
    with pytest.raises(ServiceError):
        if operation == "cart":
            update(failing, context, created)
        else:
            failing.record_turn(
                created.session_id,
                TurnRequest(request_id=context.request_id, text="restricted synthetic input"),
                context,
                "turn",
                TurnOutcomeDouble(),
            )
    assert counts(database) == before
    assert state.get_cart(created.cart_id, context).version == 0
    with database.transaction() as tx:
        assert tx.execute("SELECT event_version FROM sessions").fetchone()["event_version"] == 0


def test_explicit_outer_abort_rolls_back_test_capture_and_cart(state, context, database):
    # Force a transaction failure after both append and the response-key INSERT.
    created = state.create_session(context, "new")
    before = counts(database)
    original = state._save

    def abort_after_result(tx, scope, digest, response):
        original(tx, scope, digest, response)
        tx.execute("SELECT 1/0")

    state._save = abort_after_result
    with pytest.raises(ServiceError) as error:
        update(state, context, created)
    assert error.value.body.code == "STORAGE_UNAVAILABLE"
    assert counts(database) == before


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_cart_requests_have_one_logical_effect(state, context, database, same_key):
    created = state.create_session(context, "new")

    def edit(n):
        try:
            return update(state, context, created, key="same" if same_key else f"buyer-{n}")
        except ServiceError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = list(executor.map(edit, range(24)))
    successes = [r for r in responses if not isinstance(r, ServiceError)]
    conflicts = [r for r in responses if isinstance(r, ServiceError)]
    assert len(successes) == (24 if same_key else 1)
    assert all(r == successes[0] for r in successes)
    assert all(r.body.code == "CART_VERSION_CONFLICT" for r in conflicts)
    assert counts(database)["p6_test_event_capture"] == 1
    assert state.get_cart(created.cart_id, context).version == 1


def test_concurrent_session_creation_same_key(state, context, database):
    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = list(executor.map(lambda _: state.create_session(context, "new"), range(24)))
    assert all(r == responses[0] for r in responses)
    assert counts(database)["sessions"] == 1


def test_turn_outcome_and_request_identity_are_durable_and_private(state, context, database):
    created = state.create_session(context, "new")
    handler = TurnOutcomeDouble()
    request = TurnRequest(request_id=context.request_id, text="restricted synthetic input")
    response = state.record_turn(created.session_id, request, context, "turn", handler)
    assert state.record_turn(created.session_id, request, context, "turn", handler) == response
    assert (
        state.record_turn(created.session_id, request, context, "new-transport-key", handler)
        == response
    )
    assert handler.calls == 1
    snapshot = counts(database)
    assert snapshot["turns"] == 1 and snapshot["p6_test_event_capture"] == 1
    changed = request.model_copy(update={"text": "changed"})
    with pytest.raises(ServiceError) as error:
        state.record_turn(created.session_id, changed, context, "different-key", handler)
    assert error.value.body.code == "IDEMPOTENCY_CONFLICT"
    with database.transaction() as tx:
        stored = tx.execute("SELECT row_to_json(t)::text AS data FROM turns t").fetchone()["data"]
        event = tx.execute("SELECT event::text AS data FROM p6_test_event_capture").fetchone()[
            "data"
        ]
        assert "restricted synthetic input" not in stored + event


def test_turn_duplicate_request_id_concurrent_across_keys(state, context, database):
    created = state.create_session(context, "new")
    request = TurnRequest(request_id=context.request_id, text="synthetic turn")
    handler = TurnOutcomeDouble()
    with ThreadPoolExecutor(max_workers=8) as executor:
        responses = list(
            executor.map(
                lambda n: state.record_turn(
                    created.session_id, request, context, f"turn-{n}", handler
                ),
                range(16),
            )
        )
    assert all(r == responses[0] for r in responses) and handler.calls == 1
    assert counts(database)["p6_test_event_capture"] == 1


def test_request_id_cannot_cross_session_or_principal(state, context):
    created = state.create_session(context, "new")
    request = TurnRequest(request_id=context.request_id, text="synthetic turn")
    handler = TurnOutcomeDouble()
    state.record_turn(created.session_id, request, context, "turn", handler)
    for other in [context, context.model_copy(update={"user_id": "other"})]:
        new_session = state.create_session(other, str(uuid4()))
        with pytest.raises(ServiceError) as error:
            state.record_turn(new_session.session_id, request, other, "new-key", handler)
        assert error.value.body.code == "IDEMPOTENCY_CONFLICT"


def test_cart_and_turn_share_monotonic_session_event_versions(state, context, database):
    created = state.create_session(context, "new")
    update(state, context, created)
    state.record_turn(
        created.session_id,
        TurnRequest(request_id=context.request_id, text="synthetic"),
        context,
        "turn",
        TurnOutcomeDouble(),
    )
    update(state, context, created, version=1, quantity=0, key="remove")
    with database.transaction() as tx:
        events = tx.execute(
            "SELECT * FROM p6_test_event_capture ORDER BY aggregate_version"
        ).fetchall()
    assert [e["aggregate_version"] for e in events] == [1, 2, 3]
    assert events[-1]["event"]["payload"]["quantity_after"] == 0
    assert all(e["event"]["run_id"] == context.run_id for e in events)


def test_fixed_turn_rejects_nonzero_model_count(state, context, database):
    created = state.create_session(context, "new")

    def invalid(request, ctx):
        response = TurnOutcomeDouble()(request, ctx)
        return response.model_copy(update={"llm_call_count": 1})

    with pytest.raises(ServiceError) as error:
        state.record_turn(
            created.session_id,
            TurnRequest(request_id=context.request_id, text="x"),
            context,
            "turn",
            invalid,
        )
    assert error.value.body.code == "ILLEGAL_STATE"
    assert counts(database)["turns"] == 0


def test_migrations_repeat_and_detect_checksum_drift(database):
    database.migrate()
    database.ready()
    with database.transaction() as tx:
        tx.execute("UPDATE conversation_schema_migrations SET sha256=%s", ("0" * 64,))
    for check in [database.ready, database.migrate]:
        with pytest.raises(ServiceError):
            check()


@pytest.mark.parametrize(
    "statement,params",
    [
        ("UPDATE cart_items SET quantity=0", ()),
        ("UPDATE cart_items SET display_price_minor=-1", ()),
        ("UPDATE carts SET version=-1", ()),
        ("UPDATE carts SET quote_id=%s", (str(uuid4()),)),
        ("INSERT INTO operation_keys SELECT * FROM operation_keys", ()),
        ("UPDATE operation_keys SET response=%s", (Jsonb([]),)),
    ],
)
def test_database_constraints_reject_corrupt_state(state, context, database, statement, params):
    created = state.create_session(context, "new")
    update(state, context, created)
    # Independent raw connection observes actual PostgreSQL constraints.
    with pytest.raises(psycopg.IntegrityError), psycopg.connect(database.url) as tx:
        tx.execute(statement, params)


def test_canonical_hash_preserves_arrays_rejects_nan_and_ignores_object_order():
    assert canonical_hash({"b": 2, "a": 1}) == canonical_hash({"a": 1, "b": 2})
    assert canonical_hash([1, 2]) != canonical_hash([2, 1])
    with pytest.raises(ValueError):
        canonical_hash({"bad": float("nan")})


def test_independent_test_contexts_do_not_contend_on_database_advisory_locks(database, context):
    from .conftest import context as context_fixture

    other = context_fixture.__wrapped__()
    state = ConversationState(database, events=EventCaptureDouble())
    key = str(uuid4())
    with database.transaction() as first:
        state._lock(first, (context.namespace, context.user_id, "submit_turn", key))
        with database.transaction(statement_timeout_ms=100) as second:
            state._lock(second, (other.namespace, other.user_id, "submit_turn", key))
