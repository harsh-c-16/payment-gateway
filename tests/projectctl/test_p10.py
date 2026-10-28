"""P10 evidence fixtures/explicit boundary doubles; never real SUT measurements."""

import copy
import json
from uuid import uuid4

import pytest
from jsonschema import Draft202012Validator

import benchmarks.reporting as reporting
from benchmarks.comparison import compare_metrics
from benchmarks.planning import plan_trials
from projectctl.artifacts import content_hash, file_hash, save_evidence, write_json
from projectctl.cli import main
from projectctl.config import load_config
from projectctl.models import ExitCode
from projectctl.providers import DependencyError, Invocation, ProviderResult
from projectctl.report_models import FinalReport


@pytest.fixture
def bundle(workspace):
    config = load_config()
    trials = plan_trials(config, "W-PIPE", ["B0", "O1"], 3)
    records = []
    for trial in trials:
        invocation = Invocation(
            "benchmark run", {}, trial.config, str(uuid4()), "bench-" + uuid4().hex
        )
        result = save_evidence(
            invocation,
            ProviderResult(
                ExitCode.DEPENDENCY_FAILURE, ("explicit unavailable-provider fixture",), "offline"
            ),
            workload=trial.workload,
            variant=trial.variant,
            repetition=trial.repetition,
            order=trial.order,
        )
        records.append({key: result[key] for key in ("run_id", "evidence_dir", "exit_code")})
    directory = workspace / "artifacts/input"
    directory.mkdir(parents=True)
    write_json(
        directory / "plan.json",
        {"schema_version": 1, "order_seed": 42, "trials": [t.order for t in trials], "pending": []},
    )
    write_json(directory / "results.json", {"plan": "plan.json", "runs": records, "pending": []})
    return workspace, records


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def replace(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def test_blocked_report_preserves_all_repetitions_and_tables_without_invented_values(bundle):
    root, records = bundle
    report = reporting.build_report("artifacts/input/results.json")
    assert report["status"] == "INCOMPLETE" and not report["required_core_complete"]
    assert len(report["runs"]) == len(records) == 6
    assert all(not r["metrics"] and r["status"] == "NOT_RUN" for r in report["runs"])
    assert len(report["tables"]) == 11 and sum(t["required"] for t in report["tables"]) == 9
    assert report["content_sha256"] == content_hash(report)
    Draft202012Validator(FinalReport.model_json_schema()).validate(report)
    assert reporting.build_report("artifacts/input/results.json") == report
    assert all(file_hash(root / ref["path"]) == ref["sha256"] for ref in report["evidence_index"])


@pytest.mark.parametrize("mutation", ["missing", "changed", "traversal", "duplicate"])
def test_missing_corrupt_escaping_or_duplicate_evidence_rejected(bundle, mutation):
    root, records = bundle
    directory = root / records[0]["evidence_dir"]
    if mutation == "missing":
        (directory / "summary.json").unlink()
    elif mutation == "changed":
        (directory / "summary.json").write_text("corrupt")
    else:
        manifest = read(directory / "manifest.json")
        if mutation == "traversal":
            manifest["artifacts"][0]["path"] = "../../uv.lock"
        else:
            manifest["artifacts"].append(copy.deepcopy(manifest["artifacts"][0]))
        manifest["content_sha256"] = content_hash(manifest)
        replace(directory / "manifest.json", manifest)
    with pytest.raises((DependencyError, OSError, ValueError)):
        reporting.build_report("artifacts/input/results.json")


@pytest.mark.parametrize("mutation", ["drop", "duplicate", "identity", "plan", "unknown"])
def test_selective_best_run_and_manifest_mismatches_never_complete(bundle, mutation):
    root, records = bundle
    path = root / "artifacts/input/results.json"
    value = read(path)
    if mutation == "drop":
        value["runs"].pop()
    elif mutation == "duplicate":
        value["runs"].append(records[0])
    elif mutation == "identity":
        value["runs"][0]["run_id"] = str(uuid4())
    elif mutation == "plan":
        value["plan"] = "../outside.json"
    else:
        value["winner"] = "O1"
    replace(path, value)
    if mutation == "drop":
        report = reporting.build_report("artifacts/input/results.json")
        assert not report["required_core_complete"]
        assert "matrix is missing planned trial evidence" in report["not_run"]
    else:
        with pytest.raises((DependencyError, ValueError)):
            reporting.build_report("artifacts/input/results.json")


def test_cli_retains_refusal_and_does_not_overwrite_existing_report(bundle, capsys):
    root, records = bundle
    args = [
        "report",
        "build",
        "--matrix-results",
        "artifacts/input/results.json",
        "--out",
        "artifacts/report",
    ]
    assert main(args) == 4
    output = json.loads(capsys.readouterr().out)
    assert (root / output["evidence_dir"] / "manifest.json").is_file()
    original = (root / "artifacts/report/report.json").read_bytes()
    assert main(args) == 4
    capsys.readouterr()
    assert (root / "artifacts/report/report.json").read_bytes() == original
    (root / records[0]["evidence_dir"] / "summary.json").unlink()
    assert main(args[:-1] + ["artifacts/refused"]) == 4
    capsys.readouterr()
    assert read(root / "artifacts/refused/report.json")["runs"] == []


def test_real_report_rejects_explicit_stub_even_with_no_metrics(bundle):
    root, records = bundle
    directory = root / records[0]["evidence_dir"]
    path = directory / "summary.json"
    value = read(path)
    value["test_mode"] = "stub"
    replace(path, value)
    manifest = read(directory / "manifest.json")
    next(r for r in manifest["artifacts"] if r["path"] == "summary.json")["sha256"] = file_hash(
        path
    )
    manifest["content_sha256"] = content_hash(manifest)
    replace(directory / "manifest.json", manifest)
    with pytest.raises(DependencyError, match="test-double"):
        reporting.build_report("artifacts/input/results.json")


def test_directions_negative_costs_zero_baseline_and_all_samples_are_visible():
    def metric(name, value):
        return {
            "name": name,
            "value": value,
            "unit": "seconds",
            "status": "MEASURED",
            "sample_count": 5,
            "timing_validity": "VALID",
            "cohort": "measurement",
            "quantile_method": "nearest-rank",
            "unresolved_count": 0,
        }

    a = [
        {
            "metrics": [
                metric("analytics.producer_to_gold.p99_seconds", n),
                metric("sut.process_resident_memory_bytes.abc.peak", 10),
                metric("mean_cpu_percent", 0),
            ]
        }
        for n in (10, 20, 30)
    ]
    b = [
        {
            "metrics": [
                metric("analytics.producer_to_gold.p99_seconds", n),
                metric("sut.process_resident_memory_bytes.abc.peak", 20),
                metric("mean_cpu_percent", 4),
            ]
        }
        for n in (5, 10, 15)
    ]
    rows = {m["name"]: m for m in compare_metrics(a, b)}
    assert rows["analytics.producer_to_gold.p99_seconds"]["improvement_percent"] == 50
    assert rows["sut.process_resident_memory_bytes.abc.peak"]["improvement_percent"] == -100
    assert rows["mean_cpu_percent"]["improvement_percent"] is None
    assert rows["mean_cpu_percent"]["absolute_change"] == 4
    assert rows["mean_cpu_percent"]["sample_counts"] == [5] * 6


@pytest.mark.parametrize("workload", ["W-IMPORT", "W-SEARCH", "W-ANALYTICS"])
def test_saved_nonstream_reconciliation_uses_workload_loader_double(bundle, monkeypatch, workload):
    import benchmarks.saved_reconciliation as recheck

    root, records = bundle
    directory = root / records[0]["evidence_dir"]
    write_json(directory / "execution.json", {"test_mode": "real"})
    # Explicit loader double isolates dispatch; does not prove a real audit passed.
    calls = []

    def loader(path):
        calls.append(path)
        return {"manifest": {"workload_id": workload}}

    monkeypatch.setattr(recheck, "load_performance_run", loader)
    invocation = Invocation(
        "benchmark reconcile",
        {"run_dir": records[0]["evidence_dir"]},
        None,
        str(uuid4()),
        "bench-" + uuid4().hex,
    )
    result = recheck.execute_reconciliation(invocation)
    assert result["exit_code"] == 0 and calls == [directory]
    assert read(root / result["evidence_dir"] / "correctness.json")["workload"] == workload


def test_missing_reconciliation_evidence_returns_dependency_failure(bundle):
    root, records = bundle
    assert main(["benchmark", "reconcile", "--run-dir", records[0]["evidence_dir"]]) == 4


def test_report_presentations_retain_raw_trace_and_repeated_spread_with_explicit_loader_double(
    bundle, monkeypatch
):
    """Only report assembly is under test; these fixtures are not real performance evidence."""
    import benchmarks.comparison as comparison
    import benchmarks.observation_summary as telemetry

    root, records = bundle
    doubles = {}
    for record in records:
        directory = root / record["evidence_dir"]
        manifest = read(directory / "manifest.json")
        repetition = manifest["repetition"]
        value = repetition * (100 if manifest["variant_id"] == "B0" else 80)
        write_json(directory / "raw.json", {"observations_ms": [value]})
        for name in ("performance_review.json", "binding_review.json"):
            write_json(directory / name, {})
        summary = read(directory / "summary.json")
        summary.update(
            exit_code=0,
            test_mode="real",
            status="MEASURED",
            metrics=[
                {
                    "name": "producer_to_gold_p95_ms",
                    "unit": "milliseconds",
                    "value": value,
                    "sample_count": 1,
                    "numerator": None,
                    "denominator": None,
                    "cohort": "measurement",
                    "quantile_method": "nearest-rank",
                    "unresolved_count": 0,
                    "timing_validity": "VALID",
                    "run_id": manifest["run_id"],
                    "config_sha256": manifest["config_sha256"],
                    "status": "MEASURED",
                    "evidence_path": "raw.json",
                }
            ],
        )
        replace(directory / "summary.json", summary)
        manifest.update(
            status="MEASURED",
            correctness_passed=True,
            started_at="2026-10-28T00:00:00Z",
            git={"commit": "a" * 40, "dirty": False},
        )
        for ref in manifest["artifacts"]:
            ref["sha256"] = file_hash(directory / ref["path"])
        manifest["artifacts"] += [
            {"path": name, "sha256": file_hash(directory / name)}
            for name in ("raw.json", "performance_review.json", "binding_review.json")
        ]
        manifest["content_sha256"] = content_hash(manifest)
        replace(directory / "manifest.json", manifest)
        record["exit_code"] = 0
        from projectctl.models import EvaluationConfig

        doubles[directory] = {
            "directory": directory,
            "manifest": manifest,
            "summary": summary,
            "config": EvaluationConfig.model_validate(manifest["resolved_config"]),
            "order": read(directory / "execution_order.json"),
        }
    result_path = root / "artifacts/input/results.json"
    result = read(result_path)
    result["runs"] = records
    replace(result_path, result)
    monkeypatch.setattr(reporting, "load_performance_run", lambda path: doubles[path])
    monkeypatch.setattr(comparison, "load_performance_run", lambda path: doubles[path])
    monkeypatch.setattr(
        telemetry, "rebuild", lambda _: {"series": [], "rates": {}, "latencies": []}
    )
    report = reporting.build_report("artifacts/input/results.json")
    metric = report["comparisons"][0]["metrics"][0]
    assert metric["baseline"]["values"] == [100, 200, 300]
    assert metric["candidate"]["values"] == [80, 160, 240]
    assert metric["improvement_percent"] == 20
    assert not report["required_core_complete"]  # Required matrix, correctness/rehearsal absent.
    run = report["runs"][0]
    metric = run["metrics"][0]
    raw = root / run["evidence_dir"] / metric["evidence_path"]
    assert metric["value"] == read(raw)["observations_ms"][0]
    assert any(ref["path"] == raw.relative_to(root).as_posix() for ref in report["evidence_index"])
    assert "nearest-rank" in reporting.markdown(report)


def test_rehearsal_commands_use_one_fresh_namespace_and_no_reset():
    from benchmarks.manual.verify_p10 import setup_commands

    commands = setup_commands("bench-p10-explicit-test")
    assert commands[0][:2] == ["env", "up"]
    assert commands[-1][commands[-1].index("--suite") + 1] == "contracts,data,smoke"
    assert not any("reset" in command or "bench-smoke" in command for command in commands)
    for command in commands:
        if "--namespace" in command:
            assert command[command.index("--namespace") + 1] == "bench-p10-explicit-test"
