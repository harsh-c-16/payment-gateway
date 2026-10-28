import hashlib
import json
from copy import deepcopy

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import ValidationError

from projectctl.artifacts import canonical_json, content_hash, file_hash
from projectctl.cli import main
from projectctl.config import ROOT
from projectctl.schemas import schema_documents


def validator(name):
    path = ROOT / "contracts" / "evaluation" / f"{name}.schema.json"
    return Draft202012Validator(json.loads(path.read_text()), format_checker=FormatChecker())


def test_schemas_are_valid_and_generated_files_are_current():
    for name, expected in schema_documents():
        actual = ROOT / "contracts" / "evaluation" / f"{name}.schema.json"
        assert actual.read_text(encoding="utf-8") == expected
        Draft202012Validator.check_schema(json.loads(expected))


def test_canonical_json_has_fixed_bytes_preserves_arrays_and_unicode():
    assert canonical_json({"z": [2, 1], "a": "₹"}) == '{"a":"₹","z":[2,1]}'.encode()
    assert canonical_json({"b": 2, "a": 1}) == canonical_json({"a": 1, "b": 2})
    assert canonical_json([1, 2]) != canonical_json([2, 1])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), {1: "bad"}])
def test_invalid_json_values_are_rejected(bad):
    with pytest.raises(ValueError):
        canonical_json({"nested": bad})


def test_content_hash_excludes_only_the_root_self_hash():
    assert content_hash({"a": 1}) == content_hash({"a": 1, "content_sha256": "ignored"})
    assert content_hash({"a": 1}) != content_hash({"a": 2})
    assert content_hash({"nested": {"content_sha256": "a"}}) != content_hash(
        {"nested": {"content_sha256": "b"}}
    )


def test_file_hash_covers_exact_bytes(tmp_path):
    path = tmp_path / "raw.csv"
    path.write_bytes(b"a,b\r\n1,2\r\n")
    assert file_hash(path) == hashlib.sha256(b"a,b\r\n1,2\r\n").hexdigest()
    path.write_bytes(b"a,b\n1,2\n")
    assert file_hash(path) != hashlib.sha256(b"a,b\r\n1,2\r\n").hexdigest()


def test_generated_failure_artifacts_validate_and_references_rehash(workspace, capsys):
    assert (
        main(
            [
                "benchmark",
                "run",
                "--workload",
                "W-IMPORT",
                "--variants",
                "I0",
                "--repetitions",
                "1",
                "--config",
                "configs/evaluation.yaml",
            ]
        )
        == 4
    )
    output = json.loads(capsys.readouterr().out)
    directory = workspace / output["evidence_dir"]
    documents = {}
    for schema, filename in [
        ("run", "manifest.json"),
        ("summary", "summary.json"),
        ("config", "resolved_config.json"),
    ]:
        documents[schema] = json.loads((directory / filename).read_text())
        validator(schema).validate(documents[schema])
    manifest = documents["run"]
    assert content_hash(manifest) == manifest["content_sha256"]
    assert manifest["config_sha256"] == content_hash(documents["config"])
    assert manifest["workload_protocol"]["duration_seconds"] is None
    assert manifest["locks"]["application_sha256"] == file_hash(workspace / "uv.lock")
    for ref in manifest["artifacts"]:
        assert file_hash(directory / ref["path"]) == ref["sha256"]
    assert not (directory / "timings.parquet").exists()

    bad = deepcopy(documents["summary"])
    bad["metrics"][0]["value"] = 1234
    with pytest.raises(ValidationError):
        validator("summary").validate(bad)
    bad = deepcopy(documents["summary"])
    bad["metrics"][0]["status"] = "MEASURED"
    with pytest.raises(ValidationError):
        validator("summary").validate(bad)
    bad = deepcopy(manifest)
    bad["created_at"] = "2026-10-24T12:00:00+05:30"
    with pytest.raises(ValidationError):
        validator("run").validate(bad)
    bad = deepcopy(manifest)
    bad["run_id"] = "------------------------------------"
    with pytest.raises(ValidationError):
        validator("run").validate(bad)


def test_fixture_shape_rejects_wrong_field_without_building_p3_fixtures():
    fixture = {
        "schema_version": 1,
        "workload_id": "W-QUALITY",
        "template_version": "schema-test-only",
        "seed": 42,
        "logical_fixture_sha256": "a" * 64,
        "expected_counts": {
            "planned": 2,
            "unique_valid": 1,
            "duplicate_deliveries": 1,
            "invalid": 0,
        },
        "schedule_parameters": {
            "required": True,
            "kind": "finite",
            "rate_per_second": None,
            "record_count": 2,
            "query_count": None,
            "warmups_per_query": None,
            "executions_per_query": None,
            "template_sha256": None,
        },
        "source_manifests": [],
        "content_sha256": None,
    }
    validator("fixture").validate(fixture)
    fixture["expected_count"] = fixture.pop("expected_counts")
    with pytest.raises(ValidationError):
        validator("fixture").validate(fixture)
