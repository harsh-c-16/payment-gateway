"""Cancellation regression with explicit P8 providers; no real integration claim."""

import asyncio

import pytest


@pytest.mark.parametrize("stage", ["prepare", "exercise", "audit"])
def test_cancelled_integration_retains_every_selected_case(workspace, stage):
    from dataclasses import replace

    from benchmarks.integration import run_cases
    from projectctl.providers import ProviderRegistry
    from tests.integration.doubles import EventCaseDouble
    from tests.integration.test_p8 import invocation, rows

    double = EventCaseDouble(workspace)

    async def cancel(*args):
        raise asyncio.CancelledError()

    registry = ProviderRegistry()
    registry.register_case("smoke/G1", replace(double.binding, **{stage: cancel}))
    result = asyncio.run(run_cases(invocation(["smoke"]), registry, allow_test_doubles=True))
    directory, records = rows(workspace, result)
    assert result["exit_code"] == 4
    assert len(records) == 3
    assert records[0]["status"] == "INCOMPLETE"
    assert all(row["status"] == "NOT_RUN" for row in records[1:])
    assert all("cancelled" in row["failure_reason"] for row in records)
    assert (directory / "manifest.json").is_file()
    assert (
        double.calls
        == {"prepare": [], "exercise": ["prepare"], "audit": ["prepare", "exercise"]}[stage]
    )
