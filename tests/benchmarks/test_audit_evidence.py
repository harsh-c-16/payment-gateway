"""P1-P9 audit regressions. All evidence below is an explicit small test fixture."""

import json


import pytest


from benchmarks.observation_summary import rebuild


from projectctl.artifacts import content_hash, file_hash, write_json


def telemetry_fixture(directory, *, missing_timer=True):
    """Three acknowledged requests, one retained timer: never a complete cohort."""
    context = {
        "run_id": "fixture-run",
        "namespace": "bench-fixture",
        "variant": "B0",
        "workload": "W-SEARCH",
        "mode": "stub",
        "shared_host_clock": True,
        "duration_seconds": 1,
        "interval_seconds": 1,
        "collectors": [
            {
                "series": [
                    {
                        "key": "rss",
                        "metric": "process_resident_memory_bytes",
                        "component": "fixture",
                        "unit": "bytes",
                        "labels": {},
                    }
                ]
            }
        ],
    }
    write_json(directory / "observation_context.json", context)
    write_json(directory / "observation_end.json", {"status": "COMPLETED"})
    observations = [
        {
            "series_key": "rss",
            "sequence": 0,
            "run_id": "fixture-run",
            "namespace": "bench-fixture",
            "variant": "B0",
            "workload": "W-SEARCH",
            "test_mode": "stub",
            "status": "MEASURED",
            "value": 100,
        }
    ]
    emissions = [
        {
            "record_id": f"r-{n}",
            "event_or_request_id": f"e-{n}",
            "phase": "measurement",
            "expected_disposition": "new_valid",
            "outcome": "acknowledged",
            "ack_elapsed_seconds": n + 1,
        }
        for n in range(3)
    ]
    planned = [
        {"logical_record_id": f"r-{n}", "phase": "measurement", "expected_disposition": "new_valid"}
        for n in range(3)
    ]
    timings = [
        {
            "run_id": "fixture-run",
            "namespace": "bench-fixture",
            "component": "catalog",
            "stage": "query",
            "phase": "measurement",
            "event_id": f"e-{n}",
            "record_id": f"r-{n}",
            "duration_seconds": 0.01,
            "clock_domain": "fixture_monotonic",
            "timing_validity": "VALID",
        }
        for n in range(1 if missing_timer else 3)
    ]
    for name, rows in (
        ("observations", observations),
        ("planned", planned),
        ("emissions", emissions),
        ("timings", timings),
    ):
        (directory / (name + ".jsonl")).write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
    freeze_telemetry(directory)


def freeze_telemetry(directory):
    manifest = {
        "artifacts": [
            {"path": p.name, "sha256": file_hash(p)}
            for p in sorted(directory.iterdir())
            if p.name
            in {
                "observation_context.json",
                "observation_end.json",
                "observations.jsonl",
                "timings.jsonl",
                "planned.jsonl",
                "emissions.jsonl",
                "generator.json",
                "admission.json",
            }
            and p.is_file()
        ]
    }
    manifest["content_sha256"] = content_hash(manifest)
    (directory / "telemetry_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_offline_latency_does_not_learn_its_cohort_from_received_timers(tmp_path):
    telemetry_fixture(tmp_path)
    row = rebuild(tmp_path)["latencies"][0]
    assert row["cohort_count"] == 3
    assert row["sample_count"] == 1
    assert row["missing_timing_count"] == 2
    assert row["status"] == "INCOMPLETE"
    assert row["complete_cohort_p99"] is None


def test_unfinished_requests_remain_unresolved_even_with_explicit_null_timers(tmp_path):
    telemetry_fixture(tmp_path, missing_timer=False)
    path = tmp_path / "emissions.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[1]["outcome"] = rows[2]["outcome"] = "unresolved"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    path = tmp_path / "timings.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    for row in rows[1:]:
        row.update(duration_seconds=None, timing_validity="MISSING")
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    freeze_telemetry(tmp_path)
    row = rebuild(tmp_path)["latencies"][0]
    assert row["unresolved_count"] == 2
    assert row["completed_count"] == 1
    assert row["complete_cohort_p99"] is None


def test_event_timers_bind_to_the_original_offer_when_duplicates_complete_later(tmp_path):
    telemetry_fixture(tmp_path, missing_timer=False)
    path = tmp_path / "observation_context.json"
    context = json.loads(path.read_text())
    context["workload"] = "W-PIPE"
    path.write_text(json.dumps(context))
    path = tmp_path / "observations.jsonl"
    path.write_text(path.read_text().replace("W-SEARCH", "W-PIPE"))
    path = tmp_path / "planned.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[2]["expected_disposition"] = "duplicate_delivery"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    path = tmp_path / "emissions.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    rows[2].update(event_or_request_id="e-0", expected_disposition="duplicate_delivery")
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    path = tmp_path / "timings.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()][:2]
    for row in rows:
        row.update(stage="producer_to_gold", record_id=None)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    freeze_telemetry(tmp_path)
    row = rebuild(tmp_path)["latencies"][0]
    assert row["cohort_count"] == row["sample_count"] == 2
    assert row["status"] == "MEASURED"


def test_performance_latency_uses_stage_unresolved_count(tmp_path, monkeypatch):
    import benchmarks.performance_metrics as metrics
    from projectctl.config import load_config

    write_json(
        tmp_path / "admission.json", {"phases": {"measurement": {"unresolved": 0, "planned": 100}}}
    )
    monkeypatch.setattr(
        metrics,
        "rebuild",
        lambda _: {
            "rates": {"gold_goodput": 1},
            "series": [],
            "latencies": [
                {
                    "component": "analytics",
                    "stage": "producer_to_gold",
                    "phase": "measurement",
                    "sample_count": 1,
                    "cohort_count": 100,
                    "unresolved_count": 99,
                    "missing_timing_count": 0,
                    "timing_validity": "VALID",
                    "status": "INCOMPLETE",
                    "completed_only": {"p50": 0.01, "p95": 0.01, "p99": 0.01},
                }
            ],
        },
    )
    result = {
        m.name: m
        for m in metrics.derive_metrics(
            tmp_path, load_config(), "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "W-PIPE", []
        )
    }
    assert result["producer_to_gold_p95_ms"].unresolved_count == 99


@pytest.mark.parametrize("corrupt", [False, True])
def test_performance_loader_requires_summary_agreement_with_raw_evidence(
    tmp_path, monkeypatch, corrupt
):
    """Explicit verified-bundle/audit doubles isolate the metric loader boundary."""
    import benchmarks.performance as performance
    from projectctl.config import load_config
    from projectctl.models import Metric, Summary
    from projectctl.providers import DependencyError

    telemetry_fixture(tmp_path, missing_timer=False)
    config = load_config()
    config.profile.allocation_status = "enforced"
    run_id = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    sha = content_hash(config.model_dump())
    metric = Metric(
        name="query_p95_ms",
        unit="milliseconds",
        value=999,
        sample_count=3,
        numerator=None,
        denominator=None,
        cohort="measurement",
        quantile_method="nearest-rank",
        unresolved_count=0,
        timing_validity="VALID",
        run_id=run_id,
        config_sha256=sha,
        status="MEASURED",
        evidence_path="timings.jsonl",
    )
    summary = Summary(
        schema_version=1,
        run_id=run_id,
        namespace="bench-fixture",
        command="benchmark run",
        status="MEASURED",
        exit_code=0,
        test_mode="real",
        reasons=[],
        metrics=[metric],
        artifact_refs=[],
        config_sha256=sha,
    )
    manifest = {
        "status": "MEASURED",
        "correctness_passed": True,
        "git": {"commit": "a" * 40, "dirty": False},
        "run_id": run_id,
        "namespace": "bench-fixture",
        "workload_id": "W-SEARCH",
        "variant_id": "B0",
        "resolved_config": config.model_dump(),
        "config_sha256": sha,
        "host": {"resources_verified": True},
        "workload_protocol": {
            "kind": "sustained",
            "warmup_seconds": 60,
            "duration_seconds": 600,
            "drain_seconds": 120,
        },
    }
    monkeypatch.setattr(performance, "verified_bundle", lambda *args: manifest)
    monkeypatch.setattr(performance, "validate_outputs", lambda *args: {"passed": True})
    write_json(tmp_path / "summary.json", summary.model_dump())
    write_json(tmp_path / "resolved_config.json", config.model_dump())
    write_json(tmp_path / "execution_order.json", {"fault": "none"})
    write_json(
        tmp_path / "execution.json",
        {"test_mode": "real", "evidence_kind": "performance", "sut_performance": "MEASURED"},
    )
    write_json(tmp_path / "performance_validation.json", {"passed": True})
    write_json(
        tmp_path / "admission.json",
        {
            "phases": {
                "measurement": {
                    "unresolved": 0,
                    "missed": 0,
                    "planned": 3,
                    "acknowledged_in_window": 3,
                }
            }
        },
    )
    write_json(tmp_path / "generator.json", {"window_seconds": 600, "measured_job_seconds": 0})
    freeze_telemetry(tmp_path)
    from benchmarks.performance_metrics import admission_metrics, derive_metrics

    summary.metrics = derive_metrics(
        tmp_path,
        config,
        run_id,
        "W-SEARCH",
        admission_metrics(
            config,
            run_id,
            "W-SEARCH",
            {"window_seconds": 600, "measured_job_seconds": 0},
            {
                "phases": {
                    "measurement": {"unresolved": 0, "planned": 3, "acknowledged_in_window": 3}
                }
            },
        ),
    )
    if corrupt:
        next(m for m in summary.metrics if m.name == "query_p95_ms").value = 999
    (tmp_path / "summary.json").write_text(json.dumps(summary.model_dump()), encoding="utf-8")
    # The bundle verifier is an explicit double; only the raw metric boundary is under test.
    if corrupt:
        with pytest.raises(DependencyError, match="summary metrics"):
            performance.load_performance_run(tmp_path)
    else:
        assert performance.load_performance_run(tmp_path)["summary"] == summary.model_dump()


@pytest.mark.parametrize("change", ["duplicate", "namespace", "clock"])
def test_invalid_stage_timers_cannot_become_latency_samples(tmp_path, change):
    telemetry_fixture(tmp_path, missing_timer=False)
    path = tmp_path / "timings.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    if change == "duplicate":
        rows.append(rows[0])
    elif change == "namespace":
        rows[0]["namespace"] = "other"
    else:
        rows[0]["clock_domain"] = "another_machine"
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    freeze_telemetry(tmp_path)
    with pytest.raises(ValueError):
        rebuild(tmp_path)
