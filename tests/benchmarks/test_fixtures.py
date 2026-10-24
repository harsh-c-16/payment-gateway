import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

import pytest

from benchmarks.fixtures import FIXTURE_PATHS, build_bundle, validate_assistant_fixture
from benchmarks.quality import quality_expectations
from projectctl.artifacts import canonical_json, content_hash, file_hash
from projectctl.config import load_config
from projectctl.models import FixtureManifest
from tests.oracles.draft_fixtures import assistant_scenarios, dirty_catalogue

ROOT = Path(__file__).resolve().parents[2]


def test_quality_has_exact_independent_ids_dispositions_and_subcases():
    originals, duplicate_targets, counts, subcases = {}, set(), Counter(), Counter()
    source_ids = set()
    for row in quality_expectations(42):
        assert row["logical_record_id"] not in source_ids
        source_ids.add(row["logical_record_id"])
        counts[row["expected_disposition"]] += 1
        if row["expected_disposition"] == "new_valid":
            assert row["logical_event_id"] not in originals
            originals[row["logical_event_id"]] = (
                row["record_ordinal"],
                row["logical_content_sha256"],
            )
        elif row["expected_disposition"] == "duplicate_delivery":
            ordinal, digest = originals[row["logical_event_id"]]
            assert row["duplicate_of"] == ordinal < row["record_ordinal"]
            assert row["logical_content_sha256"] == digest
            duplicate_targets.add(ordinal)
        else:
            subcases[row["invalid_subcase"]] += 1
    assert len(source_ids) == 100000 and len(originals) == 98500 and len(duplicate_targets) == 1000
    assert counts == {"new_valid": 98500, "duplicate_delivery": 1000, "invalid": 500}
    assert len(subcases) == 10 and set(subcases.values()) == {50}


def logical_hash(seed):
    digest = hashlib.sha256()
    for row in quality_expectations(seed):
        digest.update(canonical_json(row))
    return digest.hexdigest()


def test_quality_logical_hash_is_reproducible_and_seed_changes_duplicates():
    assert logical_hash(42) == logical_hash(42)
    assert logical_hash(42) != logical_hash(43)


def test_sixty_draft_labels_keep_review_and_source_limitations_visible():
    document = json.loads((ROOT / FIXTURE_PATHS[1]).read_text(encoding="utf-8"))
    assert document == assistant_scenarios()
    counts = validate_assistant_fixture(document)
    assert all(count >= 10 for count in counts.values())
    assert len({row["group"] for row in document["scenarios"]}) == 7
    assert document["quality_evaluation"] == "NOT_RUN"
    assert all(
        row["catalogue_binding"] is None and row["relevance_labels"] is None
        for row in document["scenarios"]
    )


def test_dirty_fixtures_are_authored_expectations_not_production_outputs():
    document = json.loads((ROOT / FIXTURE_PATHS[0]).read_text(encoding="utf-8"))
    assert document == dirty_catalogue()
    cases = {row["case_id"] for row in document["cases"]}
    assert len(cases) == len(document["cases"])
    assert {
        "ordinary-price",
        "retail-is-not-sale-fallback",
        "duplicate-pid-latest",
        "equal-time-conflict",
        "absent-size-colour-material",
        "quoted-nil-arrow",
        "malformed-csv-width",
        "cell-bound",
        "price-only-update",
    } <= cases


def test_fixture_build_persists_hashes_and_cannot_overwrite(tmp_path):
    for relative in FIXTURE_PATHS:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    config = load_config("configs/evaluation.yaml")
    target = tmp_path / "artifacts/fixture-test"
    index = build_bundle(tmp_path, target, config, 42)
    assert index["content_sha256"] == content_hash(index)
    assert (
        index["dataset_checks_status"] == "NOT_RUN"
    )  # No implicit substitute CSV in tmp workspace.
    for artifact in index["artifacts"]:
        assert file_hash(tmp_path / artifact["path"]) == artifact["sha256"]
    manifest = json.loads((target / "w_quality_manifest.json").read_text())
    FixtureManifest.model_validate(manifest)
    assert manifest["logical_fixture_sha256"] == file_hash(target / "w_quality_expectations.jsonl")
    assert manifest["content_sha256"] == content_hash(manifest)
    assert manifest["expected_counts"]["planned"] == 100000
    assert (
        json.loads((target / "quality_recipe.json").read_text())["wire_materialization"]
        == "NOT_RUN"
    )
    before = (target / "fixture_index.json").read_bytes()
    with pytest.raises(FileExistsError):
        build_bundle(tmp_path, target, config, 42)
    assert (target / "fixture_index.json").read_bytes() == before
