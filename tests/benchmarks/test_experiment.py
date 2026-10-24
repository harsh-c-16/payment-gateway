import asyncio
import json
from dataclasses import replace

import pytest
from jsonschema import Draft202012Validator

import projectctl.artifacts as artifacts
import projectctl.config as configuration
from benchmarks.experiment import run_experiment
from benchmarks.planning import plan_matrix, plan_trials, reusable_run
from projectctl.artifacts import content_hash, file_hash
from projectctl.config import InputError, load_config, load_matrix
from projectctl.models import RunManifest, Summary
from tests.benchmarks.doubles import LifecycleDouble, SlowPublisher


@pytest.fixture
def experiment_config(tmp_path, monkeypatch):
    config = load_config()
    config.generator.key_count = 2
    config.generator.concurrency = 2
    config.generator.queue_limit = 10
    config.workloads["W-PIPE"].rate_per_second = 5.0
    monkeypatch.setattr(configuration, "ROOT", tmp_path)
    monkeypatch.setattr(artifacts, "ROOT", tmp_path)
    return config


def run(config, bindings, **kwargs):
    return asyncio.run(
        run_experiment(
            "W-PIPE",
            "B0",
            1,
            42,
            config=config,
            bindings=bindings,
            duration_seconds=1,
            warmup_seconds=0,
            evidence_kind="test",
            **kwargs,
        )
    )


def directory(config, manifest):
    return configuration.repo_path(config.artifacts.root) / manifest["run_id"]


def test_lifecycle_fresh_ids_strict_artifacts_and_frozen_manifest(experiment_config):
    double = LifecycleDouble()
    first = run(experiment_config, double.bindings())
    second = run(experiment_config, double.bindings())
    assert first["namespace"] != second["namespace"]
    folder = directory(experiment_config, first)
    summary = json.loads((folder / "summary.json").read_text())
    RunManifest.model_validate(first)
    Summary.model_validate(summary)
    Draft202012Validator(RunManifest.model_json_schema()).validate(first)
    Draft202012Validator(Summary.model_json_schema()).validate(summary)
    assert summary["exit_code"] == 0 and summary["test_mode"] == "stub"
    assert first["workload_protocol"]["duration_seconds"] == 1
    assert first["content_sha256"] == content_hash(first)
    for ref in first["artifacts"]:
        assert file_hash(folder / ref["path"]) == ref["sha256"]
    stages = [
        json.loads(line)["stage"] for line in (folder / "lifecycle.jsonl").read_text().splitlines()
    ]
    assert stages == ["prepare", "validate", "warmup", "measure", "drain", "reconcile", "persist"]
    assert json.loads((folder / "execution.json").read_text())["sut_performance"] == "NOT_RUN"
    unavailable = {
        slot["path"] for slot in first["required_artifacts"] if slot["status"] == "NOT_RUN"
    }
    assert {"timings.parquet", "resources.csv", "lag.csv"} <= unavailable


@pytest.mark.parametrize("stage", ["prepare", "validate", "drain"])
def test_provider_failures_retain_stage_and_evidence(experiment_config, stage):
    manifest = run(experiment_config, LifecycleDouble(fail_stage=stage).bindings())
    folder = directory(experiment_config, manifest)
    summary = json.loads((folder / "summary.json").read_text())
    assert summary["exit_code"] == 4 and manifest["correctness_passed"] is None
    assert any(stage in reason for reason in summary["reasons"])
    assert (folder / "planned.jsonl").is_file() and (folder / "workload_manifest.json").is_file()
    if stage == "drain":
        assert (folder / "emissions.jsonl").is_file() and (folder / "admission.json").is_file()


@pytest.mark.parametrize("verdict,exit_code", [(False, 3), (None, 4)])
def test_independent_audit_verdicts_propagate(experiment_config, verdict, exit_code):
    manifest = run(experiment_config, LifecycleDouble(audit_passed=verdict).bindings())
    summary = json.loads((directory(experiment_config, manifest) / "summary.json").read_text())
    assert summary["exit_code"] == exit_code


def test_slow_generation_does_not_claim_requested_rate_was_admitted(experiment_config):
    experiment_config.workloads["W-PIPE"].rate_per_second = 100.0
    experiment_config.generator.queue_limit = 2
    publisher = SlowPublisher(delay=0.2)
    manifest = run(experiment_config, LifecycleDouble(publisher).bindings())
    folder = directory(experiment_config, manifest)
    summary = json.loads((folder / "summary.json").read_text())
    assert summary["exit_code"] == 5
    metrics = {row["name"]: row for row in summary["metrics"]}
    assert metrics["generator_offered_rate"]["value"] == 100
    assert metrics["admitted_rate"]["value"] < 100


@pytest.mark.parametrize(
    "namespace", ["dev", "live", "bench-live", "bench-production-data", "other"]
)
def test_unsafe_namespaces_never_call_prepare(experiment_config, namespace):
    double = LifecycleDouble()
    with pytest.raises(InputError):
        run(experiment_config, double.bindings(), namespace=namespace)
    assert double.calls == []


def test_real_mode_and_missing_bindings_never_fall_back(experiment_config):
    double = LifecycleDouble()
    bindings = replace(double.bindings(), mode="real")
    manifest = run(experiment_config, bindings)
    summary = json.loads((directory(experiment_config, manifest) / "summary.json").read_text())
    assert summary["exit_code"] == 4 and summary["status"] == "NOT_RUN"
    assert "configuration is explicitly draft" in summary["reasons"]
    assert double.calls == []
    missing = run(experiment_config, None)
    assert missing["status"] == "INCOMPLETE" and missing["started_at"] is None


def test_stub_cannot_run_performance_protocol(experiment_config):
    double = LifecycleDouble()
    with pytest.raises(InputError):
        asyncio.run(
            run_experiment(
                "W-PIPE", "B0", 1, 42, config=experiment_config, bindings=double.bindings()
            )
        )
    assert double.calls == []


def test_existing_namespace_is_a_failure_and_never_reset(experiment_config):
    double = LifecycleDouble()

    async def existing(context, manifest):
        return {"namespace": context["namespace"], "created_new": False}

    bindings = replace(double.bindings(), prepare=existing)
    manifest = run(experiment_config, bindings)
    summary = json.loads((directory(experiment_config, manifest) / "summary.json").read_text())
    assert summary["exit_code"] == 4 and double.calls == []


def test_frozen_plan_tampering_is_visible(experiment_config):
    double = LifecycleDouble()

    async def tamper(context, deadline):
        path = (
            configuration.repo_path(experiment_config.artifacts.root)
            / context["run_id"]
            / "planned.jsonl"
        )
        path.write_text("")

    manifest = run(experiment_config, replace(double.bindings(), drain=tamper))
    summary = json.loads((directory(experiment_config, manifest) / "summary.json").read_text())
    assert summary["exit_code"] == 2


def test_pairing_repetitions_and_matrix_controls_are_recorded():
    config = load_config()
    trials = plan_trials(config, "W-PIPE", ["B0", "O1"], 3)
    assert len(trials) == 6
    for rep in (1, 2, 3):
        pair = [t for t in trials if t.repetition == rep]
        assert {t.variant for t in pair} == {"B0", "O1"}
        assert pair[0].order["pair_id"] == pair[1].order["pair_id"]
        assert pair[0].config.generator.seed == pair[1].config.generator.seed == 42
    assert [t.variant for t in trials] == [
        t.variant for t in plan_trials(config, "W-PIPE", ["B0", "O1"], 3)
    ]
    matrix = load_matrix("configs/core_matrix.yaml", config)
    expanded, pending = plan_matrix(config, matrix)
    assert len(pending) == 3
    assert len({t.order["trial_key"] for t in expanded}) == len(expanded)
    search = [t for t in expanded if t.workload == "W-SEARCH"]
    assert {t.config.retrieval.mode for t in search} == {"filter_only", "lexical"}
    layout = [t for t in expanded if t.variant == "F-PARTITION"]
    assert len(layout) == 6
    assert {t.order["effective_parameters"]["partitioning"] for t in layout} == {
        "unpartitioned",
        "date_type",
    }
    assert all(t.order["effective_parameters"]["file_layout"] == "compact" for t in layout)


def test_mismatched_control_pair_is_rejected():
    from benchmarks.planning import check_pair_controls

    trials = plan_trials(load_config(), "W-PIPE", ["B0", "O1"], 1)
    trials[1].config.generator.seed = 99
    with pytest.raises(InputError, match="controls"):
        check_pair_controls(*trials)


def test_incomplete_stub_or_corrupt_runs_never_reused(experiment_config):
    trials = plan_trials(experiment_config, "W-PIPE", ["B0"], 1)
    manifest = run(experiment_config, LifecycleDouble().bindings(), order=trials[0].order)
    folder = directory(experiment_config, manifest)
    assert not reusable_run(folder, trials[0])
    (folder / "summary.json").write_text("corrupt")
    assert not reusable_run(folder, trials[0])


def test_finite_import_records_owner_stage_timers_without_duration_padding(experiment_config):
    from benchmarks.drivers import ImportDriver

    async def importer(context):
        assert context["parameters"]["catalog_load_mode"] == "copy"
        assert context["dataset"]["rules_version"] == "flipkart-v1"
        return {
            "raw_to_ready_seconds": 0.025,
            "stages": {"staging": 0.01},
            "logical_digest": "test-only-digest",
            "raw_observations": 20000,
            "canonical_rows": 19998,
            "active_rows": 19920,
        }

    bindings = replace(LifecycleDouble().bindings(), driver=ImportDriver(importer))
    manifest = asyncio.run(
        run_experiment(
            "W-IMPORT",
            "I1",
            1,
            42,
            config=experiment_config,
            bindings=bindings,
            evidence_kind="test",
        )
    )
    folder = directory(experiment_config, manifest)
    assert manifest["workload_protocol"]["duration_seconds"] is None
    assert manifest["workload_protocol"]["warmup_seconds"] is None
    timings = json.loads((folder / "import_timings.json").read_text())
    assert timings["raw_to_ready_seconds"] == 0.025
    summary = json.loads((folder / "summary.json").read_text())
    assert summary["exit_code"] == 0
    assert 0 < summary["metrics"][0]["denominator"] < 2
    assert summary["metrics"][0]["cohort"] == "finite_job"


def test_analytics_runner_excludes_18_warmups_from_180_measured_calls(experiment_config):
    from benchmarks.drivers import QueryDriver

    async def query(payload, context):
        return {"query_id": payload["query_id"], "result_digest": "test-only-digest"}

    bindings = replace(
        LifecycleDouble().bindings(),
        driver=QueryDriver(query),
        templates=tuple({"query_id": f"Q{i}"} for i in range(1, 7)),
    )
    manifest = asyncio.run(
        run_experiment(
            "W-ANALYTICS",
            "B0",
            1,
            42,
            config=experiment_config,
            bindings=bindings,
            evidence_kind="test",
        )
    )
    folder = directory(experiment_config, manifest)
    summary = json.loads((folder / "summary.json").read_text())
    admission = json.loads((folder / "admission.json").read_text())
    assert summary["exit_code"] == 0
    assert admission["phases"]["warmup"]["acknowledged"] == 18
    assert admission["phases"]["measurement"]["acknowledged"] == 180
    assert summary["metrics"][0]["numerator"] == 180
    assert summary["metrics"][0]["cohort"] == "query"


def test_fault_barrier_missing_receipt_invalidates_trial(experiment_config):
    fault = experiment_config.faults["relay-publish-before-mark"]
    fault.measurement_second = 0

    async def unacknowledged(context, name, definition):
        return {"acknowledged": False, "target": definition["target"]}

    bindings = replace(LifecycleDouble().bindings(), fault=unacknowledged)
    manifest = run(experiment_config, bindings, fault_profile="relay-publish-before-mark")
    folder = directory(experiment_config, manifest)
    assert json.loads((folder / "summary.json").read_text())["exit_code"] == 4
    assert json.loads((folder / "faults.jsonl").read_text())["acknowledged"] is False
    assert manifest["correctness_passed"] is None


def test_run_id_cannot_escape_evidence_directory(experiment_config):
    double = LifecycleDouble()
    with pytest.raises(InputError):
        run(experiment_config, double.bindings(), run_id="../dev")
    assert double.calls == []


def test_reuse_requires_every_hash_and_clean_matching_code(experiment_config, monkeypatch):
    """Construct a labelled artifact double; no real performance run occurs."""
    import benchmarks.planning as planning
    import projectctl.cli as cli
    from projectctl.models import GitState

    experiment_config.timing.duration_seconds = 1
    experiment_config.timing.warmup_seconds = 0
    experiment_config.timing.repetitions = 1
    trial = plan_trials(experiment_config, "W-PIPE", ["B0"], 1)[0]
    manifest = run(experiment_config, LifecycleDouble().bindings(), order=trial.order)
    folder = directory(experiment_config, manifest)
    summary = json.loads((folder / "summary.json").read_text())
    execution = json.loads((folder / "execution.json").read_text())
    summary["test_mode"] = "real"
    execution |= {
        "test_mode": "real",
        "sut_performance": "MEASURED",
        "evidence_kind": "performance",
        "fixture_only": True,
    }
    for name, value in (("summary.json", summary), ("execution.json", execution)):
        (folder / name).write_text(json.dumps(value))
    state = GitState(commit="a" * 40, dirty=False)
    manifest["git"] = state.model_dump()
    for ref in manifest["artifacts"]:
        ref["sha256"] = file_hash(folder / ref["path"])
    manifest["content_sha256"] = content_hash(manifest)
    (folder / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(cli, "preflight", lambda *args: [])
    monkeypatch.setattr(planning, "git_state", lambda: state)
    assert reusable_run(folder, trial)
    monkeypatch.setattr(planning, "git_state", lambda: GitState(commit="b" * 40, dirty=False))
    assert not reusable_run(folder, trial)
    monkeypatch.setattr(planning, "git_state", lambda: state)
    (folder / "emissions.jsonl").write_text("corrupt")
    assert not reusable_run(folder, trial)
