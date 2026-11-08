"""Deployment/fault configuration with explicit Docker command doubles."""

import asyncio
import json
from copy import deepcopy

import pytest

from infra import analytics_deployment as deployment
from pipelines.ingestion.runtime import worker_allocation


def context(partitions=1, consumers=1, rows=1):
    return {
        "namespace": "bench-adapter",
        "run_id": "fixture",
        "workload_id": "W-PIPE",
        "parameters": {
            "partitions": partitions,
            "consumers": consumers,
            "sink_batch_max_rows": rows,
            "sink_batch_max_wait_ms": 50,
        },
    }


@pytest.mark.parametrize("partitions,consumers", [(1, 1), (3, 1), (3, 3)])
@pytest.mark.parametrize("rows", [1, 100])
def test_fixed_group_resources_and_distinct_consumers(partitions, consumers, rows):
    original = context(partitions, consumers, rows)
    before = deepcopy(original)
    plan = deployment.deployment_plan(original, worker_memory_mib=385, worker_cpu_cores=0.5)
    workers = [v for k, v in plan["services"].items() if "-worker-" in k]
    assert original == before
    assert len(workers) == consumers
    assert sum(int(s["mem_limit"][:-1]) for s in workers) == 385
    assert sum(s["cpus"] for s in workers) == pytest.approx(0.5)
    assert {s["environment"]["ANALYTICS_WORKER_INDEX"] for s in workers} == {
        str(i) for i in range(consumers)
    }
    assert all(s["environment"]["ANALYTICS_WORKERS"] == str(consumers) for s in workers)
    assert all(s["environment"]["SINK_BATCH_MAX_ROWS"] == str(rows) for s in workers)
    assert all(s["ports"][0].startswith("127.0.0.1:") for s in workers)
    api = next(v for k, v in plan["services"].items() if k.endswith("-api"))
    assert api["networks"]["default"]["aliases"] == ["analytics"]


def test_integer_cpu_budget_splits_into_exact_docker_units():
    plan = deployment.deployment_plan(context(3, 3), worker_memory_mib=384, worker_cpu_cores=1)
    units = [
        round(v["cpus"] * 1_000_000_000) for k, v in plan["services"].items() if "-worker-" in k
    ]
    assert sum(units) == 1_000_000_000 and max(units) - min(units) == 1


@pytest.mark.parametrize("namespace", ["dev", "replay-test", "bench-live", "bench-prod-x"])
def test_deployment_refuses_protected_namespaces(namespace):
    value = context()
    value["namespace"] = namespace
    with pytest.raises(ValueError):
        deployment.deployment_plan(value, worker_memory_mib=384, worker_cpu_cores=0.5)


@pytest.mark.parametrize("workers,index", [("2", "0"), ("1", "1"), ("3", "3"), ("true", "0")])
def test_worker_allocation_rejects_invalid_identity(monkeypatch, workers, index):
    monkeypatch.setenv("ANALYTICS_WORKERS", workers)
    monkeypatch.setenv("ANALYTICS_WORKER_INDEX", index)
    with pytest.raises(ValueError):
        worker_allocation()


@pytest.mark.parametrize(
    "field", ["raw_capture_max_bytes", "gold_publish_interval_ms", "outbox_pass_limit"]
)
def test_scaling_cannot_change_frozen_controls(field):
    value = context()
    value["parameters"][field] = 1
    with pytest.raises(ValueError, match="Frozen"):
        deployment.deployment_plan(value, worker_memory_mib=384, worker_cpu_cores=0.5)


def test_shared_broker_fault_is_disabled_without_dedicated_stack_review(monkeypatch):
    runtime = deployment.AnalyticsDeployment(context(), worker_memory_mib=384, worker_cpu_cores=0.5)
    monkeypatch.setenv("BENCHMARK_MODE", "true")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    with pytest.raises(ValueError, match="dedicated"):
        asyncio.run(
            runtime.fault(
                context(),
                "kafka-outage",
                {
                    "target": "kafka",
                    "barrier": None,
                    "duration_seconds": 30,
                    "trigger": "measurement_second",
                },
            )
        )


def test_stop_is_scoped_and_quiescence_requires_every_container(monkeypatch, tmp_path):
    runtime = deployment.AnalyticsDeployment(context(), worker_memory_mib=384, worker_cpu_cores=0.5)
    runtime.path = tmp_path / "private-run" / "compose.json"
    runtime.stage()
    commands = []

    def command(arguments, *, environment):
        commands.append(arguments)
        assert environment["RUN_NAMESPACE"] == "bench-adapter"
        return json.dumps([{"State": "exited"}] * len(runtime.services))

    monkeypatch.setattr(deployment.postgres, "command", command)
    runtime.stop()
    assert commands[-1][-len(runtime.services) :] == list(runtime.services)
    assert "down" not in commands[-1] and "postgres" not in commands[-1]
    assert runtime.quiescent()
    monkeypatch.setattr(runtime, "command", lambda *args: "[]")
    assert not runtime.quiescent()


def test_fault_guards_and_recovery_on_cancellation(monkeypatch):
    runtime = deployment.AnalyticsDeployment(context(), worker_memory_mib=384, worker_cpu_cores=0.5)
    spec = {
        "target": "analytics-consumer-1",
        "barrier": None,
        "duration_seconds": 30,
        "trigger": "measurement_second",
    }
    monkeypatch.setenv("BENCHMARK_MODE", "false")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    with pytest.raises(ValueError, match="Both"):
        asyncio.run(runtime.fault(context(), "consumer-pause", spec))
    monkeypatch.setenv("BENCHMARK_MODE", "true")
    calls = []
    monkeypatch.setattr(runtime, "command", lambda *args: calls.append(args))

    async def cancelled(seconds):
        raise asyncio.CancelledError

    monkeypatch.setattr(deployment.asyncio, "sleep", cancelled)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(runtime.fault(context(), "consumer-pause", spec))
    assert calls == [("pause", runtime.workers[0]), ("unpause", runtime.workers[0])]
