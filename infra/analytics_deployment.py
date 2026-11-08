"""Explicit, namespace-scoped analytics deployment; no infrastructure auto-start."""

import asyncio
import copy
import json
import math
import os
from datetime import UTC, datetime

import yaml
from pydantic import TypeAdapter

from infra import postgres, streaming
from pipelines.curation import BatchConfig
from pipelines.ingestion.lifecycle import isolated_namespace
from shared.contracts.common import Identifier


def deployment_plan(context, *, worker_memory_mib, worker_cpu_cores):
    """Split an explicit fixed group budget; never multiply it by the replica count."""
    namespace = isolated_namespace(context["namespace"])
    run_id = TypeAdapter(Identifier).validate_python(context["run_id"])
    parameters = context["parameters"]
    workers, partitions = parameters["consumers"], parameters["partitions"]
    if (
        type(workers) is not int
        or type(partitions) is not int
        or (partitions, workers) not in {(1, 1), (3, 1), (3, 3)}
    ):
        raise ValueError("Use P10, P30 or P33 partition/consumer topology")
    rows = BatchConfig(
        run_id=run_id, sink_batch_max_rows=parameters["sink_batch_max_rows"]
    ).sink_batch_max_rows
    if parameters["sink_batch_max_wait_ms"] != 50:
        raise ValueError("Sink collection wait must remain 50 ms")
    for field, expected in {
        "raw_capture_max_bytes": 2097152,
        "raw_capture_max_wait_ms": 50,
        "gold_publish_interval_ms": 250,
        "outbox_poll_ms": 25,
        "outbox_pass_limit": 100,
    }.items():
        if (
            type(parameters.get(field, expected)) is not int
            or parameters.get(field, expected) != expected
        ):
            raise ValueError("Frozen capture/publication/relay controls cannot change")
    if type(worker_memory_mib) is not int or worker_memory_mib < 3:
        raise ValueError("An explicit positive group memory budget is required")
    if (
        type(worker_cpu_cores) not in (int, float)
        or not math.isfinite(worker_cpu_cores)
        or worker_cpu_cores <= 0
    ):
        raise ValueError("An explicit finite positive group CPU budget is required")
    cpu_units = worker_cpu_cores * 1_000_000_000
    if cpu_units % 1 or cpu_units < workers:
        raise ValueError("CPU budget must fit Docker's integer NanoCPU units")
    cpu_units = int(cpu_units)
    base = yaml.safe_load((postgres.ROOT / "infra/compose.analytics.yaml").read_text())
    services = {}
    for index in range(workers):
        service = copy.deepcopy(base["services"]["analytics-worker"])
        service.pop("profiles", None)
        memory = worker_memory_mib // workers + (index < worker_memory_mib % workers)
        cpu_share = cpu_units // workers + (index < cpu_units % workers)
        service.update(mem_limit=f"{memory}m", cpus=cpu_share / 1_000_000_000)
        service["environment"].update(
            RUN_NAMESPACE=namespace,
            RUN_ID=run_id,
            SINK_BATCH_MAX_ROWS=str(rows),
            ANALYTICS_WORKERS=str(workers),
            ANALYTICS_WORKER_INDEX=str(index),
        )
        # Worker metrics have separate listeners; API and worker registries are not interchangeable.
        service["ports"] = [f"127.0.0.1:{18060 + index}:8006"]
        services[f"m4-{namespace}-worker-{index}"] = service
    api = copy.deepcopy(base["services"]["analytics"])
    api.pop("profiles", None)
    api["healthcheck"]["test"][-1] = api["healthcheck"]["test"][-1].replace(
        "/health/live", "/health/ready"
    )
    api["environment"].update(
        RUN_NAMESPACE=namespace,
        RUN_ID=run_id,
        SINK_BATCH_MAX_ROWS=str(rows),
        ANALYTICS_WORKERS="1",
        ANALYTICS_WORKER_INDEX="0",
    )
    api["networks"] = {"default": {"aliases": ["analytics"]}}
    services[f"m4-{namespace}-api"] = api
    return {"services": services}


class AnalyticsDeployment:
    """One serial run on the existing stack; stop touches only its named services."""

    def __init__(self, context, *, worker_memory_mib, worker_cpu_cores, dedicated_stack=False):
        if type(dedicated_stack) is not bool:
            raise ValueError("Explicit dedicated-stack review statement required")
        self.dedicated_stack = dedicated_stack
        self.context = copy.deepcopy(context)
        self.plan = deployment_plan(
            context, worker_memory_mib=worker_memory_mib, worker_cpu_cores=worker_cpu_cores
        )
        self.namespace, self.run_id = context["namespace"], context["run_id"]
        self.path = (
            postgres.ROOT / "artifacts/infra/analytics/runs" / self.namespace / "compose.json"
        )
        self.services = tuple(self.plan["services"])
        self.workers = tuple(s for s in self.services if "-worker-" in s)

    def command(self, *arguments):
        if not self.path.is_file():
            raise RuntimeError("Deployment has not been staged")
        return postgres.command(
            [
                "docker",
                "compose",
                "--project-name",
                postgres.PROJECT,
                "--file",
                str(postgres.COMPOSE),
                "--file",
                str(postgres.ROOT / "infra/compose.streaming.yaml"),
                "--file",
                str(postgres.ROOT / "infra/compose.analytics.yaml"),
                "--file",
                str(self.path),
                *arguments,
            ],
            environment={
                **os.environ,
                "RUN_NAMESPACE": self.namespace,
                "RUN_ID": self.run_id,
                "POSTGRES_SECRETS_DIR": (postgres.RUNTIME / "secrets").as_posix(),
            },
        )

    def stage(self):
        self.path.parent.mkdir(parents=True, exist_ok=False)
        # Values contain only public run identity/resources; credentials remain external secrets.
        self.path.write_text(json.dumps(self.plan, indent=2), encoding="utf-8")

    def start(self):
        self.command("up", "-d", "--no-deps", "--wait", "--wait-timeout", "60", *self.services)

    def stop(self):
        self.command("stop", "--timeout", "30", *self.services)

    def quiescent(self):
        result = self.command("ps", "--all", "--format", "json", *self.services).strip()
        states = (
            []
            if not result
            else (
                json.loads(result)
                if result.startswith("[")
                else [json.loads(line) for line in result.splitlines()]
            )
        )
        return len(states) == len(self.services) and all(
            row["State"] in {"exited", "dead", "created"} for row in states
        )

    def check_context(self, context):
        if (context["namespace"], context["run_id"]) != (self.namespace, self.run_id):
            raise ValueError("Deployment and callback run identity differ")
        if context["parameters"] != self.context["parameters"]:
            raise ValueError("Deployment parameters changed after resource allocation")

    async def fault(self, context, profile, spec):
        self.check_context(context)
        isolated_namespace(context["namespace"])
        if any(
            os.environ.get(flag, "false").lower() != "true"
            for flag in ("BENCHMARK_MODE", "FAULT_INJECTION_ENABLED")
        ):
            raise ValueError("Both isolated benchmark fault flags must be enabled")
        allowed = {
            "consumer-pause": ("analytics-consumer-1", "pause", "unpause", self.workers[:1]),
            "analytics-outage": ("analytics", "stop", "start", self.services),
            "kafka-outage": ("kafka", "stop", "start", ("kafka",)),
        }
        if profile not in allowed:
            raise ValueError("Only this deployment's consumer/analytics faults are supported")
        target, action, recover, services = allowed[profile]
        if profile == "kafka-outage" and not self.dedicated_stack:
            raise ValueError("Broker outage requires a reviewed dedicated isolated stack")
        duration = spec["duration_seconds"]
        if (
            spec["target"] != target
            or spec.get("barrier") is not None
            or spec.get("trigger") != "measurement_second"
            or type(duration) not in (int, float)
            or not math.isfinite(duration)
            or not 0 < duration <= 30
        ):
            raise ValueError("Invalid scoped fault target/boundary/duration")
        started = datetime.now(UTC).isoformat()
        command = streaming.compose if profile == "kafka-outage" else self.command
        await asyncio.to_thread(command, action, *services)
        try:
            await asyncio.sleep(duration)
        finally:
            await asyncio.to_thread(command, recover, *services)
        return {
            "acknowledged": True,
            "namespace": self.namespace,
            "run_id": self.run_id,
            "fault_profile": profile,
            "barrier": None,
            "target": target,
            "started_at": started,
            "recovered_at": datetime.now(UTC).isoformat(),
        }
