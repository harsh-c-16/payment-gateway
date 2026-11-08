"""Small explicit source/Parquet fixtures exercise the independent audit, with no DB."""

import csv
import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from benchmarks.import_audit import audit_import
from projectctl.artifacts import content_hash, file_hash


def audit_fixture(tmp_path, monkeypatch, corruption):
    # This small CSV is an explicit test fixture, never the 20,000-row source profile.
    source = tmp_path / "tiny.csv"
    with source.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=[
                "pid",
                "uniq_id",
                "crawl_timestamp",
                "discounted_price",
            ],
        )
        writer.writeheader()
        writer.writerows(
            [
                {
                    "pid": "A",
                    "uniq_id": "old",
                    "crawl_timestamp": "2016-01-01T00:00:00+00:00",
                    "discounted_price": "10",
                },
                {
                    "pid": "A",
                    "uniq_id": "new",
                    "crawl_timestamp": "2016-02-01T00:00:00+00:00",
                    "discounted_price": "20",
                },
                {
                    "pid": "B",
                    "uniq_id": "missing",
                    "crawl_timestamp": "2016-01-01T00:00:00+00:00",
                    "discounted_price": "",
                },
            ]
        )
    output = tmp_path / "import"
    output.mkdir()
    catalog = [
        {
            "sku": "FK-A",
            "source_pid": "A",
            "source_observation_id": "new",
            "source_row": 2,
            "price_minor": 2000,
            "active": True,
        },
        {
            "sku": "FK-B",
            "source_pid": "B",
            "source_observation_id": "missing",
            "source_row": 3,
            "price_minor": None,
            "active": False,
        },
    ]
    dispositions = [
        {"source_row": 1, "disposition": "superseded"},
        {"source_row": 2, "disposition": "canonical_active"},
        {"source_row": 3, "disposition": "canonical_inactive_missing_price"},
    ]
    if corruption == "price":
        catalog[0]["price_minor"] = 20
    elif corruption == "float_money":
        catalog[0]["price_minor"] = 2000.0
    elif corruption == "integer_active":
        catalog[0]["active"] = 1
        catalog[1]["active"] = 0
    elif corruption == "selection":
        catalog[0].update(source_observation_id="old", source_row=1)
    elif corruption == "inactive":
        catalog[1].update(price_minor=0, active=True)
    elif corruption == "duplicate":
        catalog.append(catalog[0].copy())
    elif corruption == "disposition":
        dispositions[0]["disposition"] = "canonical_active"
    files = {}
    for name, rows in {"catalog": catalog, "dispositions": dispositions}.items():
        path = output / (name + ".parquet")
        pq.write_table(pa.Table.from_pylist(rows), path)
        files[name] = {"path": path.name, "sha256": file_hash(path)}
    normalized = {"files": files, "dataset_revision": "fixture", "rules_version": "flipkart-v1"}
    sku = {
        "namespace": "bench-tiny",
        "dataset_revision": "fixture",
        "sorted_skus": [{"sku": "FK-A"}],
    }
    if corruption == "namespace":
        sku["namespace"] = "another-run"
    for name, document in {"normalized_manifest": normalized, "sku_manifest": sku}.items():
        document["content_sha256"] = content_hash(document)
        (output / (name + ".json")).write_text(json.dumps(document), encoding="utf-8")
    (output / "source_manifest.json").write_text(
        json.dumps({"source_sha256": file_hash(source)}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "benchmarks.import_audit.inspect_source",
        lambda path: {
            "status": "PASS",
            "source_sha256": file_hash(source),
            "observed": {"raw_rows": 3},
        },
    )
    return source, output


@pytest.mark.parametrize(
    "corruption",
    [
        None,
        "price",
        "float_money",
        "integer_active",
        "selection",
        "inactive",
        "duplicate",
        "disposition",
        "namespace",
    ],
)
def test_independent_source_audit_detects_corruption_even_with_valid_file_hashes(
    tmp_path,
    monkeypatch,
    corruption,
):
    source, output = audit_fixture(tmp_path, monkeypatch, corruption)
    result = audit_import(source, output, "bench-tiny", tmp_path)
    assert result["passed"] is (corruption is None)
    assert result["performance"] == "NOT_RUN"
    assert result["independent_facets"] == "NOT_RUN"
    assert (tmp_path / "import_source_audit.json").is_file()


def test_missing_real_source_leaves_audit_incomplete(tmp_path):
    result = audit_import(tmp_path / "missing.csv", tmp_path, "bench-missing", tmp_path)
    assert result["passed"] is None
    assert result["reason"] == "exact source check incomplete"
