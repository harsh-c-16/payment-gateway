import asyncio
import json
from uuid import uuid4

import pytest

from benchmarks.experiment import admission_reconciliation
from benchmarks.scheduler import Limits, Receipt, run_schedule
from benchmarks.workloads import generate_workload
from tests.benchmarks.doubles import SlowPublisher
from tests.benchmarks.time_double import install_clock_double


@pytest.fixture(autouse=True)
def virtual_elapsed_clock(monkeypatch):
    install_clock_double(monkeypatch)


def execute(
    tmp_path,
    publisher,
    *,
    limit=None,
    duration=0.15,
    drain=0.15,
    rows=None,
    kind="sustained",
):
    manifest = generate_workload(
        "W-PIPE",
        42,
        {"active_skus": ["TEST-SKU"]},
        key_count=1,
        warmup_seconds=0,
        duration_seconds=duration,
        rate_per_second=200,
    ).as_dict()
    if rows is None:
        workload = generate_workload(
            "W-PIPE",
            42,
            {"active_skus": ["TEST-SKU"]},
            key_count=1,
            warmup_seconds=0,
            duration_seconds=duration,
            rate_per_second=200,
        )
        rows = workload.records()
    path = tmp_path / "planned.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    context = {
        "run_id": str(uuid4()),
        "namespace": "bench-test",
        "topic": "bench-test.inventory-events.v1",
    }
    stats = asyncio.run(
        run_schedule(
            path,
            tmp_path,
            publisher,
            context,
            kind=kind,
            warmup_seconds=0,
            duration_seconds=duration,
            drain_seconds=drain,
            limits=limit or Limits(1, 2, 4096),
        )
    )
    emissions = [
        json.loads(line) for line in (tmp_path / "emissions.jsonl").read_text().splitlines()
    ]
    return stats, emissions, manifest


def test_open_loop_slow_publisher_retains_all_offers_and_bounds(tmp_path):
    stats, rows, manifest = execute(tmp_path, SlowPublisher(delay=0.05))
    assert len(rows) == 30 and stats["phases"]["measurement"]["planned"] == 30
    assert stats["peak_pending_count"] <= 2 and stats["peak_pending_bytes"] <= 4096
    assert any(row["outcome"] == "missed" for row in rows)
    assert any((row["scheduling_delay_seconds"] or 0) > 0.01 for row in rows)
    assert sorted(row["scheduled_elapsed_seconds"] for row in rows) == [i / 200 for i in range(30)]
    report = admission_reconciliation(tmp_path, manifest)
    assert not report["passed"] and report["expected_count"] == 30
    assert report["observed_count"] == 30
    assert len(report["missing_or_unadmitted_ids"]) > 0


def test_byte_cap_is_independent_of_count_cap(tmp_path):
    stats, rows, _ = execute(tmp_path, SlowPublisher(body_bytes=2048), limit=Limits(4, 10, 2048))
    assert stats["peak_pending_bytes"] <= 2048
    assert stats["peak_pending_count"] == 1
    assert any(row["error"] == "pending_bytes_limit" for row in rows)


def test_drain_expiry_retains_unknown_active_and_unsent_queue(tmp_path):
    stats, rows, _ = execute(tmp_path, SlowPublisher(delay=10), drain=0.03)
    assert len(rows) == 30
    assert any(row["outcome"] == "unresolved" for row in rows)
    assert any(row["error"] == "drain_deadline_before_send" for row in rows)
    assert stats["pending_count"] == 0
    assert all(row["ack_at"] is None for row in rows)


def test_unknown_ack_never_becomes_zero_latency_success(tmp_path):
    _, rows, _ = execute(tmp_path, SlowPublisher(delay=0, outcome="unknown"), kind="finite")
    assert all(row["outcome"] == "unresolved" for row in rows)
    assert all(row["ack_at"] is None for row in rows)


def test_wrong_ack_identity_is_unresolved(tmp_path):
    class WrongIdentity(SlowPublisher):
        async def send(self, packet, context, mark_send):
            mark_send()
            return Receipt("wrong-id", "accepted")

    _, rows, _ = execute(tmp_path, WrongIdentity(), kind="finite")
    assert rows and all(row["outcome"] == "unresolved" for row in rows)
    assert not any(row["outcome"] == "acknowledged" for row in rows)


def test_intentional_duplicate_reuses_original_wire_bytes_and_identity(tmp_path):
    base = list(
        generate_workload(
            "W-PIPE",
            42,
            {"active_skus": ["TEST-SKU"]},
            key_count=1,
            warmup_seconds=0,
            duration_seconds=1,
            rate_per_second=2,
        ).records()
    )
    base[1] |= {"duplicate_of": 0, "expected_disposition": "duplicate_delivery"}
    _, rows, _ = execute(tmp_path, SlowPublisher(delay=0), rows=base, kind="finite")
    assert rows[0]["event_or_request_id"] == rows[1]["event_or_request_id"]
    assert rows[0]["wire_sha256"] == rows[1]["wire_sha256"]
    assert rows[0]["source"]["offset"] != rows[1]["source"]["offset"]
    assert len((tmp_path / "wire.jsonl").read_text().splitlines()) == 1


def test_cutoff_and_drain_are_saved_separately(tmp_path):
    stats, rows, manifest = execute(tmp_path, SlowPublisher(delay=0.08), limit=Limits(1, 2, 4096))
    report = admission_reconciliation(tmp_path, manifest)
    assert (tmp_path / "cutoff.json").is_file()
    assert stats["cutoff"]["pending_count"] > 0
    assert report["phases"]["measurement"]["acknowledged_after_cutoff"] > 0
    assert report["phases"]["measurement"]["acknowledged_in_window"] < sum(
        row["outcome"] == "acknowledged" for row in rows
    )


@pytest.mark.parametrize("limits", [(0, 1, 1), (1, 10001, 1), (1, 1, 67108865)])
def test_illegal_bounds_are_rejected(limits):
    with pytest.raises(ValueError):
        Limits(*limits)


def test_cancellation_accounts_for_future_offers_without_fabricating_cutoff(tmp_path):
    workload = generate_workload(
        "W-PIPE",
        42,
        {"active_skus": ["TEST-SKU"]},
        key_count=1,
        warmup_seconds=0,
        duration_seconds=1,
        rate_per_second=10,
    )
    path = tmp_path / "planned.jsonl"
    path.write_text("".join(json.dumps(row) + "\n" for row in workload.records()))
    entered = asyncio.Event()

    class Publisher(SlowPublisher):
        async def send(self, packet, context, mark_send):
            mark_send()
            entered.set()
            await asyncio.Event().wait()

    async def run():
        task = asyncio.create_task(
            run_schedule(
                path,
                tmp_path,
                Publisher(),
                {"run_id": str(uuid4()), "namespace": "bench-test", "topic": "test"},
                kind="sustained",
                warmup_seconds=0,
                duration_seconds=1,
                drain_seconds=0.1,
                limits=Limits(1, 2, 4096),
            )
        )
        await entered.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(run())
    rows = [json.loads(line) for line in (tmp_path / "emissions.jsonl").read_text().splitlines()]
    assert len(rows) == 10
    assert sum(row["outcome"] == "unresolved" for row in rows) == 1
    assert sum(row["outcome"] == "missed" for row in rows) == 9
    assert not (tmp_path / "cutoff.json").exists()
    stats = json.loads((tmp_path / "generator.json").read_text())
    assert stats["status"] == "INCOMPLETE" and stats["cutoff"] is None
    assert stats["window_seconds"] is None
    assert not admission_reconciliation(tmp_path, workload.as_dict())["invariant_failures"]
