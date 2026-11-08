"""Read-only W-IMPORT reconciliation against the original CSV.

No production normalizer, reducer, business hash implementation or database writes.
This audit covers source selection, money, identity, activity and disposition;
full independent facet normalization remains a separate D-02 handoff.
"""

import csv
import json
from collections import Counter
from datetime import datetime

import pyarrow.parquet as pq

from benchmarks.dataset_checks import inspect_source, price_minor
from projectctl.artifacts import content_hash, file_hash, write_json


def audit_import(source, output, namespace, evidence):
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

    profile = inspect_source(source)
    if profile["status"] != "PASS":
        return {"passed": None, "test_mode": "real", "reason": "exact source check incomplete"}
    manifest = json.loads((output / "normalized_manifest.json").read_text("utf-8"))
    sku_manifest = json.loads((output / "sku_manifest.json").read_text("utf-8"))
    source_manifest = json.loads((output / "source_manifest.json").read_text("utf-8"))
    check("source_sha256", profile["source_sha256"], source_manifest["source_sha256"])
    check("normalized_content_hash", content_hash(manifest), manifest["content_sha256"])
    check("sku_content_hash", content_hash(sku_manifest), sku_manifest["content_sha256"])
    check("namespace", namespace, sku_manifest["namespace"])
    check("dataset_revision", manifest["dataset_revision"], sku_manifest["dataset_revision"])
    check("rules", "flipkart-v1", manifest["rules_version"])
    for name, descriptor in manifest["files"].items():
        path = (output / descriptor["path"]).resolve()
        if not path.is_relative_to(output.resolve()):
            raise ValueError("import descriptor escaped its output directory")
        check(name + "_file_hash", descriptor["sha256"], file_hash(path))
    # Read expected inputs directly, before consulting provider output values.
    expected, physical = {}, {}
    with source.open(encoding="utf-8", newline="") as stream:
        for index, row in enumerate(csv.DictReader(stream), 1):
            physical[index] = row
            rank = (datetime.fromisoformat(row["crawl_timestamp"]), row["uniq_id"])
            previous = expected.get(row["pid"])
            if previous is None or rank > previous[0]:
                expected[row["pid"]] = (rank, index, row)
    wanted = {}
    expected_dispositions = {}
    for _, index, row in expected.values():
        sale = price_minor(row["discounted_price"])
        wanted["FK-" + row["pid"]] = (
            row["pid"],
            row["uniq_id"],
            index,
            sale,
            sale is not None,
        )
        expected_dispositions[index] = (
            "canonical_active" if sale is not None else "canonical_inactive_missing_price"
        )
    for index in physical:
        expected_dispositions.setdefault(index, "superseded")
    catalog = pq.read_table(output / manifest["files"]["catalog"]["path"]).to_pylist()
    check(
        "integer_minor_units_and_boolean_activity",
        True,
        all(
            (row["price_minor"] is None or type(row["price_minor"]) is int)
            and type(row["active"]) is bool
            and type(row["source_row"]) is int
            for row in catalog
        ),
    )
    observed = {
        row["sku"]: (
            row["source_pid"],
            row["source_observation_id"],
            row["source_row"],
            row["price_minor"],
            row["active"],
        )
        for row in catalog
    }
    check("unique_canonical_skus", len(catalog), len(observed))
    check("canonical_row_count", len(wanted), len(catalog))
    check("independent_source_selection_price_activity", True, wanted == observed)
    dispositions = pq.read_table(output / manifest["files"]["dispositions"]["path"]).to_pylist()
    actual_dispositions = {row["source_row"]: row["disposition"] for row in dispositions}
    check("unique_dispositions", len(dispositions), len(actual_dispositions))
    check("independent_all_source_dispositions", True, expected_dispositions == actual_dispositions)
    counts = dict(Counter(actual_dispositions.values()))
    check("physical_record_count", profile["observed"]["raw_rows"], len(dispositions))
    wanted_skus = sorted(sku for sku, values in wanted.items() if values[-1])
    check(
        "active_sku_manifest", wanted_skus, [entry["sku"] for entry in sku_manifest["sorted_skus"]]
    )
    # Large ID arrays stay in their source artifacts; the verdict carries bounded checks.
    assertions[-1]["expected"] = {"count": len(wanted_skus)}
    assertions[-1]["observed"] = {"count": len(sku_manifest["sorted_skus"])}
    result = {
        "passed": all(item["passed"] for item in assertions),
        "test_mode": "real",
        "namespace": namespace,
        "assertions": assertions,
        "source_dispositions": counts,
        "source_sha256": profile["source_sha256"],
        "scope": "independent source selection, identity, money, activity, dispositions and hashes",
        "independent_facets": "NOT_RUN",
        "performance": "NOT_RUN",
    }
    write_json(evidence / "import_source_audit.json", result)
    return result
