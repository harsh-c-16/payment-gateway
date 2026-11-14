"""Diagnostic projection/recording checks. Owner doubles are explicit, not live passes."""

import copy
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from benchmarks.failure_demo.controller import ORIGIN, create_app
from benchmarks.journey.lab import Lab
from benchmarks.journey.model import (
    elapsed,
    latency_summary,
    merge_observations,
    related_events,
    safe_event,
    timeline,
)
from benchmarks.journey.observer import Observer
from benchmarks.journey.recordings import Recordings, write_json


@pytest.fixture
def observation():
    at = datetime(2026, 11, 14, tzinfo=UTC)
    times = [(at + timedelta(milliseconds=i)).isoformat() for i in (0, 100, 150, 300, 900)]
    eid, oid = str(uuid4()), str(uuid4())
    source = {
        "topic": "dev.order-events.v1",
        "partition": 0,
        "offset": 10,
        "raw_locator": "bronze/chunk.jsonl#0",
    }
    receipt = {
        "namespace": "dev",
        "event_id": eid,
        "source": source,
        "raw_sha256": "a" * 64,
        "disposition": "new_valid",
        "reason_code": None,
        "ingested_at": times[1],
        "bronze_durable_at": times[2],
        "silver_committed_observed_at": times[3],
        "gold_visible_at": times[4],
        "visibility_generation": 8,
        "timing_validity": "observed",
    }
    return {
        "key": "dev.order-events.v1:0:10",
        "event_id": eid,
        "event_type": "ORDER_CONFIRMED",
        "namespace": "dev",
        "source_service": "orders",
        "aggregate_id": oid,
        "produced_at": times[0],
        "source": source,
        "raw_sha256": "a" * 64,
        "payload": {"order_id": oid},
        "receipt": receipt,
    }


def test_clock_unqualified_quantiles_remain_missing(observation):
    summary = latency_summary([observation], {"status": "unavailable"})
    assert summary["completed_count"] == 1
    assert summary["producer_to_gold"]["sample_count"] == 0
    assert summary["producer_to_gold"]["p99_ms"] is None
    assert summary["cohort_p99_established"] is False


def test_quantiles_include_outbox_wait_and_pending_denominator(observation):
    pending = copy.deepcopy(observation)
    pending.update(event_id=str(uuid4()), receipt=None, outbox_pending=True)
    summary = latency_summary([observation, observation, pending], {"status": "qualified"})
    assert summary["producer_to_gold"] == {
        "sample_count": 1,
        "p50_ms": 900.0,
        "p95_ms": 900.0,
        "p99_ms": 900.0,
    }
    assert summary["cohort_count"] == 2
    assert summary["completed_count"] == 1
    assert summary["unresolved_count"] == 1
    assert summary["cohort_p99_established"] is False


@pytest.mark.parametrize("validity", ["missing", "recovery_upper_bound"])
def test_recovery_bounds_are_not_measured_latencies(observation, validity):
    observation["receipt"]["timing_validity"] = validity
    result = latency_summary([observation], {"status": "qualified"})
    assert result["producer_to_gold"]["sample_count"] == 0


def test_branch_trace_joins_business_ids_without_session_correlation_fanout(observation):
    inventory = copy.deepcopy(observation)
    inventory.update(event_id=str(uuid4()), source_service="inventory")
    payment = copy.deepcopy(observation)
    payment.update(event_id=str(uuid4()), source_service="payments")
    unrelated = copy.deepcopy(observation)
    unrelated.update(
        event_id=str(uuid4()), aggregate_id=str(uuid4()), payload={"order_id": str(uuid4())}
    )
    events = [observation, inventory, payment, unrelated]
    for event in events:
        event["correlation_id"] = "same-browser-correlation"
    assert related_events(events, "order", observation["payload"]["order_id"]) == events[:3]
    assert related_events(events, "event", payment["event_id"]) == events[:3]


def test_delivery_coordinates_remain_distinct_but_repeated_journal_entries_do_not(observation):
    duplicate = copy.deepcopy(observation["receipt"])
    duplicate["source"]["offset"] += 1
    duplicate["disposition"] = "duplicate_delivery"
    result = merge_observations(
        [observation], [observation["receipt"], observation["receipt"], duplicate], [observation]
    )
    assert len(result) == 2
    assert len({e["key"] for e in result}) == 2
    assert latency_summary(result, {"status": "qualified"})["completed_count"] == 1


def test_conflicting_delivery_does_not_inherit_original_payload(observation):
    conflict = copy.deepcopy(observation["receipt"])
    conflict["source"]["offset"] = 20
    conflict.update(disposition="invalid", reason_code="EVENT_ID_CONFLICT")
    result = merge_observations([observation], [conflict], [])
    assert not result[0].get("payload")
    assert result[0]["receipt"]["reason_code"] == "EVENT_ID_CONFLICT"


def test_broker_and_bronze_hash_mismatch_fails_closed(observation):
    broker = copy.deepcopy(observation)
    broker["raw_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="content-hash mismatch"):
        merge_observations([], [observation["receipt"]], [broker])


def test_timeline_does_not_invent_request_or_missing_clock_times(observation):
    stages = timeline(observation, {"status": "unavailable"})
    assert stages[0]["at"] is None
    assert stages[0]["status"] == "unavailable"
    assert all(s["clock_validity"] == "unavailable" for s in stages)
    assert elapsed("2026-11-14T00:00:00", "2026-11-14T00:00:01Z") is None
    assert elapsed("2026-11-14T00:00:01Z", "2026-11-14T00:00:00Z") is None


def test_timeline_marks_quarantined_and_pending_differently(observation):
    receipt = observation["receipt"]
    receipt["gold_visible_at"] = None
    assert timeline(observation, {})[-1]["status"] == "pending"
    receipt["disposition"] = "invalid"
    assert timeline(observation, {})[-1]["status"] == "failed"


def test_pending_gold_does_not_require_a_completed_timing_sample(observation):
    observation["receipt"].update(gold_visible_at=None, timing_validity="missing")
    assert timeline(observation, {"status": "qualified"})[-1]["status"] == "pending"


def test_timeline_withholds_unqualified_and_recovery_bound_durations(observation):
    assert all(
        stage["since_previous_observed_ms"] is None
        for stage in timeline(observation, {"status": "unqualified"})
    )
    observation["receipt"]["timing_validity"] = "recovery_upper_bound"
    assert timeline(observation, {"status": "qualified"})[-1]["since_previous_observed_ms"] is None


def test_event_trace_expands_targeted_business_identity(observation, monkeypatch, tmp_path):
    payment = copy.deepcopy(observation)
    payment.update(key="payment:0:12", event_id=str(uuid4()), source_service="payments")
    calls = []

    def snapshot(identity):
        calls.append(identity)
        return {
            "events": [payment] if identity == payment["event_id"] else [observation, payment],
            "namespace": "dev",
            "observed_at": "2026-11-14T00:00:01Z",
            "clock": {},
            "unavailable": [],
            "bounds": {},
        }

    runtime = SimpleNamespace(namespace="dev", call=lambda *a, **k: None)
    observer = Observer(runtime, None, tmp_path)
    monkeypatch.setattr(observer, "snapshot", snapshot)
    trace = observer.trace("event", payment["event_id"])
    assert calls == [payment["event_id"], observation["payload"]["order_id"]]
    assert {e["source_service"] for e in trace["events"]} == {"orders", "payments"}


def test_interrupted_fixture_stays_interrupted_until_explicit_recovery(tmp_path):
    identity = str(uuid4())
    folder = tmp_path / identity
    folder.mkdir()
    write_json(folder / "run.json", {"id": identity, "status": "Running"})
    closed = []
    runtime = SimpleNamespace(
        acquire_lease=lambda: SimpleNamespace(close=lambda: closed.append(True)),
        docker=lambda *a: "",
    )
    lab = Lab(runtime, tmp_path)
    assert lab.state()["run"]["status"] == "Interrupted"
    assert lab.state()["run"]["status"] == "Interrupted"
    with pytest.raises(ValueError, match="active fixture"):
        lab.start("duplicate", True)
    assert lab.recover(identity)["run"]["status"] == "Unavailable"
    assert closed == [True]


def test_catalogue_does_not_borrow_unrelated_import_artifacts(tmp_path):
    folder = tmp_path / "artifacts/infra/catalog-local"
    folder.mkdir(parents=True)
    write_json(
        folder / "source_manifest.json",
        {
            "source_sha256": "b" * 64,
            "dataset_revision": "old-dataset",
            "acquired_at": "2026-11-13T00:00:00Z",
        },
    )
    imported = {
        "import_id": str(uuid4()),
        "source_hash": "a" * 64,
        "dataset_revision": "current",
        "rules_version": "v1",
        "canonical_rows": 1,
        "started_at": None,
    }

    class Runtime:
        def container(self, *args):
            raise RuntimeError("Explicit unavailable archive probe")

    observer = Observer(Runtime(), None, tmp_path)
    observer.audit = lambda *args: (imported, {"canonical_active": 1})
    result = observer.catalogue()
    assert result["source"]["source_sha256"] == "a" * 64
    assert result["source"].get("acquired_at") is None
    assert result["source"]["archive_verified"] is None


def test_event_projection_excludes_user_text_and_unrelated_metadata():
    event = safe_event(
        {
            "event_id": "id",
            "payload": {"query_text": "private", "order_id": "public-id"},
            "metadata": {"api_token": "private", "synthetic": True},
        }
    )
    assert event["payload"] == {"order_id": "public-id"}
    assert event["metadata"] == {"synthetic": True}


def test_recording_preserves_frames_and_verifies_content_hash(tmp_path, observation):
    frame = {
        "schema": "journey-snapshot-v1",
        "observed_at": "2026-11-14T00:00:00Z",
        "events": [observation],
    }
    store = Recordings(tmp_path, lambda: frame)
    identity = store.start()["id"]
    store.capture()
    store.finish()
    saved = store.read(identity)
    assert saved["frames"] == [frame]
    assert saved["integrity"] == "verified_sha256"
    (tmp_path / identity / "frame-000.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        store.read(identity)


def test_recording_rejects_path_traversal(tmp_path):
    store = Recordings(tmp_path, lambda: {})
    with pytest.raises(ValueError):
        store.read("../../private")


def test_clean_catalogue_fixture_can_publish_metrics_without_inventing_issues(tmp_path):
    from pipelines.catalog.adapter import write_import_metrics

    write_import_metrics(
        tmp_path,
        {"selected_counts": {"canonical_active": 1}, "issue_counts": {}},
        {"parse_seconds": 0.01},
        "copy",
        SimpleNamespace(canonical_rows=1),
    )
    metrics = (tmp_path / "import_metrics.prom").read_text()
    assert "catalog_source_rows_total" in metrics
    assert "catalog_issues_total" not in metrics


def test_recording_capture_bound_is_explicit(tmp_path):
    store = Recordings(tmp_path, lambda: {"observed_at": "2026-11-14T00:00:00Z"})
    identity = store.start()["id"]
    store.current["max_frames"] = 2
    store.capture()
    store.capture()
    assert store.current is None
    assert store.read(identity)["status"] == "frame_limit_reached"


def test_fixture_requires_confirmation_before_lease_or_provider_calls(tmp_path):
    class NeverCalled:
        def acquire_lease(self):
            raise AssertionError("Unconfirmed fixture acquired lease")

    lab = Lab(NeverCalled(), tmp_path)
    for scenario, confirmed in (("race", False), ("unknown", True)):
        with pytest.raises(ValueError):
            lab.start(scenario, confirmed)


def test_diagnostic_connections_are_read_only(monkeypatch, tmp_path):
    calls = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql):
            calls.append(sql)

    monkeypatch.setattr("benchmarks.journey.observer.psycopg.connect", lambda *a, **k: Connection())
    observer = Observer(
        SimpleNamespace(values={"ORDERS_DATABASE_URL": "explicit-test-double"}), None, tmp_path
    )
    assert observer.audit("orders", lambda tx: "read") == "read"
    assert calls == ["SET TRANSACTION READ ONLY"]


def test_local_api_enforces_origin_namespace_and_uuid(tmp_path, monkeypatch):
    runtime = SimpleNamespace(namespace="dev")
    app = create_app(runtime, tmp_path / "failures")
    monkeypatch.setattr(
        app.state.journey,
        "snapshot",
        lambda: {
            "schema": "journey-snapshot-v1",
            "namespace": "dev",
            "observed_at": "2026-11-14T00:00:00Z",
            "events": [],
        },
    )
    with TestClient(app) as client:
        assert client.get("/journey/snapshot").status_code == 403
        headers = {"Origin": ORIGIN}
        assert client.get("/journey/snapshot", headers=headers).status_code == 200
        assert (
            client.get("/journey/snapshot?namespace=bench-unrelated", headers=headers).status_code
            == 404
        )
        assert (
            client.get("/journey/trace?kind=order&id=not-a-uuid", headers=headers).status_code
            == 422
        )
        assert (
            client.post(
                "/journey/lab/start", headers=headers, json={"scenario": "race", "confirmed": False}
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/journey/lab/start",
                headers=headers,
                json={"scenario": "race", "confirmed": "true"},
            ).status_code
            == 422
        )
    assert not list((tmp_path / "data-journey/lab").glob("*/run.json"))
