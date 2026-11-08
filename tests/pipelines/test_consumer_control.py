"""Consumer-only pause with native broker/clock/control-file doubles."""

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from pipelines.ingestion import control, worker
from tests.pipelines.test_consumer_observations import group


def request(seconds=30):
    return {
        "namespace": "bench-buffer",
        "run_id": "fixture",
        "request_id": str(uuid4()),
        "pause_seconds": seconds,
        "expires_at": (datetime.now(UTC) + timedelta(seconds=seconds or 10)).isoformat(),
    }


def test_operator_pause_retains_heartbeats_and_does_not_auto_resume():
    current = group()
    try:
        current.set_fetch_paused(True)
        before = current.consumer.polls
        assert current.consume_records(current.topics, 0, 1) == []
        assert current.consumer.polls > before
        assert current.buffer_snapshot()["operator_paused"] is True
        assert current.consumer.paused is True
        current.set_fetch_paused(False)
        assert current.consumer.paused is False
    finally:
        current.close()


@pytest.mark.parametrize("benchmark,faults", [("false", "true"), ("true", "false")])
def test_either_disabled_flag_prevents_control(monkeypatch, benchmark, faults):
    monkeypatch.setenv("BENCHMARK_MODE", benchmark)
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", faults)
    with pytest.raises(ValueError, match="Both"):
        control.request_and_wait(request())


def test_pause_has_actual_ack_and_expires_without_controller_recovery(monkeypatch, tmp_path):
    monkeypatch.setenv("BENCHMARK_MODE", "true")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    monkeypatch.setattr(control, "REQUEST", tmp_path / "request.json")
    monkeypatch.setattr(control, "ACK", tmp_path / "ack.json")
    clock = [0.0]
    monkeypatch.setattr(control, "monotonic", lambda: clock[0])
    states = []
    current = control.ConsumerControl("bench-buffer", "fixture")
    command = request()
    control.atomic_json(control.REQUEST, command)
    assert current.tick(SimpleNamespace(set_fetch_paused=states.append))
    assert json.loads(control.ACK.read_text())["request_id"] == command["request_id"]
    clock[0] = 31
    assert not current.tick(SimpleNamespace(set_fetch_paused=states.append))
    assert states == [True, False]
    assert json.loads(control.ACK.read_text())["paused"] is False


def test_wrong_run_cannot_pause_worker(monkeypatch, tmp_path):
    monkeypatch.setenv("BENCHMARK_MODE", "true")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    monkeypatch.setattr(control, "REQUEST", tmp_path / "request.json")
    control.atomic_json(control.REQUEST, request())
    with pytest.raises(ValueError, match="different run"):
        control.ConsumerControl("bench-buffer", "different").tick(None)


def test_short_fractional_lease_and_deleted_request_resume(monkeypatch, tmp_path):
    monkeypatch.setenv("BENCHMARK_MODE", "true")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    monkeypatch.setattr(control, "REQUEST", tmp_path / "request.json")
    monkeypatch.setattr(control, "ACK", tmp_path / "ack.json")
    control.atomic_json(control.REQUEST, request(0.5))
    states = []
    group = SimpleNamespace(set_fetch_paused=states.append)
    current = control.ConsumerControl("bench-buffer", "fixture")
    assert current.tick(group)
    control.REQUEST.unlink()
    assert not current.tick(group)
    assert states == [True, False]


def test_paused_worker_still_publishes_without_ingesting(monkeypatch):
    calls, tick = [], [0.0]
    pauses = iter([True, False])

    def paused(group):
        try:
            return next(pauses)
        except StopIteration:
            raise RuntimeError("fixture complete") from None

    class Group:
        topics = ("bench-buffer.inventory-events.v1",)

        def __init__(self, *args, **kwargs):
            pass

        def consume_records(self, topics, size, wait):
            assert size == 0 and wait == 50
            calls.append("heartbeat")
            tick[0] += 0.3

        def close(self):
            calls.append("close")

    pipeline = SimpleNamespace(
        ingest_once=lambda *args, **kwargs: calls.append("ingest"),
        publish_snapshot=lambda ns: calls.append("publish"),
    )
    monkeypatch.setattr(worker, "ConsumerGroup", Group)
    monkeypatch.setattr(worker, "ConsumerControl", lambda *args: SimpleNamespace(tick=paused))
    monkeypatch.setattr(worker, "log_buffer", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker, "monotonic", lambda: tick[0])
    with pytest.raises(RuntimeError, match="fixture complete"):
        worker.run(pipeline, "bench-buffer", "fixture", "broker-double")
    assert calls == ["heartbeat", "publish", "ingest", "close"]
