"""Only worker zero binds the real shared relay; relay/publisher here are doubles."""

from contextlib import contextmanager
from types import SimpleNamespace

from pipelines.ingestion import notifications


def test_notification_runtime_uses_shared_relay_and_closes_resources(monkeypatch):
    calls = []

    @contextmanager
    def connect():
        yield SimpleNamespace(execute=lambda sql: calls.append("ready"))

    class Publisher:
        def __init__(self, codec, bootstrap):
            assert codec == "codec-double" and bootstrap == "broker-double"

        def close(self):
            calls.append("publisher-close")

    class Relay:
        def __init__(self, pool, publisher, **options):
            assert options == {"service_name": "analytics", "batch_limit": 100}
            self.pool = pool
            self._thread = SimpleNamespace(is_alive=lambda: False)

        def start(self):
            self.connection = self.pool.getconn()
            calls.append("start")

        def stop(self, *, timeout):
            assert timeout == 30
            self.pool.putconn(self.connection)
            calls.append("stop")

    monkeypatch.setattr(notifications, "KafkaPublisher", Publisher)
    monkeypatch.setattr(notifications, "OutboxRelay", Relay)
    pipeline = SimpleNamespace(connect=connect, codec="codec-double")
    with notifications.notification_relay(pipeline, "broker-double"):
        calls.append("run")
    assert calls == ["ready", "start", "run", "stop", "publisher-close"]
