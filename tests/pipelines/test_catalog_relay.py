"""Catalogue binding reuses the real relay interface; all I/O here is doubled."""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from infra import catalog_relay


@pytest.mark.parametrize("alive", [False, True])
def test_shared_relay_binding_and_confirmed_shutdown(monkeypatch, alive):
    calls = []
    connection = SimpleNamespace(execute=lambda sql: calls.append("ready"))
    monkeypatch.setattr(catalog_relay.psycopg, "connect", lambda *a, **kw: nullcontext(connection))

    class Publisher:
        def __init__(self, codec, bootstrap):
            assert codec == "codec-double" and bootstrap == "broker-double"

        def close(self):
            calls.append("close")

    class Relay:
        def __init__(self, pool, publisher, **options):
            assert options == {
                "service_name": "catalog",
                "poll_interval_ms": 25,
                "batch_limit": 100,
            }
            self._thread = SimpleNamespace(is_alive=lambda: alive)

        def start(self):
            calls.append("start")

        def stop(self, timeout):
            assert timeout == 30
            calls.append("stop")

    monkeypatch.setattr(catalog_relay, "KafkaPublisher", Publisher)
    monkeypatch.setattr(catalog_relay, "OutboxRelay", Relay)
    if alive:
        with pytest.raises(RuntimeError, match="unconfirmed"):
            with catalog_relay.catalog_relay("url-double", "codec-double", "broker-double"):
                pass
        assert calls == ["ready", "start", "stop"]
    else:
        with catalog_relay.catalog_relay("url-double", "codec-double", "broker-double"):
            calls.append("run")
        assert calls == ["ready", "start", "run", "stop", "close"]
