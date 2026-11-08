"""Worker entrypoint wiring with explicit server/worker doubles."""

from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from pipelines.ingestion import worker
from shared.telemetry import Telemetry


@pytest.mark.parametrize("fail", [False, True])
def test_worker_serves_its_own_registry_and_closes_listener(monkeypatch, fail):
    pipeline = SimpleNamespace(telemetry=Telemetry())
    calls = []
    monkeypatch.setenv("RUN_NAMESPACE", "bench-worker-metrics")
    monkeypatch.setenv("RUN_ID", "explicit-fixture")
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "unused-double")
    monkeypatch.setattr(worker, "pipeline_from_env", lambda: pipeline)
    monkeypatch.setattr(worker, "notification_relay", lambda *args: nullcontext())

    def start(port, *, addr, registry):
        assert port == 8006 and addr == "0.0.0.0" and registry is pipeline.telemetry.registry
        calls.append("listen")
        server = SimpleNamespace(
            shutdown=lambda: calls.append("shutdown"),
            server_close=lambda: calls.append("close"),
        )
        return server, SimpleNamespace(join=lambda: calls.append("join"))

    def run(*args):
        assert args == (pipeline, "bench-worker-metrics", "explicit-fixture", "unused-double")
        calls.append("run")
        if fail:
            raise RuntimeError("explicit worker failure")

    monkeypatch.setattr(worker, "start_http_server", start)
    monkeypatch.setattr(worker, "run", run)
    if fail:
        with pytest.raises(RuntimeError, match="explicit worker failure"):
            worker.main()
    else:
        worker.main()
    assert calls == ["listen", "run", "shutdown", "close", "join"]


def test_listener_bind_failure_cannot_start_consuming(monkeypatch):
    monkeypatch.setattr(worker, "pipeline_from_env", lambda: SimpleNamespace(telemetry=Telemetry()))

    def occupied(*args, **kwargs):
        raise OSError("explicit occupied port")

    def never_run(*args):
        raise AssertionError("consumption started without its metrics listener")

    monkeypatch.setattr(worker, "start_http_server", occupied)
    monkeypatch.setattr(worker, "run", never_run)
    with pytest.raises(OSError, match="occupied port"):
        worker.main()
