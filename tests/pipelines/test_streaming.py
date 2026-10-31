"""Offline infrastructure checks; no broker or registry is simulated as a real pass."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
import yaml
from confluent_kafka import KafkaError, KafkaException

from infra import postgres, streaming
from projectctl.models import ExitCode
from projectctl.providers import Invocation, ProviderRegistry


@pytest.mark.parametrize(
    "namespace", ["", "prod", "dev.bad", "bench-../x", "replay-", "bench-" + "a" * 55]
)
def test_topic_namespace_rejects_unscoped_or_invalid_input(namespace):
    with pytest.raises(ValueError):
        streaming.topic_names(namespace)


def test_business_and_dlq_topics_are_separate_and_namespaced():
    names = streaming.topic_names("dev")
    assert len(names) == len(set(names)) == 6
    assert "dev.inventory-events.v1" in names and "dev.dead-letter.v1" in names
    assert all(name.startswith("bench-case.") for name in streaming.topic_names("bench-case"))


def test_streaming_startup_has_a_bounded_cold_boot_budget(monkeypatch):
    calls = []
    monkeypatch.setattr(postgres, "command", lambda args, **kwargs: calls.append(kwargs))
    streaming.compose("up", "--detach")
    streaming.compose("ps", "--quiet")
    assert [call["timeout"] for call in calls] == [600, 180]


def test_allocations_fit_current_engine_and_images_are_pinned():
    profile = json.loads((streaming.ROOT / "infra/streaming-profile.json").read_text())
    overlay = yaml.safe_load((streaming.ROOT / "infra/compose.streaming.yaml").read_text())
    lock = json.loads((streaming.ROOT / "infra/images.lock.json").read_text())
    assert sum(s["memory_mib"] for s in profile["services"].values()) == 2176
    assert profile["total_memory_mib"] == 2176 < 4040888320 / 1024**2
    for name, limits in profile["services"].items():
        service = overlay["services"][name]
        assert service["mem_limit"] == f"{limits['memory_mib']}m"
        assert service["cpus"] == limits["cpu_cores"]
        if name != "postgres":
            assert service["image"] == lock[name]["image"]
            assert "@sha256:" in service["image"]
    assert overlay["services"]["kafka"]["environment"]["KAFKA_AUTO_CREATE_TOPICS_ENABLE"] == "false"
    assert (
        overlay["services"]["schema-registry"]["depends_on"]["kafka"]["condition"]
        == "service_healthy"
    )


class AdminDouble:
    def __init__(self, *, partitions=1, retention="604800000", existing=False):
        self.partitions, self.retention, self.existing = partitions, retention, existing
        self.created = []

    def create_topics(self, topics, **kwargs):
        self.created = topics

        def result(timeout):
            if self.existing:
                raise KafkaException(KafkaError(KafkaError.TOPIC_ALREADY_EXISTS))

        return {topic.topic: SimpleNamespace(result=result) for topic in topics}

    def list_topics(self, **kwargs):
        return SimpleNamespace(
            topics={
                name: SimpleNamespace(
                    error=None,
                    partitions={
                        i: SimpleNamespace(replicas=[1], isrs=[1]) for i in range(self.partitions)
                    },
                )
                for name in streaming.topic_names("dev")
            }
        )

    def describe_configs(self, resources, **kwargs):
        config = {
            "retention.ms": SimpleNamespace(value=self.retention),
            "cleanup.policy": SimpleNamespace(value="delete"),
        }
        return {resource: SimpleNamespace(result=lambda timeout: config) for resource in resources}


@pytest.mark.parametrize("mismatch", ["partitions", "retention"])
def test_existing_topic_mismatch_is_rejected_without_repartitioning(monkeypatch, mismatch):
    admin = AdminDouble(
        partitions=3 if mismatch == "partitions" else 1,
        retention="1000" if mismatch == "retention" else "604800000",
        existing=True,
    )
    monkeypatch.setattr(streaming, "AdminClient", lambda config: admin)
    with pytest.raises(postgres.SetupError):
        streaming.provision_topics("dev")
    assert len(admin.created) == 6
    assert all(topic.num_partitions == 1 for topic in admin.created)


def test_existing_correct_topics_are_idempotent(monkeypatch):
    admin = AdminDouble(existing=True)
    monkeypatch.setattr(streaming, "AdminClient", lambda config: admin)
    assert streaming.provision_topics("dev")["partitions"] == 1


def test_only_owned_actions_and_profile_are_exposed(monkeypatch):
    registry = ProviderRegistry()
    streaming.register(registry)
    assert registry.missing("env reset") and registry.missing("db migrate")
    invocation = Invocation("env up", {"profile": "local4c8g"}, None, str(uuid4()), "dev")
    assert registry.invoke(invocation).code == ExitCode.BAD_INPUT
    monkeypatch.setattr(postgres, "check_engine", lambda: None)
    monkeypatch.setattr(postgres, "credentials", lambda: {})
    commands = []
    monkeypatch.setattr(streaming, "compose", lambda *args: commands.append(args))
    invocation = Invocation("env down", {}, None, str(uuid4()), "dev")
    assert registry.invoke(invocation).code == ExitCode.COMPLETED
    assert commands == [("down", "--timeout", "30")]


@pytest.mark.parametrize("failure", [None, "oom", "public_port", "memory", "image", "volume"])
def test_container_verification_enforces_the_declared_guarantees(monkeypatch, failure):
    state = {
        "id": "explicit-double",
        "health": "healthy",
        "oom_killed": False,
        "memory": 1024 * 1024**2,
        "cpu": 750000000,
        "image": "pinned-image",
        "ports": {"19092/tcp": [{"HostIp": "127.0.0.1", "HostPort": "9092"}]},
        "mounts": [{"Destination": "/var/lib/kafka/data", "Type": "volume", "RW": True}],
    }
    if failure == "oom":
        state["oom_killed"] = True
    elif failure == "public_port":
        state["ports"]["19092/tcp"][0]["HostIp"] = "0.0.0.0"
    elif failure == "memory":
        state["memory"] = 0
    elif failure == "image":
        state["image"] = "floating:latest"
    elif failure == "volume":
        state["mounts"][0]["Type"] = "bind"
    monkeypatch.setattr(streaming, "compose", lambda *args: "explicit-double")
    monkeypatch.setattr(postgres, "command", lambda *args: json.dumps(state))
    limits = {"memory_mib": 1024, "cpu_cores": 0.75}
    if failure:
        with pytest.raises(postgres.SetupError):
            streaming.container_facts("kafka", limits, "pinned-image")
    else:
        assert streaming.container_facts("kafka", limits, "pinned-image") == state
