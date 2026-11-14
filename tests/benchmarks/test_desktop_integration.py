"""Explicit owner doubles for collector failure, pinned proof and scoped demo guards."""

from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from benchmarks.windows.infrastructure import parse_cgroup
from pipelines.ingestion.api import create_app
from shared.local_diagnostics import demo_controls


def test_cgroup_is_actual_counter_data_not_requested_memory():
    row = parse_cgroup("::cpu.stat\nusage_usec 2500000\n::memory.current\n123\n"
                       "::memory.max\n1048576\n::memory.peak\n456\n::memory.events\noom_kill 2\n")
    assert row["cpu_seconds"] == 2.5 and row["memory_bytes"] == 123
    assert row["memory_peak_bytes"] == 456 and row["oom_kill_count"] == 2
    with pytest.raises((KeyError, IndexError, ValueError)):
        parse_cgroup("::cpu.stat\nusage_usec 0")


@pytest.mark.parametrize("next_generation", [1, 2])
def test_visibility_uses_exact_membership_and_refuses_mixed_query_generation(monkeypatch, next_generation):
    identity, absent = str(uuid4()), str(uuid4())
    manifest = SimpleNamespace(generation=1, files=[], created_at=datetime.now(UTC),
                               model_dump=lambda **kwargs: {"generation": 1})
    pipeline = SimpleNamespace(active_manifest=lambda *a: manifest,
                               connect=lambda: nullcontext(None),
                               query_gold=lambda *a: SimpleNamespace(generation=next_generation))
    monkeypatch.setattr("pipelines.storage.publication.iter_membership", lambda *a: iter([identity]))
    client = TestClient(create_app(pipeline, internal_token="explicit-test-token"))
    body = {"namespace": "bench-test", "event_ids": [identity, absent]}
    assert client.post('/internal/v1/analytics/visibility', json=body).status_code == 401
    result = client.post('/internal/v1/analytics/visibility', json=body,
                         headers={"Authorization": "Bearer explicit-test-token"}).json()
    assert result["visible_event_ids"] == [identity] and result["missing_event_ids"] == [absent]
    assert result["queryable"] == (next_generation == 1)


def test_refund_delay_requires_enabled_matching_run_and_expires_at_reservation(monkeypatch):
    context = SimpleNamespace(run_id=str(uuid4()), namespace="dev")
    future = (datetime.now(UTC) + timedelta(seconds=20)).isoformat()
    monkeypatch.setattr(demo_controls, "read_control", lambda *a: None)
    assert demo_controls.refund_hold_until(context, future) is None
    monkeypatch.setattr(demo_controls, "read_control", lambda *a: {"scenario": "refund"})
    assert demo_controls.refund_hold_until(context, future) > datetime.now(UTC)
    expired = (datetime.now(UTC) - timedelta(seconds=5)).isoformat()
    assert demo_controls.refund_hold_until(context, expired) is None
