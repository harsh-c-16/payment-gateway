from copy import deepcopy

import pytest

from projectctl.cli import preflight
from projectctl.config import (
    InputError,
    load_config,
    load_matrix,
    load_yaml,
    repo_path,
    resolve_config,
    validate_config,
    workload_timing,
)


def test_reference_config_and_core_matrix_validate():
    config = load_config()
    matrix = load_matrix("configs/core_matrix.yaml", config)
    assert len(matrix.rows) == 11
    assert config.state == "draft"
    assert config.dataset.dictionary_sha256 is None
    assert config.assistant.llm_max_calls == 0
    assert "C-BEST" not in config.variants
    assert any(row.selection == "measured_best" for row in matrix.rows)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(schema_version=True),
        lambda d: d.update(unknown_field=True),
        lambda d: d["generator"].update(rtae=500),
        lambda d: d["generator"].update(concurrency="32"),
        lambda d: d["generator"].update(concurrency=True),
        lambda d: d["generator"].update(rate_per_second=float("nan")),
        lambda d: d["dataset"].update(dictionary_sha256="plausible-but-not-a-hash"),
        lambda d: d["assistant"].update(llm_max_calls=1),
        lambda d: d["assistant"].update(allow_intent_llm=True),
        lambda d: d["variants"]["O1"]["config"].update(gold_publish_interval_ms=5000),
        lambda d: d["variants"]["O1"]["allowed_differences"].append("gold_publish_interval_ms"),
        lambda d: d["variants"]["O1"]["config"].update(sink_batch_max_rows=1000),
        lambda d: d["variants"]["B0"]["config"].update(catalog_chunk_rows=1),
        lambda d: d["profile"]["service_allocations"]["catalog"].update(cpu_cores=99.0),
        lambda d: d["dataset"].update(source_path="../outside.csv"),
        lambda d: d["artifacts"].update(root="../outside"),
        lambda d: d["workloads"].pop("W-QUALITY"),
        lambda d: d["workloads"]["W-SEARCH"].update(rate_per_second=None),
        lambda d: d["faults"]["analytics-outage"].update(target=None),
    ],
)
def test_invalid_controls_are_rejected(mutate):
    data = deepcopy(load_yaml("configs/evaluation.yaml"))
    mutate(data)
    with pytest.raises(InputError):
        validate_config(data)


def test_variant_resolution_is_complete_and_does_not_mutate_baseline():
    config = load_config()
    original = deepcopy(config.model_dump())
    resolved = resolve_config(config, "W-SEARCH", "R-ANN")
    assert resolved.retrieval.mode == "hybrid_ann"
    assert resolved.generator.rate_per_second == 20
    assert config.model_dump() == original
    assist = resolve_config(config, "W-AGENT", "A-ASSIST")
    assert assist.assistant.llm_max_calls == 1
    assert assist.assistant.provider is None
    assert any("live NOT_RUN" in reason for reason in preflight(assist, "W-AGENT"))


@pytest.mark.parametrize("workload", ["W-IMPORT", "W-QUALITY", "W-AGENT", "W-ANALYTICS"])
def test_finite_and_query_workloads_do_not_use_sustained_duration(workload):
    timing = workload_timing(load_config(), workload)
    assert timing["duration_seconds"] is None
    assert timing["warmup_seconds"] is None


def test_analytics_query_counts_and_sustained_timing():
    config = load_config()
    assert workload_timing(config, "W-ANALYTICS")["executions_per_query"] == 30
    assert workload_timing(config, "W-ANALYTICS")["warmups_per_query"] == 3
    assert workload_timing(config, "W-PIPE")["duration_seconds"] == 600


def test_duplicate_yaml_keys_rejected(workspace):
    (workspace / "configs" / "duplicate.yaml").write_text("schema_version: 1\nschema_version: 2\n")
    with pytest.raises(InputError, match="unique"):
        load_yaml("configs/duplicate.yaml")


def test_missing_hashes_block_even_if_draft_flag_is_removed(workspace):
    config = load_config()
    config.state = "ready"
    config.profile.allocation_status = "enforced"
    reasons = preflight(config, "W-PIPE")
    assert any("dictionary_sha256" in reason for reason in reasons)
    assert any("fixture hash" in reason for reason in reasons)
    assert any("source CSV unavailable" in reason for reason in reasons)
    assert any("infrastructure lock" in reason for reason in reasons)
    assert any("event_schemas lock" in reason for reason in reasons)


def test_source_checksum_mismatch_is_bad_input(workspace):
    config = load_config()
    source = repo_path(config.dataset.source_path)
    source.parent.mkdir(parents=True)
    source.write_bytes(b"wrong CSV bytes")
    with pytest.raises(InputError, match="SHA-256"):
        preflight(config, "W-PIPE")


def test_schema_errors_do_not_echo_secrets():
    data = deepcopy(load_yaml("configs/evaluation.yaml"))
    data["dataset"]["expected_sha256"] = "secret-token-never-echo"
    with pytest.raises(InputError) as exc:
        validate_config(data)
    assert "secret-token-never-echo" not in str(exc.value)


def test_matrix_unknown_fields_and_unsupported_pairs_fail(workspace):
    path = workspace / "configs" / "bad_matrix.yaml"
    path.write_text(
        "schema_version: 1\nrepetitions: 3\nrows:\n  - {workload: W-SEARCH, variants: [I1]}\n"
    )
    with pytest.raises(InputError):
        load_matrix("configs/bad_matrix.yaml", load_config())
