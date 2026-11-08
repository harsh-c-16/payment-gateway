"""Offline checkpoint regression tests collected by the regular benchmark CI suite."""

import json
import subprocess

import pytest

import benchmarks.manual.verify_prompt7 as checkpoint
import projectctl.artifacts as artifacts
import projectctl.config as configuration
from projectctl.config import load_config
from projectctl.models import GitState
from projectctl.providers import ProviderRegistry


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    config = load_config()
    monkeypatch.setattr(configuration, "ROOT", tmp_path)
    monkeypatch.setattr(artifacts, "ROOT", tmp_path)
    monkeypatch.setattr(checkpoint, "git_state", lambda: GitState(commit="a" * 40, dirty=True))
    return config, tmp_path


def test_missing_gates_remain_null_and_never_invoke_registered_code(workspace):
    config, _ = workspace
    registry = ProviderRegistry()

    def forbidden(*args):
        pytest.fail("prerequisite inventory invoked an owner adapter/factory")

    registry.register("env reset", forbidden)
    registry.register_workload_factory("W-SEARCH", forbidden)
    before = config.model_dump()
    result = checkpoint.assess(config, registry, reuse_connections="false")
    assert result["exit_code"] == 4
    assert result["status"] == "INCOMPLETE"
    assert result["real_writes_attempted"] is False
    assert result["correctness_passed"] is None
    assert result["B0"] == {"status": "NOT_RUN", "metrics": None, "frozen_inputs": None}
    assert result["C-BEST"]["selection"] is None
    assert result["performance"] == result["setup"] == result["smoke"] == "NOT_RUN"
    assert config.model_dump() == before
    checks = {item["name"]: item for item in result["checks"]}
    assert checks["code_revision"]["status"] == "NOT_RUN"
    assert "unavailable" in " ".join(checks["owner_bindings"]["reasons"])
    assert checks["B0_smoke_evidence"]["status"] == "NOT_RUN"


@pytest.mark.parametrize("reuse", ["true", "1", "yes", ""])
def test_session_reuse_and_short_repetitions_cannot_enter_frozen_matrix(workspace, reuse):
    config, _ = workspace
    config.timing.repetitions = 1
    result = checkpoint.assess(config, ProviderRegistry(), reuse_connections=reuse)
    control = next(c for c in result["checks"] if c["name"] == "frozen_controls")
    assert len(control["reasons"]) == 2
    assert control["session_reuse_disabled"] is False


def test_rule_label_hash_is_not_a_human_review_or_a_config_edit(workspace):
    config, _ = workspace
    config.retrieval.label_sha256 = "b" * 64
    result = checkpoint.assess(config, ProviderRegistry(), reuse_connections="false")
    label = next(c for c in result["checks"] if c["name"] == "human_relevance_labels")
    assert label["status"] == "NOT_RUN"
    assert label["certified_metrics"] is None
    assert label["configured_sha256"] == config.retrieval.label_sha256 == "b" * 64


def test_changed_application_lock_is_bad_input_with_retained_reason(workspace):
    config, root = workspace
    (root / "uv.lock").write_text("explicit wrong-lock fixture", encoding="utf-8")
    result = checkpoint.assess(config, ProviderRegistry(), reuse_connections="false")
    assert result["exit_code"] == 2
    assert any(
        "application lock SHA-256 differs" in reason
        for check in result["checks"]
        for reason in check["reasons"]
    )


def test_discovered_locks_are_observed_without_pinning_config(workspace):
    config, root = workspace
    path = root / "infra/images.lock.json"
    path.parent.mkdir()
    path.write_bytes(b'{"explicit_double":true}\r\n')
    before = config.model_dump()
    facts = checkpoint.local_files(config)
    assert facts["owner_infrastructure_lock"]["present"] is True
    assert facts["owner_infrastructure_lock"]["raw_sha256"] == artifacts.file_hash(path)
    assert facts["infrastructure_lock"] == {"path": None, "present": False, "raw_sha256": None}
    assert config.model_dump() == before


@pytest.mark.parametrize("outcome", [0, 1, "timeout", "missing"])
def test_environment_probe_retains_failure_logs(workspace, monkeypatch, outcome):
    _, root = workspace

    def run(argv, **kwargs):
        assert argv == ["uv", "sync", "--locked", "--check"]
        assert kwargs["timeout"] == 30
        if outcome == "timeout":
            raise subprocess.TimeoutExpired(argv, 30, output=b"partial", stderr=b"timeout")
        if outcome == "missing":
            raise FileNotFoundError()
        return subprocess.CompletedProcess(argv, outcome, b"stdout", b"stderr")

    monkeypatch.setattr(checkpoint.subprocess, "run", run)
    result = checkpoint.probe_lock(root)
    assert result["status"] == ("VERIFIED" if outcome == 0 else "NOT_RUN")
    assert (root / "lock.stdout.log").is_file()
    assert (root / "lock.stderr.log").is_file()
    if outcome == "timeout":
        assert (root / "lock.stdout.log").read_bytes() == b"partial"


def test_bad_config_still_writes_evidence_and_cannot_overwrite_it(workspace, monkeypatch):
    _, root = workspace
    (root / "bad.yaml").write_text("state: invented\n", encoding="utf-8")
    monkeypatch.setattr(checkpoint, "probe_lock", lambda _: {"status": "VERIFIED", "exit_code": 0})
    argv = ["--config", "bad.yaml", "--out", "evidence"]
    assert checkpoint.main(argv) == 2
    path = root / "evidence/readiness.json"
    original = path.read_bytes()
    assert json.loads(original)["performance"] == "NOT_RUN"
    with pytest.raises(FileExistsError):
        checkpoint.main(argv)
    assert path.read_bytes() == original
