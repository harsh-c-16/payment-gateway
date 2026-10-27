"""C-BEST review tests use explicit comparison and artifact doubles."""

import json

import pytest

import benchmarks.selection as selection
import projectctl.config as configuration
from benchmarks.selection import load_selection
from projectctl.artifacts import content_hash, file_hash, write_json
from projectctl.config import load_config
from projectctl.providers import DependencyError


@pytest.fixture
def selection_double(tmp_path, monkeypatch):
    config = load_config()
    monkeypatch.setattr(configuration, "ROOT", tmp_path)
    reports = {}
    for workload, candidate in (("W-PIPE", "O1"), ("W-SEARCH", "O2"), ("W-INTEGRATED", "O3")):
        refs = []
        for n in range(6):
            path = tmp_path / f"{candidate}-{n}" / "manifest.json"
            path.parent.mkdir()
            write_json(path, {"explicit_artifact_double": True})
            refs.append({"path": path.relative_to(tmp_path).as_posix(), "sha256": file_hash(path)})
        report = {
            "status": "MEASURED",
            "workload": workload,
            "candidate_variant": candidate,
            "runs": refs,
            "metrics": [{"name": "gold_goodput", "status": "MEASURED", "improvement_percent": 20}],
        }
        report["content_sha256"] = content_hash(report)
        path = tmp_path / f"{candidate}.json"
        write_json(path, report)
        reports[candidate] = {"path": path.name, "sha256": file_hash(path)}

    def compare_double(left, right):
        return json.loads((tmp_path / (left[0].split("-")[0] + ".json")).read_text())

    monkeypatch.setattr(selection, "compare_runs", compare_double)
    choices = {}
    for workload, variant in (("W-PIPE", "O1"), ("W-INTEGRATED", "O3")):
        choices[workload] = {
            "variant": variant,
            "metric": "gold_goodput",
            "rationale": "fixture rationale",
            "reviewers": ["Jaineel", "Harsh", "Aditya", "Vichitr"],
            "costs_accepted": True,
            "comparisons": [reports[variant]] if variant == "O1" else list(reports.values()),
        }
    receipt = {"schema_version": 1, "choices": choices}
    receipt["content_sha256"] = content_hash(receipt)
    write_json(tmp_path / "selection.json", receipt)
    return config, tmp_path, receipt


def test_no_evidence_has_no_default_winner():
    assert load_selection(None, load_config()) is None


def test_measured_choices_with_independent_and_interaction_evidence(selection_double):
    config, _, _ = selection_double
    result = load_selection("selection.json", config)
    assert result["variants"] == {"W-PIPE": "O1", "W-INTEGRATED": "O3"}


@pytest.mark.parametrize(
    "mutation", ["cost", "reviewers", "missing_independent", "unsupported", "tamper"]
)
def test_unreviewed_unsupported_or_unjustified_choices_rejected(selection_double, mutation):
    config, root, receipt = selection_double
    choice = receipt["choices"]["W-INTEGRATED"]
    if mutation == "cost":
        choice["costs_accepted"] = False
    elif mutation == "reviewers":
        choice["reviewers"] = ["Jaineel"]
    elif mutation == "missing_independent":
        choice["comparisons"] = choice["comparisons"][-1:]
    elif mutation == "unsupported":
        receipt["choices"]["W-PIPE"]["variant"] = "O2"
    else:
        (root / "O1-0/manifest.json").write_text("tampered")
    receipt["content_sha256"] = content_hash(receipt)
    (root / "selection.json").write_text(json.dumps(receipt))
    with pytest.raises(DependencyError):
        load_selection("selection.json", config)
