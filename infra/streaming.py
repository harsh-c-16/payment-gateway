"""Low-memory infrastructure providers; domain schema readiness belongs to M02."""

import json
import os
import re

import httpx
import psycopg
from confluent_kafka import KafkaError, KafkaException
from confluent_kafka.admin import AdminClient, ConfigResource, NewTopic

from infra import postgres
from projectctl.models import ExitCode
from projectctl.providers import ProviderResult

ROOT = postgres.ROOT
RUNTIME = ROOT / "artifacts/infra/streaming-local"
REGISTRY = "http://127.0.0.1:8081"
BOOTSTRAP = "127.0.0.1:9092"
DOMAINS = (
    "conversation-events",
    "retrieval-events",
    "order-events",
    "inventory-events",
    "payment-events",
    "dead-letter",
)


def compose(*arguments):
    return postgres.command(
        [
            "docker",
            "compose",
            "--project-name",
            postgres.PROJECT,
            "--file",
            str(postgres.COMPOSE),
            "--file",
            str(ROOT / "infra/compose.streaming.yaml"),
            *arguments,
        ],
        environment={
            **os.environ,
            "POSTGRES_SECRETS_DIR": (postgres.RUNTIME / "secrets").as_posix(),
        },
        timeout=600 if arguments[0] == "up" else 180,
    )


def topic_names(namespace):
    if namespace != "dev" and not re.fullmatch(r"(?:bench|replay)-[a-z0-9-]{1,54}", namespace):
        raise ValueError("Topic namespace must be dev or an isolated bench-/replay- name.")
    return [f"{namespace}.{domain}.v1" for domain in DOMAINS]


def verify_topics(admin, namespace, partitions=1):
    names = topic_names(namespace)
    metadata = admin.list_topics(timeout=15)
    resources = [ConfigResource(ConfigResource.Type.TOPIC, name) for name in names]
    descriptions = admin.describe_configs(resources, request_timeout=15)
    for resource in resources:
        topic = metadata.topics.get(resource.name)
        if (
            topic is None
            or topic.error
            or len(topic.partitions) != partitions
            or any(len(p.replicas) != 1 or len(p.isrs) != 1 for p in topic.partitions.values())
        ):
            raise postgres.SetupError("Missing topic or incorrect partitions/replicas/ISR.")
        config = descriptions[resource].result(timeout=20)
        if (
            config["retention.ms"].value != "604800000"
            or config["cleanup.policy"].value != "delete"
        ):
            raise postgres.SetupError(
                "Topic retention or cleanup policy differs; no mutation made."
            )
    return {
        "topics": names,
        "partitions": partitions,
        "retention_ms": 604800000,
        "configured_consumer_groups": {
            "analytics": f"{namespace}.analytics.v1",
            "catalog_stock": f"{namespace}.catalog-stock.v1",
        },
    }


def provision_topics(namespace, partitions=1):
    if type(partitions) is not int or partitions < 1:
        raise ValueError("Partition count must be a positive integer.")
    names = topic_names(namespace)
    admin = AdminClient({"bootstrap.servers": BOOTSTRAP})
    futures = admin.create_topics(
        [
            NewTopic(
                name,
                num_partitions=partitions,
                replication_factor=1,
                config={"retention.ms": "604800000", "cleanup.policy": "delete"},
            )
            for name in names
        ],
        request_timeout=20,
    )
    for future in futures.values():
        try:
            future.result(timeout=25)
        except KafkaException as exc:
            if exc.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
                raise
    return verify_topics(admin, namespace, partitions)


def container_facts(service, limits, expected_image):
    container = compose("ps", "--quiet", service)
    if not container or len(container.splitlines()) != 1:
        raise postgres.SetupError(f"Exactly one {service} container must be running.")
    state = json.loads(
        postgres.command(
            [
                "docker",
                "inspect",
                "--format",
                '{"id":{{json .Id}},"health":{{json .State.Health.Status}},'
                '"memory":{{json .HostConfig.Memory}},"cpu":{{json .HostConfig.NanoCpus}},'
                '"image":{{json .Config.Image}},"mounts":{{json .Mounts}},'
                '"ports":{{json .NetworkSettings.Ports}},"oom_killed":{{json .State.OOMKilled}}}',
                container,
            ]
        )
    )
    port = "19092/tcp" if service == "kafka" else "8081/tcp"
    host_port = "9092" if service == "kafka" else "8081"
    if (
        state["health"] != "healthy"
        or state["oom_killed"]
        or state["memory"] != limits["memory_mib"] * 1024 * 1024
        or state["cpu"] != int(limits["cpu_cores"] * 1000000000)
        or state["image"] != expected_image
        or state["ports"].get(port) != [{"HostIp": "127.0.0.1", "HostPort": host_port}]
    ):
        raise postgres.SetupError(f"{service} health, image, loopback port or limits differ.")
    if service == "kafka":
        mounts = [m for m in state["mounts"] if m["Destination"] == "/var/lib/kafka/data"]
        if len(mounts) != 1 or mounts[0]["Type"] != "volume" or not mounts[0]["RW"]:
            raise postgres.SetupError("Kafka needs its retained writable named volume.")
    return state


def verify():
    postgres.check_engine()
    profile = json.loads((ROOT / "infra/streaming-profile.json").read_text())
    lock = json.loads((ROOT / "infra/images.lock.json").read_text())
    available = int(postgres.command(["docker", "info", "--format", "{{.MemTotal}} "]).strip())
    if available <= profile["total_memory_mib"] * 1024 * 1024:
        raise postgres.SetupError("Docker memory is below the declared development allocations.")
    database = postgres.verify(**profile["services"]["postgres"])
    containers = {
        name: container_facts(name, profile["services"][name], lock[name]["image"])
        for name in ("kafka", "schema-registry")
    }
    with httpx.Client(base_url=REGISTRY, timeout=15, trust_env=False) as client:
        response = client.get("/config")
        response.raise_for_status()
        if response.json()["compatibilityLevel"] != "BACKWARD_TRANSITIVE":
            raise postgres.SetupError("Schema Registry compatibility must be BACKWARD_TRANSITIVE.")
        response = client.get("/subjects")
        response.raise_for_status()
        subjects = response.json()
    volume = json.loads(
        postgres.command(
            [
                "docker",
                "volume",
                "inspect",
                "--format",
                "{{json .}}",
                f"{postgres.PROJECT}_lakehouse_data",
            ]
        )
    )
    if volume["Driver"] != "local" or volume["Labels"].get("group3.owner") != "vichitr":
        raise postgres.SetupError("Shared lakehouse volume ownership differs.")
    return {
        "profile": profile,
        "docker_memory_bytes": available,
        "postgres": database,
        "containers": containers,
        "registry_subjects": subjects,
        "topics": verify_topics(AdminClient({"bootstrap.servers": BOOTSTRAP}), "dev"),
        "lakehouse_volume": volume["Name"],
        "domain_schemas": "NOT_RUN; M02 required",
        "benchmark_readiness": "NOT_RUN",
    }


def adapter(invocation):
    if invocation.arguments.get("profile", "streaming-local") != "streaming-local":
        return ProviderResult(ExitCode.BAD_INPUT, ("Use --profile streaming-local.",), "real")
    try:
        postgres.check_engine()
        if invocation.action == "env up":
            postgres.prepare()
            compose("config", "--quiet")
            compose("up", "--detach", "--wait", "--wait-timeout", "150")
            postgres.command(
                [
                    "docker",
                    "volume",
                    "create",
                    "--label",
                    "group3.owner=vichitr",
                    "--label",
                    "group3.checkpoint=M01b",
                    f"{postgres.PROJECT}_lakehouse_data",
                ]
            )
            provision_topics("dev")
        elif invocation.action == "env down":
            postgres.credentials()
            compose("down", "--timeout", "30")
            return ProviderResult(ExitCode.COMPLETED, ("Stopped; all volumes retained.",), "real")
        facts = verify()
        out = RUNTIME / "checks" / invocation.run_id
        out.mkdir(parents=True, exist_ok=False)
        (out / "streaming.json").write_text(json.dumps(facts, indent=2), encoding="utf-8")
        return ProviderResult(
            ExitCode.COMPLETED,
            (
                "Infrastructure verified; domain schemas/benchmark gates pending.",
                f"Evidence: {out.relative_to(ROOT).as_posix()}/streaming.json",
            ),
            "real",
        )
    except (
        postgres.SetupError,
        httpx.HTTPError,
        KafkaException,
        psycopg.Error,
        TimeoutError,
    ) as exc:
        reason = str(exc) if isinstance(exc, postgres.SetupError) else type(exc).__name__
        return ProviderResult(ExitCode.DEPENDENCY_FAILURE, (reason,), "real")


def register(registry):
    for action in ("env up", "env verify", "env down"):
        registry.register(action, adapter)
