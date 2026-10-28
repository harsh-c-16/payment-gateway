import json
import xml.etree.ElementTree as ET

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
