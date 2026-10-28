from collections import Counter, defaultdict

import pytest

from benchmarks.workloads import generate_workload
from projectctl.config import InputError

CATALOG = {"active_skus": [f"FK-{i:05}" for i in range(19920)]}


def test_pipe_frozen_subset_schedule_and_independent_input_order():
    workload = generate_workload("W-PIPE", 42, CATALOG)
    data = workload.as_dict()
    assert data["phase_counts"] == {"measurement": 300000, "warmup": 30000}
    assert len(data["selected_skus"]) == 10000
    reversed_catalog = {"active_skus": list(reversed(CATALOG["active_skus"]))}
    assert (
        generate_workload("W-PIPE", 42, reversed_catalog).as_dict()["selected_skus"]
        == data["selected_skus"]
    )
    assert workload.recipe == generate_workload("W-PIPE", 42, CATALOG).recipe
    rows = list(
        generate_workload("W-PIPE", 42, CATALOG, warmup_seconds=1, duration_seconds=1).records()
    )
    assert [r["offset_seconds"] for r in rows[:3]] == [0, 0.002, 0.004]
    assert rows[500]["phase"] == "measurement" and rows[500]["offset_seconds"] == 1


def test_hot_key_absolute_versions_continue_across_phases():
    records = generate_workload(
        "W-PIPE",
        42,
        CATALOG,
        key_distribution="hot80",
        warmup_seconds=1,
        duration_seconds=1,
        rate_per_second=100,
    ).records()
    versions = defaultdict(list)
    for row in records:
        versions[row["payload"]["sku"]].append(row["payload"]["stock_version"])
    assert max(map(len, versions.values())) >= 160
    for values in versions.values():
        assert values == list(range(1, len(values) + 1))


def test_frozen_inputs_cannot_be_changed_by_caller():
    templates = [{"query_id": "q1", "request": {"nested": [1]}}]
    manifest = generate_workload("W-SEARCH", 42, templates=templates)
    templates[0]["request"]["nested"].append(2)
    assert manifest.as_dict()["templates"][0]["request"]["nested"] == [1]


def test_quality_recipe_preserves_98500_1000_500_and_earlier_duplicate_targets():
    workload = generate_workload("W-QUALITY", 42, CATALOG)
    assert workload.as_dict()["duration_seconds"] is None
    classes = Counter()
    originals = {}
    for row in workload.records():
        classes[row["expected_disposition"]] += 1
        assert row["offset_seconds"] is None
        if row["duplicate_of"] is not None:
            assert row["duplicate_of"] < row["record_ordinal"]
            assert originals[row["duplicate_of"]] == row["logical_content_sha256"]
        elif row["expected_disposition"] == "new_valid":
            originals[row["record_ordinal"]] = row["logical_content_sha256"]
    assert classes == {"new_valid": 98500, "duplicate_delivery": 1000, "invalid": 500}


def test_query_protocol_randomizes_complete_rounds_and_counts_exactly():
    templates = [{"query_id": f"Q{i}"} for i in range(1, 7)]
    rows = list(generate_workload("W-ANALYTICS", 42, templates=templates).records())
    counts = Counter((r["phase"], r["payload"]["query_id"]) for r in rows)
    assert len(rows) == 198
    assert all(counts["warmup", f"Q{i}"] == 3 for i in range(1, 7))
    assert all(counts["measurement", f"Q{i}"] == 30 for i in range(1, 7))
    assert all(r["offset_seconds"] is None for r in rows)


def test_import_and_agent_are_finite_not_600_second_jobs():
    manifest = generate_workload("W-IMPORT", 42).as_dict()
    assert manifest["source_observations"] == 20000
    assert manifest["expected_counts"]["planned"] == 1  # one delegated whole import
    assert manifest["warmup_seconds"] is None and manifest["duration_seconds"] is None
    agent = generate_workload("W-AGENT", 42, templates=[{"scenario_id": str(i)} for i in range(60)])
    assert agent.as_dict()["expected_counts"]["planned"] == 60


@pytest.mark.parametrize("active", [[], ["same", "same"], ["bad space"], [None], [{}]])
def test_invalid_or_unavailable_manifest_is_explicit(active):
    with pytest.raises(InputError):
        generate_workload("W-PIPE", 42, {"active_skus": active}, key_count=1)


@pytest.mark.parametrize("workload", ["W-SEARCH", "W-INTEGRATED", "W-ANALYTICS", "W-AGENT"])
def test_missing_frozen_templates_never_become_fake_requests(workload):
    with pytest.raises(InputError):
        generate_workload(workload, 42, CATALOG)
