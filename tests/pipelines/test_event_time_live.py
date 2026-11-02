"""Real PostgreSQL/Parquet event-time tests; no full workload/performance claim."""

import json
import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from pipelines.curation.db import one, rows
from pipelines.curation.event_time import advance_watermark
from pipelines.storage.readers import quarantine
from shared.event_transport.consumer import raw_fingerprint

from . import test_vertical_live as live
from .test_vertical_live import count, curate, event, query, record

vertical = live.vertical
outbox_double = live.outbox_double
pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_VERTICAL_LIVE_TESTS") != "1",
    reason="RUN_VERTICAL_LIVE_TESTS=1 requires real PostgreSQL and the Linux volume",
)


def test_late_fact_revises_complete_window_and_persists_lineage_and_separate_timing(vertical):
    ns, now = vertical.test_namespace, vertical.test_event_time
    old = now - timedelta(minutes=4)
    facts = [event(vertical, 1, old), event(vertical, 2, now)]
    assert (
        curate(vertical, [record(vertical, fact, i) for i, fact in enumerate(facts)]).new_valid == 2
    )
    first = vertical.publish_snapshot(ns)
    assert first.generation == 1
    with vertical.connect() as tx:
        windows = rows(tx, "SELECT * FROM event_time_windows ORDER BY minute")
        assert [r["provisionally_complete"] for r in windows] == [True, False]
    late = event(vertical, 3, old + timedelta(seconds=1))
    assert curate(vertical, [record(vertical, late, 2)]).new_valid == 1
    second = vertical.publish_snapshot(ns)
    assert second.generation == 2
    assert [r["unique_events"] for r in query(vertical).rows] == [2, 1]
    root = json.loads(vertical.store.read(second.input_manifest_ids[0]))
    shard = json.loads(vertical.store.read(root["membership_files"][0]["path"]))
    annotation = shard["sources"][0]
    assert annotation["reason"] == "LATE_RECONCILIATION" and annotation["revision"] == 2
    assert "OUT_OF_ORDER" in annotation["timestamp_quality"]
    assert root["event_time_policy"]["allowed_lateness_seconds"] == 120
    assert root["event_time_status"]["watermark"] == (
        now - timedelta(seconds=120)
    ).isoformat().replace("+00:00", "Z")
    assert curate(vertical, [record(vertical, late, 3)]).duplicate_delivery == 1
    assert vertical.publish_snapshot(ns).generation == 2
    with vertical.connect() as tx:
        timings = rows(tx, "SELECT * FROM event_time_visibility ORDER BY processed_at")
        assert [t["latency_kind"] for t in timings] == [
            "initial_visibility",
            "initial_visibility",
            "late_correction",
        ]
        assert all(t["timing_validity"] == "observed" for t in timings)
        assert all(t["processing_to_visibility_seconds"] >= 0 for t in timings)
        assert tx.execute("SELECT count(*) FROM event_time_observations").fetchone()[0] == 3
    Path("artifacts/m09/late-revision.json").write_text(
        json.dumps(
            {
                "source_commit": vertical.code_commit,
                "namespace": ns,
                "generation": 2,
                "gold_counts": [2, 1],
                "late_lineage": annotation,
                "latency_kinds": [t["latency_kind"] for t in timings],
                "performance_trial": "NOT_RUN; small synthetic correctness fixture",
            },
            indent=2,
        )
    )


def test_idle_partition_exclusion_resume_and_watermark_never_regresses(vertical):
    ns, now = vertical.test_namespace, vertical.test_event_time
    first = record(vertical, event(vertical, 1, now - timedelta(seconds=100)))
    second = replace(record(vertical, event(vertical, 2, now), 0), partition=1)
    curate(vertical, [first, second])
    with vertical.connect() as tx, tx.transaction():
        before = one(tx, "SELECT * FROM event_time_watermarks")["watermark"]
        assert before == now - timedelta(seconds=220)
        # Age only this fixture's partition, with the exact 10-second boundary.
        at = tx.execute("SELECT clock_timestamp()").fetchone()[0]
        tx.execute(
            "UPDATE event_time_partitions SET last_seen_at=%s WHERE partition=0",
            (at - timedelta(seconds=10),),
        )
        assert advance_watermark(tx, ns, at)["watermark"] == now - timedelta(seconds=120)
    resumed = record(vertical, event(vertical, 3, now - timedelta(seconds=110)), 1)
    assert curate(vertical, [resumed]).new_valid == 1
    with vertical.connect() as tx, tx.transaction():
        annotation = one(
            tx,
            "SELECT * FROM event_time_observations WHERE event_id=%s",
            (resumed and json.loads(resumed.value_bytes)["event_id"],),
        )
        assert annotation["reason"] == "LATE_RECONCILIATION"
        assert "RESUMED_IDLE_PARTITION" in annotation["timestamp_quality"]
        assert one(tx, "SELECT * FROM event_time_watermarks")["watermark"] == now - timedelta(
            seconds=120
        )
        tx.execute(
            "UPDATE event_time_partitions SET last_seen_at=clock_timestamp()-interval '11 seconds'"
        )
        status = advance_watermark(tx, ns)
        assert status["active_partitions"] == 0 and status["watermark"] == now - timedelta(
            seconds=120
        )


def test_future_boundary_quarantine_does_not_poison_watermark(vertical, outbox_double):
    ingress = datetime.now(UTC)
    allowed = event(vertical, 1, ingress + timedelta(seconds=5))
    rejected = event(vertical, 2, ingress + timedelta(seconds=5, microseconds=1))
    sources = [
        replace(record(vertical, fact, i), ingested_at=ingress)
        for i, fact in enumerate([allowed, rejected])
    ]
    outcome = curate(vertical, sources)
    assert outcome.new_valid == outcome.invalid == 1
    page = quarantine(vertical.connect, vertical.test_namespace)
    assert page.records[0].reason_code.value == "FUTURE_TIMESTAMP"
    with vertical.connect() as tx:
        assert (
            one(tx, "SELECT * FROM event_time_partitions")["maximum_event_time"]
            == allowed.event_time
        )
        assert one(tx, "SELECT * FROM event_time_observations")["timestamp_quality"] == [
            "FUTURE_WITHIN_TOLERANCE"
        ]
    assert count(vertical, "silver_events") == count(vertical, "test_outbox_double") == 1


def test_timestamp_state_rolls_back_with_sink_failure(vertical, monkeypatch):
    from pipelines.curation import event_time

    source = record(vertical, event(vertical))
    actual = event_time.advance_watermark
    calls = []

    def fail_after_partition(*args, **kwargs):
        calls.append(True)
        result = actual(*args, **kwargs)
        if len(calls) == 2:
            raise OSError("explicit SQL failure after partition update")
        return result

    monkeypatch.setattr(event_time, "advance_watermark", fail_after_partition)
    with pytest.raises(OSError):
        curate(vertical, [source])
    with vertical.connect() as tx:
        for table in ("event_time_partitions", "event_time_watermarks", "event_time_observations"):
            assert tx.execute("SELECT count(*) FROM " + table).fetchone()[0] == 0
        assert tx.execute("SELECT disposition FROM source_receipts").fetchone()[0] is None
    assert count(vertical, "silver_events") == count(vertical, "pipeline_minute") == 0
    monkeypatch.setattr(event_time, "advance_watermark", actual)
    assert curate(vertical, [source]).new_valid == 1


def test_restricted_quarantine_inspection_contains_references_not_raw_content(
    vertical, outbox_double
):
    source = record(vertical, event(vertical))
    secret = b"\xff-SYNTHETIC-RESTRICTED-CONTENT"
    source = replace(
        source,
        value_bytes=secret,
        raw_sha256=raw_fingerprint(source.key_bytes, secret, source.headers),
    )
    assert curate(vertical, [source]).invalid == 1
    page = quarantine(vertical.connect, vertical.test_namespace)
    assert page.records[0].source_locator.raw_locator.startswith("bronze/")
    assert "SYNTHETIC-RESTRICTED" not in page.model_dump_json()
    assert page.records[0].reason_code.value == "INVALID_UTF8"
    assert count(vertical, "silver_events") == 0


def test_out_of_order_within_allowance_and_exact_watermark_boundary_are_not_late(vertical):
    now = vertical.test_event_time
    for i, seconds in enumerate([0, 60, 120, 121]):
        fact = event(vertical, i + 1, now - timedelta(seconds=seconds))
        assert curate(vertical, [record(vertical, fact, i)]).new_valid == 1
    with vertical.connect() as tx:
        annotations = rows(tx, "SELECT * FROM event_time_observations ORDER BY processed_at")
        assert [r["reason"] for r in annotations] == [
            "INGESTION",
            "INGESTION",
            "INGESTION",
            "LATE_RECONCILIATION",
        ]
        assert annotations[1]["timestamp_quality"] == ["OUT_OF_ORDER"]
        assert annotations[2]["timestamp_quality"] == ["OUT_OF_ORDER"]


def test_late_visibility_recovery_retains_upper_bound_classification(vertical, monkeypatch):
    ns, now = vertical.test_namespace, vertical.test_event_time
    curate(vertical, [record(vertical, event(vertical, 1, now))])
    vertical.publish_snapshot(ns)
    late = event(vertical, 2, now - timedelta(minutes=4))
    curate(vertical, [record(vertical, late, 1)])
    original = vertical._observe

    def lost(*args):
        raise OSError("explicit loss after pointer commit before observation")

    monkeypatch.setattr(vertical, "_observe", lost)
    with pytest.raises(OSError):
        vertical.publish_snapshot(ns)
    with vertical.connect() as tx:
        missing = one(tx, "SELECT * FROM event_time_visibility WHERE event_id=%s", (late.event_id,))
        assert missing["latency_kind"] == "late_correction"
        assert missing["observed_at"] is None and missing["timing_validity"] == "missing"
    monkeypatch.setattr(vertical, "_observe", original)
    vertical.recover_observations(ns)
    with vertical.connect() as tx:
        recovered = one(
            tx, "SELECT * FROM event_time_visibility WHERE event_id=%s", (late.event_id,)
        )
        assert recovered["latency_kind"] == "late_correction"
        assert recovered["observed_at"] is not None
        assert recovered["timing_validity"] == "recovery_upper_bound"
    assert vertical.publish_snapshot(ns).generation == 2
