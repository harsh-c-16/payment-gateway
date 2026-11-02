"""D-01/D-02 checks of an import. Prices and counts are re-derived without the normalizer."""

import json
from pathlib import Path

import pyarrow.parquet as pq

from benchmarks.dataset_checks import SOURCE_SHA256, inspect_source, price_minor
from pipelines.catalog.artifacts import content_hash, hash_file, write_json
from pipelines.catalog.normalize import ACTIVE, INACTIVE, business_digest

DATA_RAW = Path(__file__).resolve().parents[2] / "data/raw"
# File 08 measured values, valid for this checksum and these rules only.
EXPECTED_COVERAGE = {
    "colour": 10918,
    "material": 10439,
    "size": 4,
    "active_colour": 10890,
    "active_material": 10399,
    "active_size": 4,
    "active_brand": 14072,
    "active_category": 19600,
}


def verify_import(manifest_path, namespace, connection, source_path=None):
    directory = Path(manifest_path).parent
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    source_manifest = json.loads((directory / "source_manifest.json").read_text(encoding="utf-8"))
    sku_manifest = json.loads((directory / "sku_manifest.json").read_text(encoding="utf-8"))
    assertions = []

    def check(name, expected, observed):
        assertions.append(
            {
                "name": name,
                "expected": expected,
                "observed": observed,
                "passed": expected == observed,
            }
        )

    check("manifest_content_hash", manifest["content_sha256"], content_hash(manifest))
    check("sku_manifest_hash", sku_manifest["content_sha256"], content_hash(sku_manifest))
    for name, descriptor in manifest["files"].items():
        check(f"{name}_file_hash", descriptor["sha256"], hash_file(directory / descriptor["path"]))
    catalog = pq.read_table(directory / manifest["files"]["catalog"]["path"]).to_pylist()
    observations = pq.read_table(directory / manifest["files"]["observations"]["path"]).to_pylist()
    dispositions = pq.read_table(directory / manifest["files"]["dispositions"]["path"]).to_pylist()
    by_row = {row["source_row"]: row for row in observations}
    counts = {}
    for row in dispositions:
        counts[row["disposition"]] = counts.get(row["disposition"], 0) + 1
    check("disposition_exclusive", len(by_row), len(dispositions))
    check(
        "disposition_conservation",
        manifest["raw_rows"],
        manifest["canonical_rows"] + manifest["superseded_rows"] + manifest["rejected_rows"],
    )
    check("canonical_unique_sku", len(catalog), len({row["sku"] for row in catalog}))
    selected = {
        row["source_row"] for row in dispositions if row["disposition"] in (ACTIVE, INACTIVE)
    }
    check(
        "canonical_rows_are_selected_rows",
        True,
        selected == {row["source_row"] for row in catalog},
    )
    price_errors, lineage_errors = 0, 0
    for row in catalog:
        raw = by_row[row["source_row"]]
        if (raw["uniq_id"], raw["pid"]) != (row["source_observation_id"], row["source_pid"]):
            lineage_errors += 1
        expected_price = price_minor(raw["discounted_price"])
        if row["price_minor"] != expected_price or row["active"] != (expected_price is not None):
            price_errors += 1
    check("independent_price_and_activity_errors", 0, price_errors)
    check("lineage_errors", 0, lineage_errors)
    check(
        "business_digest_from_parquet",
        manifest["canonical_business_digest"],
        business_digest([[row["sku"], row["normalized_business_hash"]] for row in catalog]),
    )
    database_rows = connection.execute(
        "SELECT sku,normalized_business_hash FROM products "
        "WHERE namespace=%s AND dataset_revision=%s",
        (namespace, manifest["dataset_revision"]),
    ).fetchall()
    check(
        "business_digest_from_database",
        manifest["canonical_business_digest"],
        business_digest([list(row) for row in database_rows]),
    )
    status = connection.execute(
        "SELECT status FROM catalog_imports WHERE namespace=%s AND source_hash=%s",
        (namespace, source_manifest["source_sha256"]),
    ).fetchone()
    check("import_complete", "complete", status[0] if status else None)
    skus = [entry["sku"] for entry in sku_manifest["sorted_skus"]]
    check("sku_manifest_sorted", True, sorted(skus) == skus)
    check(
        "sku_manifest_only_active", True, sorted(r["sku"] for r in catalog if r["active"]) == skus
    )
    report = {
        "source_sha256": source_manifest["source_sha256"],
        "dictionary_sha256": manifest["dictionary_sha256"],
        "rules_version": manifest["rules_version"],
        "dataset_revision": manifest["dataset_revision"],
        "observed": counts,
        "assertions": assertions,
        "provider_normalization_comparison": "NOT_RUN",
        "facet_coverage_verification": "NOT_RUN",
    }
    if source_manifest["source_sha256"] == SOURCE_SHA256:
        independent = inspect_source(
            Path(source_path) if source_path else DATA_RAW / source_manifest["source_path"]
        )
        if independent["status"] == "PASS":
            wanted = independent["observed"]
            mapping = {
                "canonical_rows": manifest["canonical_rows"],
                "canonical_active": manifest["active_rows"],
                "canonical_inactive_missing_price": manifest["inactive_rows"],
                "superseded": manifest["superseded_rows"],
                "rejected_mandatory": manifest["rejected_rows"],
                "raw_rows": manifest["raw_rows"],
            }
            comparison = all(wanted[key] == value for key, value in mapping.items())
            check("independent_source_counts", True, comparison)
            report["provider_normalization_comparison"] = "PASS" if comparison else "FAIL"
            profile = json.loads((directory / "profile.json").read_text(encoding="utf-8"))
            coverage = {key: profile["facet_coverage"][key] for key in EXPECTED_COVERAGE}
            check("facet_coverage", EXPECTED_COVERAGE, coverage)
            report["facet_coverage_verification"] = (
                "PASS" if coverage == EXPECTED_COVERAGE else "FAIL"
            )
    write_json(directory / "dataset_checks.json", report)
    return report
