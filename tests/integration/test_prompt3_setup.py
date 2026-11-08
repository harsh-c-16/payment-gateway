"""Actual source/provider setup only: no database, Kafka or whole-service pass is implied."""

import json
from uuid import uuid4

import pytest

from benchmarks.dataset_checks import inspect_source
from projectctl.config import load_config, repo_path
from projectctl.models import ExitCode
from projectctl.providers import Invocation, default_registry


def test_real_catalog_profile_matches_independent_exact_source_check(tmp_path, monkeypatch):
    config = load_config()
    source = repo_path(config.dataset.source_path)
    if not source.is_file():
        pytest.skip("actual source CSV unavailable; live source/profile check NOT_RUN")
    monkeypatch.setenv("PROJECTCTL_ADAPTER_MODULE", "projectctl.jaineel")
    registry = default_registry()
    invocation = Invocation(
        "catalog profile",
        {"source": str(source), "out": str(tmp_path)},
        None,
        str(uuid4()),
        "bench-prompt3-source",
    )
    result = registry.invoke(invocation)
    assert result.code == ExitCode.COMPLETED and result.test_mode == "real"
    independent = inspect_source(source)
    profile = json.loads((tmp_path / "profile.json").read_text("utf-8"))
    assert independent["status"] == "PASS"
    assert profile["source_sha256"] == independent["source_sha256"]
    assert profile["selected_counts"] == {
        key: independent["observed"][key]
        for key in ("canonical_active", "canonical_inactive_missing_price", "superseded")
    }
    assert independent["performance"] == "NOT_RUN"
