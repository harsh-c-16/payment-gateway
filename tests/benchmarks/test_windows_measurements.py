"""Measurement integrity tests; no CI/CD or fabricated performance results."""

import json

import pytest

from benchmarks.windows.evidence import clock_probe
from benchmarks.windows.measure import compare, summarize


def test_direction_zero_and_all_repetitions_are_retained():
    result = compare([10, 20, 30], [20, 30, 40])
    assert result["improvement_percent"] == -50
    assert result["baseline_values"] == [10, 20, 30]
    assert result["candidate"]["min"] == 20
    assert compare([0], [1])["improvement_percent"] is None
    with pytest.raises(ValueError, match="paired"):
        compare([1, 2, 3], [1, 2])


def test_clock_bound_includes_round_trip_and_detects_host_step(monkeypatch):
    wall = iter([100.0, 100.2])
    monotonic = iter([10.0, 10.2])
    monkeypatch.setattr("benchmarks.windows.evidence.time.time", lambda: next(wall))
    monkeypatch.setattr("benchmarks.windows.evidence.time.perf_counter", lambda: next(monotonic))
    receipt = clock_probe(lambda: 100.15, samples=1)
    assert receipt["best"]["offset_ms"] == pytest.approx(50)
    assert receipt["best"]["offset_bound_ms"] == pytest.approx(150)


def test_failed_verification_cannot_leave_a_stale_passed_receipt(tmp_path, monkeypatch):
    from benchmarks.windows import evidence

    receipt = tmp_path / "controls.json"
    receipt.write_text('{"passed": true}')
    monkeypatch.setattr(evidence, "desktop_only", lambda: None)

    def unavailable(*args, **kwargs):
        raise RuntimeError("Unavailable")

    monkeypatch.setattr(evidence, "_live_snapshot", unavailable)
    with pytest.raises(RuntimeError):
        evidence.live_snapshot(receipt)
    facts = json.loads(receipt.read_text())
    assert facts["passed"] is False and facts["status"] == "FAILED"


def test_clock_gate_rejects_a_host_step_even_when_offset_bound_is_small(monkeypatch):
    from benchmarks.windows import evidence

    monkeypatch.setattr(
        evidence,
        "clock_probe",
        lambda read: {"best": {"offset_bound_ms": 20}, "samples": [{"host_clock_step_ms": 1000}]},
    )
    assert evidence.clocks(["explicit-test-container"])["passed"] is False


@pytest.mark.parametrize("tamper", [False, True])
def test_diagnostic_report_checks_hash_and_cannot_promote_a_failed_run(tmp_path, tamper):
    from benchmarks.windows.evidence import digest, write
    from benchmarks.windows.report import rebuild

    rows = []
    for axis, variants in (
        ("import", ("I0", "I1")),
        ("index", ("B0", "O2")),
        ("batch", ("B0", "O1")),
        ("compaction", ("small_files", "compacted")),
    ):
        rows += [
            {
                "axis": axis,
                "variant": variant,
                "repetition": 1,
                "seconds": 2 - number,
                "result": "explicit-test-double",
            }
            for number, variant in enumerate(variants)
        ]
    journal = tmp_path / "measurements.jsonl"
    journal.write_text("\n".join(json.dumps(r) for r in rows))
    write(
        tmp_path / "manifest.json",
        {"status": "FAILED", "repetitions": 1, "files": {"measurements.jsonl": digest(journal)}},
    )
    if tamper:
        journal.write_text(journal.read_text() + "\n{}")
        with pytest.raises(ValueError, match="manifest hash"):
            rebuild(tmp_path, tmp_path / "report")
    else:
        result = rebuild(tmp_path, tmp_path / "report")
        assert result["source_status"] == "FAILED"
        assert result["qualified_performance_claim"] is False
        assert result["status"] == "DIAGNOSTIC_ONLY"


def test_comparison_rejects_one_changed_execution_and_missing_pair():
    rows = [
        {"axis": "batch", "variant": variant, "repetition": rep, "seconds": 1, "result": "same"}
        for variant in ("B0", "O1")
        for rep in (1, 2, 3)
    ]
    assert summarize(rows, 3)["batch"]["correctness_equal"]
    rows[-1]["result"] = "changed"
    with pytest.raises(AssertionError, match="Logical results"):
        summarize(rows, 3)
    with pytest.raises(ValueError, match="No measurements"):
        summarize(rows[:-1], 3)
