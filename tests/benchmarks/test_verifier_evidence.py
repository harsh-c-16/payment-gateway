import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from types import SimpleNamespace

import pytest

from benchmarks.manual.verify_p7 import scenario_results


@pytest.mark.parametrize(
    "verdict,expected",
    [(None, "PASS"), ("failure", "FAIL"), ("error", "FAIL"), ("skipped", "NOT_RUN")],
)
def test_scenario_evidence_uses_junit_verdict_even_when_property_was_recorded(verdict, expected):
    junit = ET.Element("testsuites")
    test = ET.SubElement(junit, "testcase", name="scenario")
    properties = ET.SubElement(test, "properties")
    row = {
        "scenario_id": "audit-case",
        "namespace": "bench-audit",
        "started_at": "2026-10-27T00:00:00Z",
        "completed_at": "2026-10-27T00:00:01Z",
    }
    ET.SubElement(properties, "property", name="assistant_turn", value=json.dumps(row))
    if verdict:
        ET.SubElement(test, verdict, message="fixture teardown failed after recording property")
    rows, cases = scenario_results(junit, "f" * 64)
    assert rows == [row]
    assert cases[0]["status"] == expected
    assert cases[0]["assertions"][0]["passed"] == (expected == "PASS")
    assert (cases[0]["failure_reason"] is None) == (expected == "PASS")


def test_p7_selects_fixed_traces_from_combined_p7_p11_junit():
    junit = ET.Element("testsuites")
    for mode in ("fixed", "assist"):
        test = ET.SubElement(junit, "testcase", name=mode)
        properties = ET.SubElement(test, "properties")
        row = {
            "scenario_id": "same-scenario",
            "mode": mode,
            "namespace": "bench-" + mode,
            "started_at": "2026-10-28T00:00:00Z",
            "completed_at": "2026-10-28T00:00:01Z",
        }
        ET.SubElement(properties, "property", name="assistant_turn", value=json.dumps(row))
    rows, cases = scenario_results(junit, "f" * 64)
    assert len(rows) == len(cases) == 1
    assert rows[0]["mode"] == "fixed"


@pytest.mark.parametrize(
    "real_exit,expected", [(0, True), (4, True), (2, False), (3, False), (5, False)]
)
def test_p11_checkpoint_distinguishes_missing_provider_from_executed_failure(real_exit, expected):
    from benchmarks.manual.verify_p11 import checkpoint_passed

    counts = {"tests": 120, "failures": 0, "errors": 0, "skipped": 0}
    checks = [{"exit_code": 0}, {"exit_code": real_exit}]
    assert checkpoint_passed(checks, counts, {"modes": {}}, True) is expected
    assert not checkpoint_passed(checks, counts, {"modes": {}}, False)
    assert not checkpoint_passed(checks, {**counts, "skipped": 1}, {"modes": {}}, True)


@pytest.mark.parametrize("partial", ["partial evidence", b"partial evidence", None])
def test_p5_retains_timeout_evidence_and_records_remaining_checks(tmp_path, monkeypatch, partial):
    from benchmarks.manual import verify_p5

    monkeypatch.setattr(verify_p5, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["verify_p5.py"])
    monkeypatch.setattr(
        verify_p5, "Preservation", lambda *_: SimpleNamespace(matches=lambda *_: True)
    )
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        if len(calls) == 1:
            raise subprocess.TimeoutExpired(command, 240, output=partial, stderr=partial)
        expected = 4 if command[1:5] == ["-m", "projectctl", "contracts", "check"] else 0
        return subprocess.CompletedProcess(command, expected, "", "")

    monkeypatch.setattr(verify_p5.subprocess, "run", run)
    assert verify_p5.main() == 1
    evidence = next((tmp_path / "artifacts/p5").glob("*/checks.json"))
    checks = json.loads(evidence.read_text())
    assert len(checks) == len(calls) == 11
    assert checks[0]["actual_exit"] is None and checks[0]["passed"] is False
    assert checks[0]["stdout"] == ("partial evidence" if partial else "")
    assert "partial output retained" in checks[0]["stderr"]
    assert all(check["passed"] for check in checks[1:])


def test_windows_checkpoint_retries_sharing_lock_and_preserves_failure(monkeypatch, tmp_path):
    from pathlib import Path

    from benchmarks.manual import verify_p5

    source, target = tmp_path / "pending.json", tmp_path / "checks.json"
    source.write_text("new checkpoint")
    target.write_text("previous checkpoint")
    actual = Path.replace
    calls = []

    def locked(path, destination):
        calls.append(path)
        if len(calls) < 3:
            error = PermissionError("explicit Windows sharing-lock double")
            error.winerror = 32
            raise error
        return actual(path, destination)

    monkeypatch.setattr(Path, "replace", locked)
    monkeypatch.setattr(verify_p5, "sleep", lambda _: None)
    verify_p5.replace_checkpoint(source, target)
    assert len(calls) == 3 and target.read_text() == "new checkpoint"

    source.write_text("next checkpoint")
    calls.clear()

    def permanent(path, destination):
        calls.append(path)
        error = PermissionError("persistent Windows lock double")
        error.winerror = 5
        raise error

    monkeypatch.setattr(Path, "replace", permanent)
    with pytest.raises(PermissionError):
        verify_p5.replace_checkpoint(source, target)
    assert len(calls) == 5 and target.read_text() == "new checkpoint"
    assert source.read_text() == "next checkpoint"
