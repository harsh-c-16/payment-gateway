import json

import pytest

from projectctl.cli import main


def test_compare_missing_evidence_is_visible_dependency_failure(workspace, capsys):
    assert (
        main(
            [
                "benchmark",
                "compare",
                "--baseline",
                "one,two,three",
                "--candidate",
                "four,five,six",
                "--out",
                "artifacts/comparison",
            ]
        )
        == 4
    )
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "NOT_RUN" and output["exit_code"] == 4
    assert not (workspace / "artifacts/comparison/comparison.json").exists()


def test_compare_one_best_run_is_bad_input(workspace, capsys):
    assert (
        main(
            [
                "benchmark",
                "compare",
                "--baseline",
                "one",
                "--candidate",
                "two",
                "--out",
                "artifacts/comparison",
            ]
        )
        == 2
    )
    output = json.loads(capsys.readouterr().out)
    assert "all three" in " ".join(output["reasons"])


@pytest.mark.parametrize("variants,faults", [("B0,O1", "none"), ("B0", "consumer-pause")])
def test_smoke_cannot_carry_candidate_or_fault_performance_labels(
    workspace, capsys, variants, faults
):
    assert (
        main(
            [
                "benchmark",
                "run",
                "--workload",
                "W-PIPE",
                "--variants",
                variants,
                "--faults",
                faults,
                "--smoke",
                "--config",
                "configs/evaluation.yaml",
            ]
        )
        == 2
    )
    assert json.loads(capsys.readouterr().out)["exit_code"] == 2
