"""Build immutable offline P3 expectation bundles, with no SUT/model execution."""

import hashlib
import json
from collections import Counter
from pathlib import Path

from benchmarks.dataset_checks import inspect_source
from benchmarks.metrics import SLOTS
from benchmarks.quality import SUBCASES, quality_expectations
from projectctl.artifacts import canonical_json, content_hash, file_hash
from projectctl.models import ExpectedCounts, FixtureManifest

FIXTURE_PATHS = (
    "contracts/fixtures/catalog/dirty_catalogue.json",
    "contracts/fixtures/assistant/scenarios.json",
    "contracts/fixtures/quality/adversarial.json",
)


def validate_assistant_fixture(document):
    scenarios = document["scenarios"]
    if len(scenarios) != 60 or len({row["scenario_id"] for row in scenarios}) != 60:
        raise ValueError("assistant fixture must contain 60 unique scenarios")
    counts = Counter()
    for row in scenarios:
        if set(row["intent_labels"]) != set(SLOTS):
            raise ValueError("every scenario must preserve the original six labels")
        counts.update(slot for slot in SLOTS if row["intent_labels"][slot] is not None)
        if row["generative_call_budget"]["fixed"] != 0 or row["generative_call_budget"][
            "assist"
        ] not in {0, 1}:
            raise ValueError("scenario violates fixed/assist call budget")
        if row["control"] != "search" and row["generative_call_budget"]["assist"] != 0:
            raise ValueError("purchase/status controls must make zero generative calls")
        if (
            row["review_status"] != "awaiting_human_review"
            or row["reviewer"] is not None
            or row["reviewed_at"] is not None
        ):
            raise ValueError("draft fixture cannot claim human review")
        if row["relevance_labels"] is not None:
            raise ValueError("no generated relevance ground truth is allowed")
    if any(counts[slot] < 10 for slot in SLOTS):
        raise ValueError("at least ten positive labels per original slot required")
    if document["frozen"] or document["review_status"] != "awaiting_human_review":
        raise ValueError("draft labels must remain unfrozen pending human review")
    return dict(counts)


def write_json(path, document):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(document, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def build_bundle(root: Path, target: Path, config, seed):
    documents = {
        path: json.loads((root / path).read_text(encoding="utf-8")) for path in FIXTURE_PATHS
    }
    positives = validate_assistant_fixture(documents[FIXTURE_PATHS[1]])
    # Exclusive creation preserves prior evidence and refuses accidental overwrite.
    target.mkdir(parents=True, exist_ok=False)
    artifacts = []
    for relative, document in documents.items():
        output = target / Path(relative).name
        write_json(output, document)
        artifacts.append({"path": output.relative_to(root).as_posix(), "sha256": file_hash(output)})
    counts, subcases = Counter(), Counter()
    digest = hashlib.sha256()
    logical = target / "w_quality_expectations.jsonl"
    with logical.open("xb") as stream:
        for record in quality_expectations(seed):
            encoded = canonical_json(record) + b"\n"
            stream.write(encoded)
            digest.update(encoded)
            counts[record["expected_disposition"]] += 1
            if record["invalid_subcase"]:
                subcases[record["invalid_subcase"]] += 1
    if counts != {"new_valid": 98500, "duplicate_delivery": 1000, "invalid": 500}:
        raise ValueError("W-QUALITY conservation failed")
    logical_sha = digest.hexdigest()
    references = [{"path": path, "sha256": file_hash(root / path)} for path in FIXTURE_PATHS]
    manifest = FixtureManifest(
        schema_version=1,
        workload_id="W-QUALITY",
        template_version="w-quality-logical-v1",
        seed=seed,
        logical_fixture_sha256=logical_sha,
        expected_counts=ExpectedCounts(
            planned=100000, unique_valid=98500, duplicate_deliveries=1000, invalid=500
        ),
        schedule_parameters=config.workloads["W-QUALITY"].model_copy(
            update={"template_sha256": logical_sha}
        ),
        source_manifests=references,
        content_sha256=None,
    )
    manifest.content_sha256 = content_hash(manifest.model_dump())
    write_json(target / "w_quality_manifest.json", manifest.model_dump())
    recipe = {
        "schema_version": 1,
        "seed": seed,
        "test_mode": "offline",
        "purpose": "logical expectations only; not canonical event DTOs",
        "counts": dict(counts),
        "invalid_subcases": [
            {"name": subcase, "count": subcases[subcase], "reason_code": reason}
            for subcase, reason in SUBCASES
        ],
        "identity_conflicts": "separate adversarial.json; excluded from 100000 records",
        "wire_materialization": "NOT_RUN",
        "runtime_event_ids_and_sku_mapping": "NOT_RUN",
        "kafka_execution": "NOT_RUN",
    }
    write_json(target / "quality_recipe.json", recipe)
    source = Path(config.dataset.source_path)
    if source.is_absolute() or not (root / source).resolve().is_relative_to(root.resolve()):
        raise ValueError("source path must remain within the workspace")
    dataset_checks = inspect_source(root / source)
    write_json(target / "dataset_checks.json", dataset_checks)
    for name in (
        "w_quality_expectations.jsonl",
        "w_quality_manifest.json",
        "quality_recipe.json",
        "dataset_checks.json",
    ):
        artifacts.append(
            {
                "path": (target / name).relative_to(root).as_posix(),
                "sha256": file_hash(target / name),
            }
        )
    index = {
        "schema_version": 1,
        "test_mode": "offline",
        "seed": seed,
        "artifacts": artifacts,
        "assistant_scenario_count": 60,
        "assistant_positive_labels": positives,
        "label_review": "awaiting_human_review",
        "assistant_quality": "NOT_RUN",
        "real_provider_integration": "NOT_RUN",
        "performance": "NOT_RUN",
        "dataset_checks_status": dataset_checks["status"],
        "content_sha256": None,
    }
    index["content_sha256"] = content_hash(index)
    write_json(target / "fixture_index.json", index)
    return index
