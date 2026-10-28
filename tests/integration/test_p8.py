import asyncio
import json
from uuid import uuid4

import pytest

from benchmarks.integration import (
    bind_runtime_inputs,
    check_observation,
    execute_reconciliation,
    run_cases,
    validate_review,
    validate_setup,
)
from benchmarks.integration_cases import BY_ID, expand_suites
from benchmarks.integration_faults import FaultGate
from projectctl.cli import main
from projectctl.config import load_config
from projectctl.providers import DependencyError, Invocation, ProviderRegistry, default_registry

from .doubles import ClockDouble, EventCaseDouble, HookDouble, event_evidence


def invocation(suite):
    return Invocation(
        "eval run",
        {"suite": suite},
        load_config("configs/evaluation.yaml"),
        str(uuid4()),
        "bench-" + uuid4().hex,
    )


def rows(workspace, result):
    directory = workspace / result["evidence_dir"]
    return directory, [
        json.loads(line) for line in (directory / "tests.jsonl").read_text().splitlines()
    ]


def test_aliases_are_exact_and_overlaps_do_not_repeat_cases():
    cases = expand_suites(["correctness", "data", "T-07"])
    assert len(cases) == len({case.case_id for case in cases})
    assert {case.suite for case in cases} == {
        "contracts",
        "D-01",
        "D-02",
        "D-03",
        "T-01",
        "T-03",
        "T-07",
        "T-08",
        "T-09",
        "T-12",
        "D-05",
    }
    assert [case.case_id for case in expand_suites(["T-11"])] == ["T-11/analytics", "T-11/kafka"]
    assert {case.barrier for case in expand_suites(["T-07"])} >= {
        "after_local_commit",
        "after_publish_before_outbox_mark",
        "after_sink_commit_before_offset_commit",
    }


def test_missing_providers_emit_every_case_without_a_false_pass(workspace):
    result = asyncio.run(run_cases(invocation(["smoke"]), ProviderRegistry()))
    directory, records = rows(workspace, result)
    assert result["exit_code"] == 4
    assert len(records) == 3 and all(row["status"] == "NOT_RUN" for row in records)
    assert all(row["input_fixture_hash"] is None for row in records)
    assert json.loads((directory / "correctness.json").read_text())["passed"] is False
    assert json.loads((directory / "manifest.json").read_text())["correctness_passed"] is None


def test_draft_cli_keeps_case_inventory_and_dependency_reasons(workspace, capsys):
    code = main(["eval", "run", "--suite", "correctness", "--config", "configs/evaluation.yaml"])
    result = json.loads(capsys.readouterr().out)
    _, records = rows(workspace, result)
    assert code == 4 and len(records) == len(expand_suites(["correctness"]))
    assert all(row["status"] == "NOT_RUN" for row in records)
    assert "explicitly draft" in records[0]["failure_reason"]
    assert result["metrics"] == []


def test_real_evaluation_refuses_stub_before_any_prepare(workspace):
    double = EventCaseDouble(workspace)
    registry = ProviderRegistry()
    registry.register_case("smoke/G1", double.binding)
    result = asyncio.run(run_cases(invocation(["smoke"]), registry))
    _, records = rows(workspace, result)
    assert result["exit_code"] == 4 and not double.calls
    assert "refuses test doubles" in records[0]["failure_reason"]


def test_explicit_double_preserves_fixture_and_cannot_complete_real_gate(workspace):
    double = EventCaseDouble(workspace)
    registry = ProviderRegistry()
    registry.register_case("smoke/G1", double.binding)
    result = asyncio.run(run_cases(invocation(["smoke"]), registry, allow_test_doubles=True))
    directory, records = rows(workspace, result)
    assert records[0]["status"] == "PASS" and records[0]["test_mode"] == "stub"
    assert double.calls == ["prepare", "exercise", "audit"]
    assert records[1]["status"] == records[2]["status"] == "NOT_RUN"
    frozen = json.loads((directory / "case-00/fixture.json").read_text())
    assert frozen["expected"]["events"] == {"valid": "a" * 64}
    assert not json.loads((directory / "correctness.json").read_text())["real_integration_passed"]
    original = (directory / "tests.jsonl").read_bytes()
    replay = execute_reconciliation(
        Invocation(
            "benchmark reconcile",
            {"run_dir": result["evidence_dir"]},
            None,
            str(uuid4()),
            "bench-recheck",
        )
    )
    assert replay["exit_code"] == 4  # absent G3 cases remain incomplete on read-only recheck
    assert (directory / "tests.jsonl").read_bytes() == original


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda value: value["audit"]["silver_events"].clear(),
        lambda value: value["audit"]["active_gold"].update(totals_by_currency={"INR": 1}),
        lambda value: value["audit"]["active_gold"].update(query_generation=0),
        lambda value: value["bronze"][1].update(wire_sha256="f" * 64),
        lambda value: value["bronze"][1].update(offset=0),
        lambda value: value["quarantine"].clear(),
        lambda value: value.update(namespace="dev"),
        lambda value: value["facts"].update(gold_logical_effects=1.0),
    ],
)
def test_corruption_fails_instead_of_relying_on_exported_pass_flags(workspace, corrupt):
    double = EventCaseDouble(workspace, corrupt=corrupt)
    registry = ProviderRegistry()
    registry.register_case("smoke/G1", double.binding)
    result = asyncio.run(run_cases(invocation(["smoke"]), registry, allow_test_doubles=True))
    _, records = rows(workspace, result)
    assert result["exit_code"] == 3 and records[0]["status"] == "FAIL"
    assert any(not item["passed"] for item in records[0]["assertions"])


def test_missing_collection_is_incomplete_not_zero(workspace):
    double = EventCaseDouble(
        workspace, corrupt=lambda value: value.update(collection_complete=False)
    )
    registry = ProviderRegistry()
    registry.register_case("smoke/G1", double.binding)
    result = asyncio.run(run_cases(invocation(["smoke"]), registry, allow_test_doubles=True))
    _, records = rows(workspace, result)
    assert result["exit_code"] == 4 and records[0]["status"] == "INCOMPLETE"


def test_provider_exception_is_retained_without_sensitive_text(workspace):
    double = EventCaseDouble(workspace, exercise_error=ConnectionError)
    registry = ProviderRegistry()
    registry.register_case("smoke/G1", double.binding)
    result = asyncio.run(run_cases(invocation(["smoke"]), registry, allow_test_doubles=True))
    directory, records = rows(workspace, result)
    assert result["exit_code"] == 4 and records[0]["status"] == "INCOMPLETE"
    assert "sensitive DSN" not in (directory / "tests.jsonl").read_text()
    assert (directory / "case-00/fixture.json").exists()


def test_real_bindings_require_review_before_callbacks(workspace):
    double = EventCaseDouble(workspace, mode="real")
    registry = ProviderRegistry()
    registry.register_case("smoke/G1", double.binding)
    result = asyncio.run(run_cases(invocation(["smoke"]), registry))
    assert result["exit_code"] == 4 and not double.calls


def test_review_pins_export_contract_and_independent_fixture(workspace):
    from projectctl.artifacts import file_hash

    fixture = workspace / "fixture.json"
    fixture.write_text("{}")
    review = workspace / "review.json"
    record = {
        "schema_version": 1,
        "read_only_audit": True,
        "namespace_scoped": True,
        "reviewers": ["Jaineel", "Harsh", "Aditya", "Vichitr"],
        "fixture_sha256": file_hash(fixture),
        "contracts": [{"path": "fixture.json", "sha256": file_hash(fixture)}],
    }
    review.write_text(json.dumps(record))
    assert validate_review(review, "bench-check", fixture)["namespace"] == "bench-check"
    fixture.write_text('{"changed":true}')
    with pytest.raises(DependencyError):
        validate_review(review, "bench-check", fixture)


def test_real_shaped_review_round_trips_through_saved_report_validation(workspace, monkeypatch):
    """Explicit setup/provider doubles isolate persistence, never certify real providers."""
    import benchmarks.integration as integration
    from benchmarks.integration import CaseBinding
    from benchmarks.reporting import _evaluation
    from projectctl.artifacts import file_hash, write_json

    case = BY_ID["D-01/source"]
    fixture = workspace / "source-fixture.json"
    write_json(fixture, {"case_id": case.case_id, "input": {"source": "synthetic"}})
    review = workspace / "review.json"
    write_json(
        review,
        {
            "schema_version": 1,
            "read_only_audit": True,
            "namespace_scoped": True,
            "reviewers": ["Jaineel", "Harsh", "Aditya", "Vichitr"],
            "fixture_sha256": file_hash(fixture),
            "contracts": [{"path": "source-fixture.json", "sha256": file_hash(fixture)}],
        },
    )

    async def prepare(ctx):
        return {"namespace": ctx["namespace"], "created_new": True}

    async def exercise(ctx, fixture, gate):
        return None

    async def audit(ctx):
        return {k: ctx[k] for k in ("namespace", "run_id", "case_id")} | {
            "collection_complete": True,
            "facts": dict(case.checks),
        }

    monkeypatch.setattr(integration, "validate_setup", lambda *args, **kwargs: None)
    registry = ProviderRegistry()
    registry.register_case(
        case.case_id, CaseBinding("real", fixture, prepare, exercise, audit, review)
    )
    result = asyncio.run(run_cases(invocation(["D-01"]), registry))
    directory, records = rows(workspace, result)
    assert records[0]["status"] == "PASS"
    _, rebuilt = _evaluation(directory / "manifest.json", {})
    assert rebuilt[0]["status"] == "PASS"


@pytest.mark.parametrize(
    "corruption", ["unacknowledged", "wrong-target", "lost-volume", "missing-recovery"]
)
def test_saved_fault_reconciliation_rechecks_journal_not_just_reference(workspace, corruption):
    from benchmarks.integration import CaseBinding
    from projectctl.artifacts import content_hash, file_hash, write_json

    case = BY_ID["D-03/resume"]
    fixture = workspace / "fault-fixture.json"
    write_json(fixture, {"case_id": case.case_id, "input": {"source": "explicit-double"}})

    async def prepare(ctx):
        return {"namespace": ctx["namespace"], "created_new": True}

    async def exercise(ctx, fixture, gate):
        await gate.run()

    async def audit(ctx):
        return {k: ctx[k] for k in ("namespace", "run_id", "case_id")} | {
            "collection_complete": True,
            "facts": dict(case.checks),
        }

    registry = ProviderRegistry()
    registry.register_case(
        case.case_id,
        CaseBinding("stub", fixture, prepare, exercise, audit, fault_hooks=HookDouble()),
    )
    result = asyncio.run(run_cases(invocation(["D-03"]), registry, allow_test_doubles=True))
    directory, records = rows(workspace, result)
    assert result["exit_code"] == 0
    path = directory / "case-00/faults.jsonl"
    journal = [json.loads(line) for line in path.read_text().splitlines()]
    if corruption == "unacknowledged":
        journal[0]["acknowledged"] = False
    elif corruption == "wrong-target":
        journal[0]["target"] = "another-worker"
    elif corruption == "lost-volume":
        journal[2]["restart"]["retained_volume"] = False
    else:
        journal.pop()
    path.write_text("".join(json.dumps(r) + "\n" for r in journal))
    # Reseal this disposable fixture to isolate semantic checking from hash checking.
    next(r for r in records[0]["artifact_refs"] if r["path"] == "case-00/faults.jsonl")[
        "sha256"
    ] = file_hash(path)
    (directory / "tests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    manifest = json.loads((directory / "manifest.json").read_text())
    for ref in manifest["artifacts"]:
        ref["sha256"] = file_hash(directory / ref["path"])
    manifest["content_sha256"] = content_hash(manifest)
    (directory / "manifest.json").write_text(json.dumps(manifest))
    replay = execute_reconciliation(
        Invocation(
            "benchmark reconcile",
            {"run_dir": result["evidence_dir"]},
            None,
            str(uuid4()),
            "bench-recheck",
        )
    )
    assert replay["exit_code"] == 4


def test_checkout_cannot_start_with_partial_projection_or_seed_proof():
    context = {"namespace": "bench-real"}
    setup = {"namespace": "bench-real", "created_new": True}
    with pytest.raises(DependencyError):
        validate_setup(setup, context, real=True)
    validate_setup(setup, context, real=False)
    with pytest.raises(DependencyError):
        validate_setup(setup | {"namespace": "dev"}, context, real=False)


def test_g3_cannot_pass_on_empty_transaction_audit():
    expected, audit = event_evidence("bench-example")
    observed = {
        "namespace": "bench-example",
        "run_id": "test",
        "case_id": "smoke/G3-success",
        "collection_complete": True,
        "facts": dict(BY_ID["smoke/G3-success"].checks),
        "audit": audit,
    }
    assertions, _ = check_observation(
        BY_ID["smoke/G3-success"],
        {"expected": expected},
        observed,
        {"namespace": "bench-example", "run_id": "test"},
    )
    assert any(not row["passed"] for row in assertions)


def test_saved_evidence_tamper_is_incomplete_and_original_is_untouched(workspace):
    result = asyncio.run(run_cases(invocation(["smoke"]), ProviderRegistry()))
    directory, _ = rows(workspace, result)
    (directory / "tests.jsonl").write_text("{}\n")
    replay = execute_reconciliation(
        Invocation(
            "benchmark reconcile",
            {"run_dir": result["evidence_dir"]},
            None,
            str(uuid4()),
            "bench-recheck",
        )
    )
    assert replay["exit_code"] == 4
    assert (directory / "tests.jsonl").read_text() == "{}\n"


def test_registration_is_explicit_and_failures_are_not_silent(monkeypatch):
    monkeypatch.setenv("PROJECTCTL_ADAPTER_MODULE", "nonexistent_p8_owner_bindings")
    registry = default_registry()
    assert "ModuleNotFoundError" in registry.binding_failure
    assert registry.case("smoke/G1") is None
    with pytest.raises(ValueError):
        registry.register_case("unknown", None)


@pytest.mark.parametrize("target", ["analytics", "kafka"])
def test_outages_use_separate_targets_at_second_180_for_30_seconds(target):
    case = BY_ID["T-11/" + target]
    clock, hooks, journal = ClockDouble(), HookDouble(), []
    ctx = {"namespace": "bench-fault", "run_id": "run", "case_id": case.case_id}
    gate = FaultGate(case, ctx, hooks, journal.append, clock=clock, sleep=clock.sleep)
    asyncio.run(gate.run(measurement_origin=10.0))
    assert hooks.calls == ["arm", "ack", "stop", "restart"]
    assert [row["phase"] for row in journal] == ["acknowledged", "injected", "recovered"]
    assert journal[1]["measurement_second"] == 180
    assert journal[2]["outage_seconds"] == 30 and gate.completed


def test_wrong_barrier_namespace_cannot_stop_a_service():
    case = BY_ID["T-07/publish-before-mark"]
    hooks = HookDouble(bad_ack=True)
    gate = FaultGate(
        case,
        {"namespace": "bench-x", "run_id": "x", "case_id": case.case_id},
        hooks,
        lambda _: None,
    )
    with pytest.raises(DependencyError):
        asyncio.run(gate.run())
    assert hooks.calls == ["arm", "ack"]


@pytest.mark.parametrize("stop_error", [False, True])
def test_restart_attempted_even_on_lost_stop_response_and_volume_proof_required(stop_error):
    case = BY_ID["T-07/publish-before-mark"]
    hooks = HookDouble(retained=False, stop_error=stop_error)
    gate = FaultGate(
        case,
        {"namespace": "bench-x", "run_id": "x", "case_id": case.case_id},
        hooks,
        lambda _: None,
    )
    with pytest.raises((DependencyError, ConnectionError)):
        asyncio.run(gate.run())
    assert hooks.calls[-1] == "restart" and not gate.completed


def test_missing_actual_measurement_origin_does_not_inject_outage():
    case = BY_ID["T-11/kafka"]
    hooks = HookDouble()
    gate = FaultGate(case, {"namespace": "bench-x"}, hooks, lambda _: None)
    with pytest.raises(DependencyError):
        asyncio.run(gate.run())
    assert hooks.calls == []


def test_runtime_generated_ids_are_bound_without_changing_business_values():
    order, quote = str(uuid4()), str(uuid4())
    fixture = {
        "expected": {
            "orders": {"@id:order": {"quote_id": "@id:quote", "total_amount_minor": 100}},
            "events": None,
            "gold_totals_by_currency": {"INR": 100},
        }
    }
    receipt = {
        "identities": {"@id:order": order, "@id:quote": quote},
        "source_expectations": {"events": {"source-event": "e" * 64}},
    }
    bound = bind_runtime_inputs(fixture, receipt)
    assert bound["expected"]["orders"] == {order: {"quote_id": quote, "total_amount_minor": 100}}
    assert bound["expected"]["gold_totals_by_currency"] == {"INR": 100}
    assert fixture["expected"]["events"] is None
    with pytest.raises(DependencyError):
        bind_runtime_inputs(
            fixture, {"source_expectations": {"gold_totals_by_currency": {"INR": 0}}}
        )
    with pytest.raises(DependencyError):
        bind_runtime_inputs(fixture, {"expected": {"total_amount_minor": 0}})


def test_runtime_source_receipt_cannot_rewrite_a_frozen_event_set():
    with pytest.raises(DependencyError):
        bind_runtime_inputs(
            {"expected": {"events": {"original": "a" * 64}}},
            {"source_expectations": {"events": {"changed": "b" * 64}}},
        )


def test_real_oracle_stays_incomplete_without_explicit_scoped_review_token():
    from benchmarks.reconciliation import reconcile_run

    expected, observed = event_evidence("bench-review-test")
    observed["test_mode"] = "real"  # pure evidence projection double, not real services
    review_double = {
        "namespace": "bench-review-test",
        "review_sha256": "e" * 64,
        "reviewers": ["Jaineel", "Harsh", "Aditya", "Vichitr"],
        "contracts": [{"path": "explicit-contract-double", "sha256": "f" * 64}],
    }
    assert reconcile_run(expected, observed)["status"] == "INCOMPLETE"
    assert reconcile_run(expected, observed, binding_review=review_double)["status"] == "PASS"
    review_double["namespace"] = "dev"
    assert reconcile_run(expected, observed, binding_review=review_double)["status"] == "INCOMPLETE"


# P4 treats a missing mandatory planned emission receipt as an integrity failure.
@pytest.mark.parametrize("corruption,code", [(None, 0), ("bad-gold", 3), ("missing-emission", 3)])
def test_saved_benchmark_rechecks_both_admission_and_downstream_without_writes(
    workspace, corruption, code
):
    from projectctl.artifacts import canonical_json, file_hash, save_evidence, write_json
    from projectctl.models import ExitCode
    from projectctl.providers import ProviderResult

    run_id, namespace = str(uuid4()), "bench-benchmark-projection-double"
    config = load_config("configs/evaluation.yaml")
    source = workspace / config.artifacts.root / run_id
    source.mkdir(parents=True)
    expected, observed = event_evidence(namespace)
    if corruption == "bad-gold":
        observed["active_gold"]["business_rows"] = {"pipeline_minute": {"event_count": 2}}
    write_json(source / "expected.json", expected)
    write_json(source / "observed.json", observed)
    planned = [
        {"logical_record_id": key, "phase": "measurement"}
        for key in expected["source_dispositions"]
    ]
    (source / "planned.jsonl").write_bytes(b"".join(canonical_json(row) + b"\n" for row in planned))
    write_json(
        source / "workload_manifest.json",
        {
            "kind": "finite",
            "warmup_seconds": None,
            "duration_seconds": None,
            "planned_sha256": file_hash(source / "planned.jsonl"),
        },
    )
    emissions = [
        {
            "record_id": row["logical_record_id"],
            "actual_send_at": "2026-10-27T00:00:00Z",
            "outcome": "acknowledged",
            "ack_elapsed_seconds": 0.1,
            "source": {"topic": "fixture", "partition": 0, "offset": index},
            "wire_sha256": expected["bronze_sha256"][row["logical_record_id"]],
        }
        for index, row in enumerate(planned)
    ]
    if corruption == "missing-emission":
        emissions.pop()
    (source / "emissions.jsonl").write_bytes(
        b"".join(canonical_json(row) + b"\n" for row in emissions)
    )
    original = save_evidence(
        Invocation("benchmark run", {}, config, run_id, namespace),
        ProviderResult(ExitCode.COMPLETED, ("explicit saved evidence double",), "stub"),
        execution={
            "status": "MEASURED",
            "started_at": "2026-10-27T00:00:00Z",
            "completed_at": "2026-10-27T00:00:01Z",
            "correctness_passed": True,
            "metrics": [],
        },
    )
    before = {path.name: file_hash(path) for path in source.iterdir() if path.is_file()}
    recheck = execute_reconciliation(
        Invocation(
            "benchmark reconcile",
            {"run_dir": original["evidence_dir"]},
            None,
            str(uuid4()),
            "bench-read-only",
        )
    )
    assert recheck["exit_code"] == code
    assert before == {path.name: file_hash(path) for path in source.iterdir() if path.is_file()}
