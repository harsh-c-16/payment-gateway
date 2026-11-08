"""Explicit projection/review doubles check saved quality dispatch and hash gates."""

import json

import pytest

from benchmarks.analytics_recheck import recheck
from benchmarks.workloads import generate_workload
from projectctl.artifacts import file_hash, write_json
from projectctl.config import load_config
from projectctl.providers import DependencyError


@pytest.mark.parametrize("fault", [None, "raw_hash", "stub", "selection"])
def test_saved_quality_uses_frozen_inputs_and_replays_the_independent_oracle(
    tmp_path, monkeypatch, fault
):
    config = load_config()
    monkeypatch.setattr("projectctl.config.ROOT", tmp_path)
    projection = {
        "active_skus": [f"FK-DOUBLE-{i:05}" for i in range(19920)],
        "dataset_revision": "explicit-catalogue-double",
    }
    manifest = generate_workload("W-QUALITY", config.generator.seed, projection).as_dict()
    context = {
        "namespace": "bench-saved-quality-double",
        "run_id": "explicit-run-double",
        "workload_id": "W-QUALITY",
    }
    expected = context | {
        "audit_kind": "W-QUALITY",
        "seed": config.generator.seed,
        "selected_skus": manifest["selected_skus"],
        "dataset_revision": projection["dataset_revision"],
    }
    raw = {
        "namespace": context["namespace"],
        "run_id": context["run_id"],
        "test_mode": "stub" if fault == "stub" else "real",
        "collection_complete": True,
    }
    write_json(tmp_path / "resolved_config.json", config.model_dump())
    write_json(tmp_path / "quality_raw_audit.json", raw)
    write_json(
        tmp_path / "observed.json",
        {"raw_audit_sha256": file_hash(tmp_path / "quality_raw_audit.json")},
    )
    review = {
        "contracts": [
            {"path": path}
            for path in (
                "benchmarks/analytics_recheck.py",
                "benchmarks/pipeline_audit.py",
                "infra/analytics_runtime.py",
                "infra/analytics_resources.py",
                "pipelines/ingestion/adapters.py",
            )
        ]
    }
    monkeypatch.setattr("benchmarks.analytics_recheck.verify_review", lambda _: review)
    monkeypatch.setattr("benchmarks.composition.catalog_projection", lambda _: projection)
    calls = []

    def oracle(ctx, directory, observed):
        calls.append(ctx)
        assert observed["binding_review_verified"] is True
        return {"status": "INCOMPLETE", "passed": None, "fixture": "explicit oracle spy"}

    monkeypatch.setattr("benchmarks.quality_audit.reconcile_quality", oracle)
    if fault == "raw_hash":
        (tmp_path / "quality_raw_audit.json").write_text(json.dumps(raw) + "\n", encoding="utf-8")
    elif fault == "selection":
        expected["selected_skus"] = list(reversed(expected["selected_skus"]))
    if fault:
        with pytest.raises(DependencyError):
            recheck(tmp_path, context, expected)
        assert calls == []
    else:
        assert recheck(tmp_path, context, expected)["passed"] is None
        assert len(calls) == 1 and calls[0]["selected_skus"] == manifest["selected_skus"]
