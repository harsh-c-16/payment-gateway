"""Owner exports judged by the harness's own frozen checks and real FaultGate."""

import asyncio
import json
from uuid import uuid4

import psycopg
import pytest

from benchmarks.integration import check_observation
from benchmarks.integration_cases import BY_ID
from benchmarks.integration_faults import FaultGate
from pipelines.catalog import exports
from pipelines.catalog.faults import BARRIER, TARGET, CatalogImportFaults
from shared.event_transport.codec import EventCodec
from shared.local_diagnostics import quarantine_local_diagnostic
from tests.catalog.helpers import apply_record, import_rows, row, stock_record, write_csv
from tests.pipelines.transport_doubles import offline_cache

CODEC = EventCodec(offline_cache(), source_service="inventory")


def harness_verdict(case_id, facts):
    context = {"namespace": "bench-x", "run_id": "r"}
    observed = {
        "namespace": "bench-x",
        "run_id": "r",
        "case_id": case_id,
        "collection_complete": True,
        "facts": facts,
    }
    assertions, _ = check_observation(BY_ID[case_id], {"expected": {}}, observed, context)
    return [item for item in assertions if not item["passed"]]


def test_d01_facts_pass_the_frozen_harness_checks(source_csv):
    assert harness_verdict("D-01/source", exports.d01_facts(source_csv)) == []


def test_d02_facts_pass_the_frozen_harness_checks(source_csv):
    assert harness_verdict("D-02/normalize", exports.d02_facts(source_csv)) == []


def test_d02_reports_a_broken_dirty_expectation(tmp_path, source_csv):
    fixture = json.loads(exports.DIRTY_FIXTURE.read_text(encoding="utf-8"))
    case = next(c for c in fixture["cases"] if c["case_id"] == "ordinary-price")
    case["expected"]["normalized_fields"]["price_minor"] = 1
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(fixture), encoding="utf-8")
    facts = exports.d02_facts(source_csv, dirty_fixture=path)
    assert facts["dirty_fixture_failures"] == 1
    assert harness_verdict("D-02/normalize", facts)


def test_d03_fault_gate_kills_at_barrier_then_resume_and_repeat_change_nothing(
    tmp_path, database_url, monkeypatch
):
    monkeypatch.setenv("CATALOG_DATABASE_URL", database_url)
    namespace = "bench-h-" + uuid4().hex[:16]
    source = write_csv(tmp_path / "source.csv", [row(f"P{i:05}") for i in range(2500)])
    out = tmp_path / namespace
    hooks = CatalogImportFaults(source, out, url=database_url)
    journal = []
    context = {"namespace": namespace, "run_id": "run", "case_id": "D-03/resume"}
    gate = FaultGate(BY_ID["D-03/resume"], context, hooks, journal.append)
    assert (BY_ID["D-03/resume"].barrier, BY_ID["D-03/resume"].target) == (BARRIER, TARGET)
    with psycopg.connect(database_url, autocommit=True) as connection:
        assert not exports.catalog_ready(connection, namespace)
        asyncio.run(gate.run())
        assert gate.completed
        assert [item["phase"] for item in journal] == ["acknowledged", "injected", "recovered"]
        assert journal[-1]["restart"]["chunks_resumed"] >= 1
        assert exports.catalog_ready(connection, namespace)
        facts = exports.import_resume_facts(connection, namespace, source, out, url=database_url)
    assert facts == {
        "business_digest_equal": True,
        "repeat_import_status": "noop",
        "inactive_with_projection": 0,
    }


def test_fault_child_refuses_without_explicit_enablement(tmp_path, monkeypatch):
    from pipelines.catalog.faults import child

    monkeypatch.delenv("FAULT_INJECTION_ENABLED", raising=False)
    with pytest.raises(SystemExit):
        child(str(tmp_path / "x.csv"), str(tmp_path), "bench-h-x", "copy")
    monkeypatch.setenv("FAULT_INJECTION_ENABLED", "true")
    with pytest.raises(SystemExit):
        child(str(tmp_path / "x.csv"), str(tmp_path), "dev", "copy")


def test_projection_audit_and_facts_reflect_durable_receipts(
    tmp_path, database_url, db, outbox_double
):
    namespace = "bench-h-" + uuid4().hex[:16]
    import_rows(tmp_path, database_url, namespace, [row("A1")])

    def send(version, reserved, offset):
        record = stock_record(CODEC, namespace, "FK-A1", version, 10, reserved, offset=offset)
        return apply_record(db, CODEC, record, quarantine_local_diagnostic)

    send(1, 0, 1)
    send(3, 3, 2)
    send(2, 2, 3)
    send(3, 3, 4)
    send(3, 4, 5)
    with psycopg.connect(database_url, autocommit=True) as connection:
        facts = exports.projection_facts(connection, namespace, "FK-A1")
        audit = exports.projection_audit(connection, namespace)
    assert facts == {"current_version": 3, "stale": 1, "duplicate": 1, "conflict": 1}
    assert audit["stocks"] == [
        {"sku": "FK-A1", "on_hand": 10, "reserved": 3, "available": 7, "stock_version": 3}
    ]
    assert audit["deferred"] == 0 and audit["outcomes"]["applied"] == 2
