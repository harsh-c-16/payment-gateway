"""Frozen W-ANALYTICS layouts and their audit, over Vichitr's real publisher and FileStore."""

import asyncio
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from analytics.queries import fixture
from analytics.queries.layouts import freeze, load_frozen, verify_files
from analytics.queries.suite import LAYOUT_FOR_PARAMETERS, QUERIES, runner_query_adapter
from pipelines.catalog.runtime import CatalogRuntime


@pytest.fixture
def frozen(pipeline, tmp_path, monkeypatch):
    fixture.build(
        pipeline, pipeline.test_namespace, publications=3, events_per_publication=40, days=3
    )
    day = (datetime.now(UTC) - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    document = freeze(pipeline, pipeline.test_namespace, day, pipeline.test_root)
    path = tmp_path / "frozen_layouts.json"
    path.write_text(json.dumps(document))
    monkeypatch.setenv("LAKEHOUSE_ROOT", str(pipeline.test_root))
    monkeypatch.setenv("ANALYTICS_FROZEN_LAYOUTS", str(path))
    monkeypatch.delenv("CATALOG_BINDING_REVIEW_PATH", raising=False)
    return path, document


def test_freeze_pins_generations_day_and_identical_results(frozen):
    path, document = frozen
    assert set(document["expected_digests"]) == set(QUERIES)
    assert all(
        document["generations_after"][d] > document["generations_before"][d]
        for d in ("silver", "gold")
    )
    loaded = load_frozen(path)
    assert loaded.query_day.isoformat().startswith(document["query_day"])
    for name in loaded.layouts:
        assert verify_files(loaded, name) == []


def emissions(directory, document, parameters):
    loaded = load_frozen(directory.parent / "frozen_layouts.json")
    adapter = runner_query_adapter(loaded.layout_for, document["store_root"], loaded.query_day)
    with (directory / "emissions.jsonl").open("w", encoding="utf-8") as stream:
        for query_id in QUERIES:
            details = asyncio.run(adapter({"query_id": query_id}, {"parameters": parameters}))
            row = {"payload": {"query_id": query_id}, "outcome": "acknowledged", "details": details}
            stream.write(json.dumps(row) + "\n")


@contextmanager
def no_database(variable):
    raise AssertionError("the analytics audit must not read a database")
    yield


@pytest.mark.parametrize(("file_layout", "partitioning"), sorted(LAYOUT_FOR_PARAMETERS))
def test_analytics_audit_passes_on_every_frozen_layout(frozen, tmp_path, file_layout, partitioning):
    _, document = frozen
    parameters = {"file_layout": file_layout, "partitioning": partitioning}
    run = tmp_path / "run"
    run.mkdir()
    emissions(run, document, parameters)
    context = {"namespace": "bench-h-" + uuid4().hex[:12], "parameters": parameters}
    verdict = asyncio.run(CatalogRuntime(read=no_database).analytics_audit(context, run))
    assert verdict["passed"] is True, verdict["mismatched_paths"]
    assert (run / "query_results.parquet").stat().st_size


def test_analytics_audit_detects_a_changed_file(frozen, tmp_path):
    path, document = frozen
    parameters = {"file_layout": "compact", "partitioning": "date_type"}
    run = tmp_path / "run"
    run.mkdir()
    emissions(run, document, parameters)
    victim = load_frozen(path).layouts["compacted"].files[0]
    target = load_frozen(path).document["store_root"] + "/" + victim.path
    with open(target, "ab") as stream:
        stream.write(b"x")
    context = {"namespace": "bench-h-" + uuid4().hex[:12], "parameters": parameters}
    verdict = asyncio.run(CatalogRuntime(read=no_database).analytics_audit(context, run))
    assert verdict["passed"] is None and verdict["collection_complete"] is False
