import json
from uuid import UUID

import pytest

from projectctl.cli import main, parser
from projectctl.models import ExitCode
from projectctl.providers import OWNERS, Invocation, ProviderRegistry, ProviderResult


class ExplicitAdapterDouble:
    """Adapter result transport only. Does not pretend to start a real environment."""

    def __init__(self, code):
        self.code = code
        self.calls = []

    def __call__(self, invocation: Invocation):
        self.calls.append(invocation)
        return ProviderResult(self.code, ("explicit adapter double",), "stub")


@pytest.mark.parametrize("command", [[], *[action.split() for action in OWNERS]])
def test_every_command_has_help(command, capsys):
    with pytest.raises(SystemExit) as exc:
        parser().parse_args([*command, "--help"])
    assert exc.value.code == 0
    assert "usage:" in capsys.readouterr().out


@pytest.mark.parametrize(
    "arguments",
    [
        [],
        ["unknown"],
        ["env", "verify", "--profile", "local4c8g", "--unknown"],
        ["env", "verify", "--prof", "local4c8g"],
        [
            "catalog",
            "import",
            "--source",
            "data/raw/input.csv",
            "--rules",
            "flipkart-v1",
            "--load-mode",
            "bulk",
            "--namespace",
            "bench-test",
            "--out",
            "artifacts/import",
        ],
        [
            "benchmark",
            "run",
            "--workload",
            "W-PIPE",
            "--variants",
            "B0,B0",
            "--config",
            "configs/evaluation.yaml",
        ],
        [
            "benchmark",
            "run",
            "--workload",
            "W-PIPE",
            "--variants",
            "C-BEST",
            "--config",
            "configs/evaluation.yaml",
        ],
        [
            "benchmark",
            "run",
            "--workload",
            "W-PIPE",
            "--variants",
            "B0",
            "--repetitions",
            "0",
            "--config",
            "configs/evaluation.yaml",
        ],
        ["eval", "run", "--suite", "T-99", "--config", "configs/evaluation.yaml"],
        ["env", "reset", "--namespace", "dev"],
        ["env", "reset", "--namespace", "live"],
        ["env", "reset", "--namespace", "bench-live"],
        ["env", "reset", "--namespace", "bench-prod-orders"],
        ["env", "reset", "--namespace", "bench-../live"],
        ["report", "build", "--matrix-results", "../outside.json", "--out", "artifacts/report"],
    ],
)
def test_bad_input_saves_evidence_and_never_calls_provider(arguments, workspace, capsys):
    registry = ProviderRegistry()
    double = ExplicitAdapterDouble(ExitCode.COMPLETED)
    registry.register("env reset", double)
    assert main(arguments, registry=registry) == 2
    output = json.loads(capsys.readouterr().out)
    assert output["exit_code"] == 2
    assert double.calls == []
    assert (workspace / output["evidence_dir"] / "manifest.json").is_file()


def test_missing_environment_adapter_is_dependency_failure(workspace, capsys):
    assert main(["env", "verify", "--profile", "local4c8g"]) == 4
    output = json.loads(capsys.readouterr().out)
    assert output["test_mode"] == "offline"
    assert "Vichitr" in output["reasons"][0]
    for metric in output["metrics"]:
        assert metric["value"] is None and metric["status"] == "NOT_RUN"
    manifest = json.loads((workspace / output["evidence_dir"] / "manifest.json").read_text())
    assert manifest["correctness_passed"] is None
    assert manifest["locks"]["image_digests"] is None
    assert manifest["host"]["resources_verified"] is False


def test_env_down_has_the_documented_bare_command_surface(workspace, capsys):
    assert main(["env", "down"]) == 4
    assert json.loads(capsys.readouterr().out)["test_mode"] == "offline"


def test_evidence_storage_failure_returns_dependency_exit_even_for_bad_input(
    workspace, monkeypatch, capsys
):
    import projectctl.cli as cli

    def unavailable(*args, **kwargs):
        raise OSError("test-only evidence store unavailable")

    monkeypatch.setattr(cli, "save_evidence", unavailable)
    assert main(["unknown"]) == 4
    assert json.loads(capsys.readouterr().out)["status"] == "INCOMPLETE"


@pytest.mark.parametrize("code", list(ExitCode))
def test_explicit_adapter_results_propagate_all_exit_codes(code, workspace, capsys):
    registry = ProviderRegistry()
    double = ExplicitAdapterDouble(code)
    registry.register("env verify", double)
    assert main(["env", "verify", "--profile", "local4c8g"], registry=registry) == code
    output = json.loads(capsys.readouterr().out)
    assert output["test_mode"] == "stub"
    UUID(double.calls[0].run_id)
    assert output["namespace"] == double.calls[0].namespace
    assert double.calls[0].arguments["profile"] == "local4c8g"
    assert output["status"] == "NOT_RUN"  # Passing double is not a measurement.


def test_benchmark_draft_prepares_unique_resolved_manifests_and_blocks_adapter(workspace, capsys):
    registry = ProviderRegistry()
    double = ExplicitAdapterDouble(ExitCode.COMPLETED)
    registry.register("benchmark run", double)
    assert (
        main(
            [
                "benchmark",
                "run",
                "--workload",
                "W-PIPE",
                "--variants",
                "B0,O1",
                "--repetitions",
                "3",
                "--config",
                "configs/evaluation.yaml",
            ],
            registry=registry,
        )
        == 4
    )
    output = json.loads(capsys.readouterr().out)
    assert len(output["runs"]) == 6
    assert len({run["run_id"] for run in output["runs"]}) == 6
    assert len({run["namespace"] for run in output["runs"]}) == 6
    assert double.calls == []
    seen = set()
    for run in output["runs"]:
        directory = workspace / run["evidence_dir"]
        manifest = json.loads((directory / "manifest.json").read_text())
        resolved = json.loads((directory / "resolved_config.json").read_text())
        assert manifest["resolved_config"] == resolved
        assert manifest["config_sha256"] is not None
        assert manifest["started_at"] is None
        assert manifest["workload_protocol"]["duration_seconds"] == 600
        assert manifest["required_artifacts"][0]["status"] == "NOT_RUN"
        assert "configuration is explicitly draft" in run["reasons"]
        seen.add((manifest["variant_id"], manifest["repetition"]))
    assert seen == {(variant, rep) for variant in ["B0", "O1"] for rep in [1, 2, 3]}


def test_invalid_workload_variant_combination_fails_before_preparing_runs(workspace, capsys):
    assert (
        main(
            [
                "benchmark",
                "run",
                "--workload",
                "W-SEARCH",
                "--variants",
                "I1",
                "--config",
                "configs/evaluation.yaml",
            ]
        )
        == 2
    )
    assert not (workspace / "benchmarks" / "results").exists()


def test_suites_do_not_silently_pass_without_registered_cases(workspace, capsys):
    assert (
        main(
            [
                "eval",
                "run",
                "--suite",
                "contracts,data,smoke",
                "--config",
                "configs/evaluation.yaml",
            ]
        )
        == 4
    )
    assert "adapter unavailable: eval run" in " ".join(
        json.loads(capsys.readouterr().out)["reasons"]
    )


def test_fault_names_are_registered_not_arbitrary_commands(workspace, capsys):
    assert (
        main(
            [
                "benchmark",
                "run",
                "--workload",
                "W-CHECKOUT",
                "--variants",
                "B0",
                "--faults",
                "arbitrary-shell-command",
                "--config",
                "configs/evaluation.yaml",
            ]
        )
        == 2
    )


def test_reset_is_separate_from_read_only_report(workspace, capsys):
    registry = ProviderRegistry()
    double = ExplicitAdapterDouble(ExitCode.COMPLETED)
    registry.register("env reset", double)
    assert (
        main(
            [
                "report",
                "build",
                "--matrix-results",
                "artifacts/missing.json",
                "--out",
                "artifacts/report",
            ],
            registry=registry,
        )
        == 4
    )
    assert double.calls == []


def test_registry_rejects_duplicate_and_unknown_registrations():
    registry = ProviderRegistry()
    registry.register("env up", ExplicitAdapterDouble(ExitCode.COMPLETED))
    with pytest.raises(ValueError):
        registry.register("env up", ExplicitAdapterDouble(ExitCode.COMPLETED))
    with pytest.raises(ValueError):
        registry.register("teammate internals", ExplicitAdapterDouble(ExitCode.COMPLETED))
