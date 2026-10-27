"""P9 eligibility tests use explicit evidence doubles, never real integration claims."""

import asyncio
import copy
import json
from dataclasses import replace

import pytest

import benchmarks.performance as performance
import projectctl.artifacts as artifacts
import projectctl.config as configuration
from benchmarks.experiment import run_experiment
from benchmarks.performance import (
    controls_hash,
    load_performance_run,
    review_blockers,
    validate_outputs,
    verified_bundle,
)
from projectctl.artifacts import content_hash, file_hash, save_evidence, write_json
from projectctl.config import InputError, load_config
from projectctl.models import ExitCode, GitState
from projectctl.providers import DependencyError, Invocation, ProviderResult
from tests.benchmarks.doubles import LifecycleDouble


@pytest.fixture
def evidence_workspace(tmp_path, monkeypatch):
    config = load_config()
    monkeypatch.setattr(configuration, "ROOT", tmp_path)
    monkeypatch.setattr(artifacts, "ROOT", tmp_path)
    return config, tmp_path


def test_clean_commit_and_review_required_even_with_a_registered_real_driver(
    evidence_workspace, monkeypatch
):
    config, root = evidence_workspace
    import projectctl.cli as cli

    monkeypatch.setattr(cli, "preflight", lambda *args: [])
    monkeypatch.setattr(performance, "git_state", lambda: GitState(commit="a" * 40, dirty=True))
    double = LifecycleDouble()
    manifest = asyncio.run(
        run_experiment(
            "W-PIPE", "B0", 1, 42, config=config, bindings=replace(double.bindings(), mode="real")
        )
    )
    summary = json.loads(
        (root / config.artifacts.root / manifest["run_id"] / "summary.json").read_text()
    )
    assert double.calls == []
    assert summary["exit_code"] == 4 and summary["status"] == "NOT_RUN"
    assert any("clean committed" in r for r in summary["reasons"])
    assert any("receipt unavailable" in r for r in summary["reasons"])
    assert all(m["value"] is None for m in summary["metrics"])


def test_controls_bind_inputs_resources_but_allow_registered_series():
    config = load_config()
    other = config.model_copy(deep=True)
    other.retrieval.mode = "filter_only"
    other.generator.key_distribution = "hot80"
    other.generator.rate_per_second = 2000.0
    assert controls_hash(config) == controls_hash(other)
    other.generator.payment_delay_ms += 1
    assert controls_hash(config) != controls_hash(other)


def minimal_review(config, root):
    """Receipt double for validation branches. It never describes an executed environment."""
    resource = {
        "test_mode": "real",
        "enforced": True,
        "git_commit": "a" * 40,
        "profile": config.profile.model_dump(),
        "image_digests": ["fixture@sha256:" + "b" * 64],
        "host": {
            "cpu_model": "fixture",
            "physical_cores": 4,
            "total_memory_bytes": 10,
            "os": "fixture",
            "storage": "fixture",
        },
    }
    write_json(root / "resource.json", resource)
    review = {
        "schema_version": 1,
        "reviewers": sorted(performance.REVIEWERS),
        "git_commit": "a" * 40,
        "controls_sha256": controls_hash(config),
        "resource_receipt": {"path": "resource.json", "sha256": file_hash(root / "resource.json")},
        "correctness_runs": [],
        "inputs": [],
        "smoke_run": None,
        "baseline_run": None,
        "diagnosis": None,
        "hypotheses": [],
    }
    review["content_sha256"] = content_hash(review)
    write_json(root / "review.json", review)
    return review


@pytest.mark.parametrize(
    "mutation,expected",
    [
        ("identity", "identity/controls"),
        ("resources", "actual enforced"),
        ("inputs", "input hashes"),
        ("hash", "identity/controls"),
    ],
)
def test_review_rejects_wrong_identity_resource_or_incomplete_inputs(
    evidence_workspace, monkeypatch, mutation, expected
):
    config, root = evidence_workspace
    monkeypatch.setattr(performance, "git_state", lambda: GitState(commit="a" * 40, dirty=False))
    review = minimal_review(config, root)
    if mutation == "identity":
        review["git_commit"] = "c" * 40
    if mutation == "resources":
        resource = json.loads((root / "resource.json").read_text())
        resource["test_mode"] = "stub"
        (root / "resource.json").write_text(json.dumps(resource))
        review["resource_receipt"]["sha256"] = file_hash(root / "resource.json")
    review["content_sha256"] = content_hash(review)
    if mutation == "hash":
        review["content_sha256"] = "0" * 64
    (root / "review.json").write_text(json.dumps(review))
    assert expected in " ".join(review_blockers(config, "review.json"))


def test_json_duplicate_keys_and_nonfinite_values_rejected(tmp_path):
    path = tmp_path / "bad.json"
    for source in ('{"a":1,"a":2}', '{"a":NaN}'):
        path.write_text(source)
        with pytest.raises(ValueError):
            performance.read_json(path)


def test_bundle_hashes_paths_and_required_index_are_checked(evidence_workspace):
    config, root = evidence_workspace
    invocation = Invocation(
        "benchmark run", {}, config, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "bench-fixture"
    )
    output = save_evidence(
        invocation, ProviderResult(ExitCode.DEPENDENCY_FAILURE, ("fixture",), "stub")
    )
    directory = root / output["evidence_dir"]
    assert verified_bundle(directory, {"summary.json"})["run_id"] == invocation.run_id
    with pytest.raises(DependencyError, match="not indexed"):
        verified_bundle(directory, {"timings.parquet"})
    with pytest.raises(DependencyError):
        load_performance_run(directory)
    (directory / "summary.json").write_text("corrupted fixture")
    with pytest.raises(DependencyError, match="changed"):
        verified_bundle(directory)


def test_missing_outputs_never_promote_a_provider_pass_flag(tmp_path):
    result = validate_outputs(tmp_path, {"workload_id": "W-PIPE", "namespace": "bench-fixture"})
    assert result["passed"] is False
    assert "missing raw evidence: lag.csv" in result["reasons"]
    assert any("audit/telemetry" in r for r in result["reasons"])


def test_evidence_ref_cannot_escape_workspace(evidence_workspace):
    with pytest.raises(InputError):
        performance.checked_ref({"path": "../outside", "sha256": "a" * 64})


def test_fixture_only_manifest_never_becomes_a_performance_run(evidence_workspace, monkeypatch):
    config, root = evidence_workspace
    # Explicit loader-boundary double tests the promotion check, not a real run.
    from projectctl.models import RunManifest

    output = save_evidence(
        Invocation(
            "benchmark run", {}, config, "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "bench-fixture"
        ),
        ProviderResult(ExitCode.COMPLETED, (), "stub"),
    )
    directory = root / output["evidence_dir"]
    manifest = json.loads((directory / "manifest.json").read_text())
    RunManifest.model_validate(manifest)
    monkeypatch.setattr(performance, "verified_bundle", lambda *args: copy.deepcopy(manifest))
    write_json(directory / "execution_order.json", {})
    write_json(directory / "execution.json", {"fixture_only": True, "test_mode": "stub"})
    write_json(directory / "performance_validation.json", {"passed": True})
    with pytest.raises(DependencyError, match="real clean-revision"):
        load_performance_run(directory)
