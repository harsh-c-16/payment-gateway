"""Real shared codec/outbox and isolated PostgreSQL; explicitly doubled registry IDs.

The cache fixture uses pinned production schemas with synthetic local IDs. It
proves SDK/schema/transaction integration, never live registry or Kafka delivery.
Catalogue/Orders/model inputs below are explicitly declared test doubles.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from services.conversation.app import create_app
from services.conversation.database import MIGRATIONS
from services.conversation.errors import ServiceError
from services.conversation.events import SharedEvents
from services.conversation.state import ConversationState
from services.conversation.workflow import FixedWorkflow
from shared.contracts.events import EventEnvelope, ValidEvent
from shared.event_transport.schemas import documents

from .intent_doubles import IntentSpy
from .test_state import update
from .test_workflow import quoted
from .workflow_doubles import WorkflowProviderDouble

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def cache_path(tmp_path):
    """Explicit registry mapping double; all schemas/hashes are the owner's pins."""
    manifest = {
        "compatibility": "BACKWARD_TRANSITIVE",
        "schemas": [
            {**entry, "schema": schema, "id": index, "version": 1}
            for index, (entry, schema) in enumerate(documents().values(), 1)
        ],
    }
    path = tmp_path / "registry-mapping-double.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


@pytest.fixture
def events(cache_path):
    return SharedEvents(
        cache_path=cache_path,
        dataset_revision=WorkflowProviderDouble().facets["dataset_revision"],
    )


def rows(database):
    with database.transaction() as tx:
        return tx.execute("SELECT * FROM outbox ORDER BY outbox_id").fetchall()


def checked(events, database):
    result = []
    for row in rows(database):
        document = json.loads(bytes(row["payload"]))
        if document.get("event_type") is None:
            continue  # DLQ has its own registered schema, checked separately.
        event = EventEnvelope.model_validate(document)
        codec = events._codec
        raw, headers, topic, key = codec.encode(event)
        assert raw == bytes(row["payload"])
        assert topic == row["topic"] and key.decode() == row["partition_key"]
        assert isinstance(codec.validate_event(raw, headers, topic, key), ValidEvent)
        assert event.metadata.synthetic is True
        assert event.metadata.scenario_source == "benchmark"
        assert event.metadata.dataset_revision == codec.dataset_revision
        assert row["published_at"] is None
        result.append(event)
    return result


@pytest.mark.parametrize("fault", ["missing", "incomplete", "tampered", "malformed"])
def test_cache_failures_are_dependency_errors(cache_path, fault):
    manifest = json.loads(cache_path.read_text())
    if fault == "missing":
        cache_path.unlink()
    elif fault == "incomplete":
        manifest["schemas"].pop()
        cache_path.write_text(json.dumps(manifest))
    elif fault == "tampered":
        manifest["schemas"][0]["schema"]["title"] = "tampered"
        cache_path.write_text(json.dumps(manifest))
    else:
        cache_path.write_text("{")
    with pytest.raises(ServiceError) as error:
        SharedEvents(cache_path=cache_path, dataset_revision="explicit-test-revision").ready()
    assert error.value.body.code == "DEPENDENCY_UNAVAILABLE"


def test_missing_dataset_binding_is_not_ready(cache_path, monkeypatch):
    monkeypatch.delenv("CATALOG_DATASET_REVISION", raising=False)
    with pytest.raises(ServiceError) as error:
        SharedEvents(cache_path=cache_path).ready()
    assert error.value.body.code == "DEPENDENCY_UNAVAILABLE"


def test_missing_pinned_repository_schema_is_not_ready(cache_path, monkeypatch):
    import shared.event_transport.schemas as schemas

    monkeypatch.setattr(schemas, "MANIFEST", cache_path.with_name("missing-schema-manifest.json"))
    with pytest.raises(ServiceError) as error:
        SharedEvents(cache_path=cache_path, dataset_revision="test-revision").ready()
    assert error.value.body.code == "DEPENDENCY_UNAVAILABLE"


def test_schema_cache_is_loaded_once_and_no_publisher_is_constructed(
    events, cache_path, monkeypatch
):
    import shared.event_transport as transport

    def forbidden(*args, **kwargs):
        pytest.fail("event construction/readiness must never construct a Kafka publisher")

    monkeypatch.setattr(transport, "KafkaPublisher", forbidden)
    events.ready()
    cache_path.unlink()
    events.ready()  # Established verified cache remains usable without registry/files.
    events.check_revision(WorkflowProviderDouble().facets["dataset_revision"])
    with pytest.raises(ServiceError):
        events.check_revision("different-revision")


def test_forward_migration_uses_exact_owner_templates_without_rewriting_history():
    assert [p.name for p in MIGRATIONS] == [
        "001_state.sql",
        "002_workflow.sql",
        "003_intent_diagnostics.sql",
        "004_shared_events.sql",
    ]
    content = MIGRATIONS[-1].read_text(encoding="utf-8")
    for template in ("shared/outbox/schema.sql", "shared/local_diagnostics/schema.sql"):
        assert (ROOT / template).read_text(encoding="utf-8").strip() in content


def test_ready_exercises_real_append_without_leaving_an_event(database, events):
    state = ConversationState(database, events=events)
    state.ready()
    state.ready()
    assert rows(database) == []
    database.migrate()
    state.ready()


def test_forward_upgrade_preserves_preexisting_cart_and_migration_checksums(
    monkeypatch, request, context
):
    import services.conversation.database as database_module

    from .doubles import EventCaptureDouble

    # Create an actual pre-004 database schema using the unchanged migration chain.
    all_migrations = database_module.MIGRATIONS
    monkeypatch.setattr(database_module, "MIGRATIONS", all_migrations[:3])
    database = request.getfixturevalue("database")
    state = ConversationState(database, events=EventCaptureDouble())
    created = state.create_session(context, "pre-upgrade")
    snapshot = update(state, context, created)
    with database.transaction() as tx:
        before = tx.execute(
            "SELECT * FROM conversation_schema_migrations ORDER BY version"
        ).fetchall()
    monkeypatch.setattr(database_module, "MIGRATIONS", all_migrations)
    database.migrate()
    database.ready()
    assert state.get_cart(created.cart_id, context) == snapshot
    assert update(state, context, created) == snapshot
    with database.transaction() as tx:
        after = tx.execute(
            "SELECT * FROM conversation_schema_migrations ORDER BY version"
        ).fetchall()
    assert after[:3] == before and [r["version"] for r in after] == [1, 2, 3, 4]
    assert rows(database) == []  # No invented historical facts are backfilled.


@pytest.mark.parametrize("fault", ["missing_table", "denied_insert", "append_failure"])
def test_readiness_fails_on_unusable_outbox(database, events, monkeypatch, fault):
    import shared.outbox as outbox

    if fault == "append_failure":

        def fail(tx, event):
            raise outbox.OutboxError("explicit append failure double")

        monkeypatch.setattr(outbox, "append_outbox", fail)
    else:
        with database.transaction() as tx:
            if fault == "missing_table":
                tx.execute("DROP TABLE outbox")
            else:
                # A real SQL trigger rejects writes, including for a superuser test role.
                tx.execute(
                    "CREATE FUNCTION reject_outbox() RETURNS trigger LANGUAGE plpgsql AS "
                    "$$ BEGIN RAISE EXCEPTION 'test-only outbox write rejection'; END $$"
                )
                tx.execute(
                    "CREATE TRIGGER reject_outbox BEFORE INSERT ON outbox "
                    "FOR EACH ROW EXECUTE FUNCTION reject_outbox()"
                )
    with pytest.raises(ServiceError) as error:
        ConversationState(database, events=events).ready()
    expected = "DEPENDENCY_UNAVAILABLE" if fault == "append_failure" else "STORAGE_UNAVAILABLE"
    assert error.value.body.code == expected


def test_ready_http_uses_actual_schema_and_append_path(database, events):
    state = ConversationState(database, events=events)
    with TestClient(create_app(state=state)) as client:
        assert client.get("/health/ready").json() == {"status": "ready", "mode": "real"}
    assert rows(database) == []


def test_missing_cache_http_readiness_and_cart_mutation_fail_closed(database, context, tmp_path):
    state = ConversationState(
        database, events=SharedEvents(cache_path=tmp_path / "missing.json", dataset_revision="test")
    )
    created = state.create_session(context, "new")
    with TestClient(create_app(state=state)) as client:
        for response in (
            client.get("/health/ready"),
            client.put(
                f"/v1/carts/{created.cart_id}/items/SYN",
                headers=context.headers("edit"),
                json={"quantity": 1, "expected_cart_version": 0},
            ),
        ):
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert state.get_cart(created.cart_id, context).version == 0 and rows(database) == []


def test_cart_real_outbox_schema_provenance_and_idempotent_restart(database, events, context):
    state = ConversationState(database, events=events)
    created = state.create_session(context, "new")
    first = update(state, context, created)
    original = rows(database)
    restarted = ConversationState(database, events=events)
    assert update(restarted, context, created) == first
    assert rows(database) == original
    (event,) = checked(events, database)
    assert event.event_type == "ADD_TO_CART" and event.aggregate_version == 1
    assert event.session_id == created.session_id
    assert event.payload["quantity_after"] == 1


@pytest.mark.parametrize("failure", ["after_append", "after_response", "invalid_schema"])
def test_real_outbox_failure_rolls_back_cart_version_key_and_event(
    database, events, context, monkeypatch, failure
):
    import shared.outbox as outbox

    state = ConversationState(database, events=events)
    created = state.create_session(context, "new")
    if failure == "after_append":
        original = outbox.append_outbox

        def fail(tx, event):
            original(tx, event)
            raise outbox.OutboxError("explicit failure after real append")

        monkeypatch.setattr(outbox, "append_outbox", fail)
    elif failure == "after_response":
        original_save = state._save

        def fail_save(tx, scope, digest, response):
            original_save(tx, scope, digest, response)
            tx.execute("SELECT 1/0")

        monkeypatch.setattr(state, "_save", fail_save)
    else:
        original_event = state._event

        def invalid(tx, row, ctx, kind, payload, at):
            original_event(tx, row, ctx, kind, {**payload, "quantity_after": 11}, at)

        monkeypatch.setattr(state, "_event", invalid)
    with pytest.raises(ServiceError):
        update(state, context, created)
    assert state.get_cart(created.cart_id, context).version == 0
    assert rows(database) == []
    with database.transaction() as tx:
        assert tx.execute("SELECT event_version FROM sessions").fetchone()["event_version"] == 0
        assert tx.execute("SELECT count(*) AS n FROM operation_keys").fetchone()["n"] == 1


@pytest.mark.parametrize(
    "text,kind,tool_names",
    [
        ("clothing", "INTENT_EXTRACTED", ["facets", "search"]),
        ("shirt brand unknown-brand", "INTENT_REJECTED", ["facets"]),
    ],
)
def test_turn_facts_commit_with_response_and_request_retry_is_noop(
    database, events, context, text, kind, tool_names
):
    from shared.contracts.conversation import TurnRequest

    state = ConversationState(database, events=events)
    provider = WorkflowProviderDouble()
    workflow = FixedWorkflow(state, provider.gateway())  # Explicit provider double.
    created = state.create_session(context, "new")
    request = TurnRequest(request_id=context.request_id, text=text)
    first = workflow.dispatch_turn(created.session_id, request, context, "turn")
    original = rows(database)
    assert workflow.dispatch_turn(created.session_id, request, context, "retry-key") == first
    assert rows(database) == original
    facts = checked(events, database)
    assert [f.aggregate_version for f in facts] == list(range(1, len(facts) + 1))
    assert len({f.event_id for f in facts}) == len(facts)
    assert [f.event_type for f in facts].count("CONVERSATION_TURN") == 1
    (intent_fact,) = [f for f in facts if f.event_type == kind]
    assert intent_fact.payload["turn_id"] == first.turn_id
    tools = [f.payload for f in facts if f.event_type == "TOOL_CALLED"]
    assert [f["tool_name"] for f in tools] == tool_names
    assert all(f["duration_ms"] >= 0 for f in tools)
    assert all(f.payload.get("turn_id") == first.turn_id for f in facts)
    assert first.llm_call_count == provider.model.attempts == 0
    assert not {"SEARCH_REQUESTED", "PRODUCT_RETRIEVED"} & {f.event_type for f in facts}


def test_malformed_model_diagnostic_dlq_and_turn_share_transaction(database, events, context):
    from shared.contracts.conversation import TurnRequest

    state = ConversationState(database, events=events)
    spy = IntentSpy(outcome="invalid")
    workflow = FixedWorkflow(
        state,
        WorkflowProviderDouble().gateway(),
        assistant_mode="assist",
        allow_intent_llm=True,
        intent_provider=spy,
    )
    created = state.create_session(context, "new")
    request = TurnRequest(
        request_id=context.request_id,
        text="apparel size medium colour blue material cotton",
        mode="assist",
    )
    response = workflow.dispatch_turn(created.session_id, request, context, "turn")
    facts = checked(events, database)
    (rejected,) = [f for f in facts if f.event_type == "INTENT_REJECTED"]
    with database.transaction() as tx:
        diagnostic = tx.execute("SELECT * FROM local_diagnostics").fetchone()
        private = tx.execute("SELECT * FROM intent_rejections").fetchone()
    assert (
        diagnostic["restricted_content_reference"]
        == rejected.payload["restricted_content_reference"]
    )
    assert private["restricted_output"] == "not json"
    (dlq,) = [r for r in rows(database) if r["topic"].endswith("dead-letter.v1")]
    assert str(diagnostic["diagnostic_id"]) == str(dlq["event_id"])
    from shared.contracts.events import DlqNotice

    notice = DlqNotice.model_validate_json(bytes(dlq["payload"]))
    events._codec.encode(notice)
    assert "not json" not in str([json.loads(bytes(r["payload"])) for r in rows(database)])
    original = rows(database)
    assert workflow.dispatch_turn(created.session_id, request, context, "retry") == response
    assert rows(database) == original and len(spy.calls) == 1


@pytest.mark.parametrize("failure_kind", ["INTENT_EXTRACTED", "dlq"])
def test_failure_in_fact_batch_rolls_back_entire_turn_but_preserves_model_attempt_audit(
    database, events, context, monkeypatch, failure_kind
):
    import shared.outbox as outbox
    from shared.contracts.conversation import TurnRequest
    from shared.contracts.events import DlqNotice

    state = ConversationState(database, events=events)
    spy = IntentSpy(outcome="invalid")
    assist = failure_kind == "dlq"
    workflow = FixedWorkflow(
        state,
        WorkflowProviderDouble().gateway(),
        assistant_mode="assist" if assist else "fixed",
        allow_intent_llm=assist,
        intent_provider=spy if assist else None,
    )
    created = state.create_session(context, "new")
    original = outbox.append_outbox

    def fail(tx, event):
        original(tx, event)
        if isinstance(event, DlqNotice) or event.event_type == failure_kind:
            raise outbox.OutboxError("explicit failure after real batch append")

    monkeypatch.setattr(outbox, "append_outbox", fail)
    request = TurnRequest(
        request_id=context.request_id,
        mode="assist" if assist else "fixed",
        text="apparel size medium colour blue" if assist else "clothing",
    )
    with pytest.raises(ServiceError):
        workflow.dispatch_turn(created.session_id, request, context, "turn")
    assert rows(database) == []
    with database.transaction() as tx:
        for table in ("turns", "local_diagnostics", "intent_rejections"):
            assert tx.execute(f"SELECT count(*) AS n FROM {table}").fetchone()["n"] == 0
        assert tx.execute("SELECT event_version FROM sessions").fetchone()["event_version"] == 0
        assert tx.execute("SELECT count(*) AS n FROM operation_keys").fetchone()["n"] == 1
        assert tx.execute("SELECT count(*) AS n FROM intent_attempts").fetchone()["n"] == int(
            assist
        )
    assert len(spy.calls) == int(assist)


def test_catalogue_revision_mismatch_rolls_back_turn_before_search(database, events, context):
    from shared.contracts.conversation import TurnRequest

    state = ConversationState(database, events=events)
    provider = WorkflowProviderDouble()
    provider.facets["dataset_revision"] = "different-dataset-revision"
    workflow = FixedWorkflow(state, provider.gateway())
    created = state.create_session(context, "new")
    with pytest.raises(ServiceError) as error:
        workflow.dispatch_turn(
            created.session_id,
            TurnRequest(request_id=context.request_id, text="clothing"),
            context,
            "turn",
        )
    assert error.value.body.code == "DEPENDENCY_UNAVAILABLE"
    assert provider.count("/v1/search") == 0 and rows(database) == []
    with database.transaction() as tx:
        assert tx.execute("SELECT count(*) AS n FROM turns").fetchone()["n"] == 0


def test_checkout_accepted_event_retries_preserve_identity_after_append_failure(
    database, events, context, monkeypatch
):
    import shared.outbox as outbox

    state = ConversationState(database, events=events)
    provider = WorkflowProviderDouble()
    workflow = FixedWorkflow(state, provider.gateway())
    created, quote, body = quoted(workflow, context)
    original = outbox.append_outbox

    def fail(tx, event):
        original(tx, event)
        if event.event_type == "CHECKOUT_STARTED":
            raise outbox.OutboxError("explicit loss after accepted-checkout append")

    with monkeypatch.context() as patch:
        patch.setattr(outbox, "append_outbox", fail)
        with pytest.raises(ServiceError):
            workflow.checkout_cart(created.cart_id, body, context, "checkout")
    assert len(provider.accepted) == 1  # Remote effect exists, local result still pending.
    assert not [e for e in checked(events, database) if e.event_type == "CHECKOUT_STARTED"]
    with database.transaction() as tx:
        command = tx.execute(
            "SELECT * FROM workflow_commands WHERE operation='checkout_cart'"
        ).fetchone()
    assert command["state"] == "pending"
    retried_context = context.model_copy(update={"correlation_id": str(uuid4())})
    accepted = workflow.checkout_cart(created.cart_id, body, retried_context, "checkout")
    assert workflow.checkout_cart(created.cart_id, body, context, "alias-key") == accepted
    facts = checked(events, database)
    (event,) = [e for e in facts if e.event_type == "CHECKOUT_STARTED"]
    assert event.correlation_id == context.correlation_id
    assert event.payload == {
        "cart_id": created.cart_id,
        "quote_id": quote["quote_id"],
        "confirmation_id": body.confirmation_id,
        "order_id": accepted["order_id"],
    }
    assert event.aggregate_version == 2 and len(provider.accepted) == 1


def test_database_sql_error_keeps_storage_classification(database, events, context):
    context = context.model_copy(update={"session_id": str(uuid4())})
    with pytest.raises(ServiceError) as error, database.transaction() as tx:
        tx.execute("DROP TABLE outbox")
        events.append(
            tx,
            event_type="ADD_TO_CART",
            context=context,
            version=1,
            payload={"cart_id": str(uuid4()), "cart_version": 1, "sku": "SYN", "quantity_after": 1},
            event_time=datetime.now(UTC),
        )
    assert error.value.body.code == "STORAGE_UNAVAILABLE"
    assert rows(database) == []  # DROP also rolled back.
