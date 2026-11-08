"""Relay lifecycle/connection doubles; this suite makes no live Kafka claim."""

import json
from time import monotonic, sleep
from types import SimpleNamespace

import pytest

from services.conversation import relay


@pytest.fixture
def components(monkeypatch):
    calls = []

    class DatabaseDouble:
        def __init__(self, url):
            pass

        def ready(self):
            calls.append("database-ready")

    class EventsDouble:
        def ready(self, database):
            calls.append("event-append-ready")

        def event_codec(self):
            return "verified-codec-double"

    class PublisherDouble:
        def __init__(self, codec, bootstrap):
            assert codec == "verified-codec-double"
            calls.append("publisher")

        def close(self):
            calls.append("close")

    class RelayDouble:
        def __init__(self, pool, publisher, **kwargs):
            assert kwargs == {
                "service_name": "conversation",
                "poll_interval_ms": 25,
                "batch_limit": 100,
            }

        def start(self):
            calls.append("start")

        def stop(self):
            calls.append("stop")

    monkeypatch.setattr(relay, "Database", DatabaseDouble)
    monkeypatch.setattr(relay, "SharedEvents", EventsDouble)
    monkeypatch.setattr(relay, "KafkaPublisher", PublisherDouble)
    monkeypatch.setattr(relay, "OutboxRelay", RelayDouble)
    return calls, DatabaseDouble, EventsDouble, RelayDouble


def test_ready_append_precedes_publisher_and_shared_relay(components):
    calls, *_ = components
    runtime = relay.RelayRuntime("explicit-db-double", "explicit-broker-double")
    runtime.start()
    assert calls == ["database-ready", "event-append-ready", "publisher", "start"]
    with pytest.raises(RuntimeError):
        runtime.start()
    runtime.stop()
    assert calls[-2:] == ["stop", "close"]


def test_missing_event_dependency_starts_no_publisher(components, monkeypatch):
    calls, _, events, _ = components

    def fail(*args):
        raise RuntimeError("explicit missing cache double")

    monkeypatch.setattr(events, "ready", fail)
    with pytest.raises(RuntimeError):
        relay.RelayRuntime("db-double", "broker-double").start()
    assert calls == ["database-ready"]


def test_relay_start_failure_closes_publisher_once(components, monkeypatch):
    calls, _, _, worker = components

    def fail(*args):
        raise RuntimeError("explicit failed worker double")

    monkeypatch.setattr(worker, "start", fail)
    runtime = relay.RelayRuntime("db-double", "broker-double")
    with pytest.raises(RuntimeError):
        runtime.start()
    runtime.stop()
    assert calls.count("close") == 1


def test_pool_releases_budget_on_connect_failure_and_connection_close(monkeypatch):
    pool = relay.RelayPool("explicit-db-double")

    def failed(*args, **kwargs):
        raise OSError("connection double")

    monkeypatch.setattr(relay.psycopg, "connect", failed)
    with pytest.raises(OSError):
        pool.getconn()
    closed = []
    connection = SimpleNamespace(close=lambda: closed.append(True))
    monkeypatch.setattr(relay.psycopg, "connect", lambda *a, **k: connection)
    assert pool.getconn() is connection
    pool.putconn(connection)
    assert closed == [True]
    assert pool.getconn() is connection
    pool.putconn(connection)


def test_cli_without_required_environment_exits_before_any_runtime(components, monkeypatch):
    monkeypatch.delenv("CONVERSATION_DATABASE_URL", raising=False)
    monkeypatch.delenv("KAFKA_BOOTSTRAP_SERVERS", raising=False)
    assert relay.main([]) == 4
    assert components[0] == []


def test_real_postgres_shared_relay_marks_existing_bytes_and_restart_is_noop(
    database, tmp_path, monkeypatch, context
):
    """Real DB/shared thread/codec; registry IDs and broker acknowledgement are doubles."""
    from services.conversation.events import SharedEvents
    from services.conversation.state import ConversationState
    from shared.contracts.conversation import CartUpdateRequest
    from shared.event_transport.schemas import documents

    mapping = {
        "compatibility": "BACKWARD_TRANSITIVE",
        "schemas": [
            {**entry, "schema": schema, "id": index, "version": 1}
            for index, (entry, schema) in enumerate(documents().values(), 1)
        ],
    }
    path = tmp_path / "explicit-registry-id-double.json"
    path.write_text(json.dumps(mapping), encoding="utf-8")
    monkeypatch.setenv("EVENT_SCHEMA_CACHE_PATH", str(path))
    monkeypatch.setenv("CATALOG_DATASET_REVISION", "finish-explicit-synthetic")
    events = SharedEvents()
    state = ConversationState(database, events=events)
    created = state.create_session(context, "session")
    state.update_cart(
        created.cart_id,
        "FK-RELAY-UNIT",
        CartUpdateRequest(quantity=1, expected_cart_version=0),
        context,
        "cart",
    )
    with database.transaction() as tx:
        before = tx.execute("SELECT event_id,payload FROM outbox").fetchone()
    published = []

    class AckDouble:
        def __init__(self, codec, bootstrap):
            self.codec = codec

        def publish_event(self, event, topic, key):
            raw, _, _, _ = self.codec.encode(event, topic, key)
            assert raw == bytes(before["payload"])
            published.append(event.event_id)

        def close(self):
            pass

    monkeypatch.setattr(relay, "KafkaPublisher", AckDouble)
    for restart in range(2):
        runtime = relay.RelayRuntime(database.url, "explicit-broker-ack-double")
        runtime.start()
        try:
            deadline = monotonic() + 5
            while monotonic() < deadline:
                with database.transaction() as tx:
                    row = tx.execute("SELECT published_at FROM outbox").fetchone()
                if row["published_at"] is not None:
                    break
                sleep(0.025)
            assert row["published_at"] is not None
        finally:
            runtime.stop()
        if restart:
            assert len(published) == 1
    assert published == [str(before["event_id"])]
    with database.transaction() as tx:
        assert tx.execute("SELECT count(*) AS n FROM outbox").fetchone()["n"] == 1


def test_real_m1_migration_participant_is_idempotent(database, monkeypatch):
    from projectctl.models import ExitCode
    from projectctl.setup import migrate_conversation

    monkeypatch.setenv("CONVERSATION_DATABASE_URL", database.url)
    assert migrate_conversation(None).code == ExitCode.COMPLETED
    assert migrate_conversation(None).code == ExitCode.COMPLETED
    database.ready()
