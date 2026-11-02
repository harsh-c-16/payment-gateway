"""Owner audit exports for Jaineel's D-01, D-02, D-03 and T-09 case bindings.

These collect observations only. The harness compares them with its own frozen checks; nothing
here decides whether a case passed.
"""

import hashlib
import json
import random
from pathlib import Path

from pipelines.catalog.adapter import run_import
from pipelines.catalog.normalize import (
    ACTIVE,
    INACTIVE,
    REJECTED,
    SUPERSEDED,
    load_dictionary,
    normalize_catalog_row,
    read_source,
    select_latest_listings,
)

ROOT = Path(__file__).resolve().parents[2]
DIRTY_FIXTURE = ROOT / "contracts/fixtures/catalog/dirty_catalogue.json"
# Asserted against live PostgreSQL by a repeat import, not by the pure rules.
LIVE_ONLY_FIELDS = {
    "catalog_version_after_first",
    "catalog_version_after_repeat",
    "second_import_business_change_count",
}


def dirty_case_failures(case, dictionary):
    """Names of the expectations one independent dirty row case does not meet."""
    observations = [
        normalize_catalog_row(raw, number, dictionary)
        for number, raw in enumerate(case["input_rows"], 1)
    ]
    selection = select_latest_listings(observations)
    expected, failures = case["expected"], []

    def check(name, passed):
        if not passed:
            failures.append(name)

    check(
        "dispositions",
        [selection.dispositions[item.row_number] for item in observations]
        == expected["dispositions"],
    )
    check(
        "selected_source_ids",
        [item.uniq_id for item in selection.canonical] == expected["selected_source_ids"],
    )
    bound = [item.row_number for item in observations if item.bound_exceeded]
    failure = expected["import_failure"]
    check(
        "import_failure",
        bound[:1] == [failure["source_row_number"]] if failure else not bound,
    )
    wanted = dict(expected["normalized_fields"])
    issues = {code for item in observations for code in item.issues}
    check("issue_codes", set(wanted.pop("issue_codes", [])) <= issues)
    listing_count = wanted.pop("listing_count", None)
    if listing_count is not None:
        check("listing_count", len(selection.canonical) == listing_count)
    record_number = wanted.pop("source_logical_record_number", None)
    filters = wanted.pop("hard_filter_matches", {})
    attributes = wanted.pop("attributes", {})
    if not selection.canonical:
        check("nothing_to_compare", not wanted and not filters and not attributes)
        return failures
    fields = selection.canonical[0].fields
    if record_number is not None:
        check("source_logical_record_number", fields["source_row_number"] == record_number)
    for name, value in attributes.items():
        check(f"attributes.{name}", fields["attributes"].get(name) == value)
    for name, value in filters.items():
        facet, requested = name.split("=")
        check(f"hard_filter.{name}", (fields[facet] == requested) is value)
    for name, value in wanted.items():
        if name not in LIVE_ONLY_FIELDS:
            check(name, fields.get(name) == value)
    return failures


def d01_facts(source):
    dictionary = load_dictionary()
    uniq_ids, pids, rows, missing_both = set(), set(), 0, 0
    for _, raw in read_source(source, dictionary):
        rows += 1
        uniq_ids.add(raw["uniq_id"])
        pids.add(raw["pid"])
        missing_both += not raw["discounted_price"].strip() and not raw["retail_price"].strip()
    return {
        "source_rows": rows,
        "columns": len(dictionary["source_header"]),
        "unique_observations": len(uniq_ids),
        "unique_pid": len(pids),
        "missing_both_prices": missing_both,
    }


def d02_facts(source, *, dirty_fixture=DIRTY_FIXTURE, seed=42):
    dictionary = load_dictionary()
    rows = [(number, raw) for number, raw in read_source(source, dictionary)]
    observations = [normalize_catalog_row(raw, number, dictionary) for number, raw in rows]
    selection = select_latest_listings(observations)
    shuffled = rows[:]
    random.Random(seed).shuffle(shuffled)
    reordered = select_latest_listings(
        [normalize_catalog_row(raw, number, dictionary) for number, raw in shuffled]
    )
    counts = {}
    for disposition in selection.dispositions.values():
        counts[disposition] = counts.get(disposition, 0) + 1
    cases = json.loads(Path(dirty_fixture).read_text(encoding="utf-8"))["cases"]
    failures = sum(
        bool(dirty_case_failures(case, dictionary)) for case in cases if "input_rows" in case
    )
    return {
        "active": counts.get(ACTIVE, 0),
        "inactive": counts.get(INACTIVE, 0),
        "superseded": counts.get(SUPERSEDED, 0),
        "rejected": counts.get(REJECTED, 0),
        "canonical": len(selection.canonical),
        "unknown_categories": sum(i.fields["category"] is None for i in selection.canonical),
        "usable_sizes": sum(i.fields["size"] is not None for i in selection.canonical),
        "dirty_fixture_failures": failures,
        "shuffled_digest_equal": reordered.digest == selection.digest,
    }


def business_digest(connection, namespace):
    """Digest over SKU, business hash and version; volatile import times stay out."""
    rows = connection.execute(
        "SELECT sku,normalized_business_hash,catalog_version FROM products "
        "WHERE namespace=%s ORDER BY sku",
        (namespace,),
    ).fetchall()
    return hashlib.sha256(json.dumps([list(row) for row in rows]).encode()).hexdigest()


def catalog_ready(connection, namespace):
    row = connection.execute(
        "SELECT count(*) FROM catalog_imports WHERE namespace=%s AND status='complete'",
        (namespace,),
    ).fetchone()
    return row[0] > 0


def import_resume_facts(connection, namespace, source, out, *, url=None):
    """After a fault-gated resume: import again and report what a repeat changed.

    second_seed_new_effects belongs to Aditya's seed export and is not reported here.
    """
    before = business_digest(connection, namespace)
    report, _ = run_import(source, load_mode="copy", namespace=namespace, out=out, url=url)
    inactive_listed = connection.execute(
        "SELECT count(*) FROM products p JOIN stock_projection s USING (namespace,sku) "
        "WHERE p.namespace=%s AND NOT p.active",
        (namespace,),
    ).fetchone()[0]
    return {
        "business_digest_equal": before == business_digest(connection, namespace),
        "repeat_import_status": report.status,
        "inactive_with_projection": inactive_listed,
    }


def projection_audit(connection, namespace):
    """Read-only projection snapshot, compared with Inventory by the independent oracle."""
    stocks = connection.execute(
        "SELECT sku,on_hand,reserved,available,stock_version FROM stock_projection "
        "WHERE namespace=%s ORDER BY sku",
        (namespace,),
    ).fetchall()
    outcomes = connection.execute(
        "SELECT outcome,count(*) FROM projection_receipts WHERE namespace=%s GROUP BY outcome",
        (namespace,),
    ).fetchall()
    deferred = connection.execute(
        "SELECT count(*) FROM stock_deferred WHERE namespace=%s", (namespace,)
    ).fetchone()[0]
    columns = ("sku", "on_hand", "reserved", "available", "stock_version")
    return {
        "stocks": [dict(zip(columns, row, strict=True)) for row in stocks],
        "outcomes": dict(outcomes),
        "deferred": deferred,
    }


def projection_facts(connection, namespace, sku):
    """The T-09 version counts for one SKU, from durable receipts."""
    current = connection.execute(
        "SELECT stock_version FROM stock_projection WHERE namespace=%s AND sku=%s",
        (namespace, sku),
    ).fetchone()
    outcomes = dict(
        connection.execute(
            "SELECT outcome,count(*) FROM projection_receipts WHERE namespace=%s AND sku=%s "
            "GROUP BY outcome",
            (namespace, sku),
        ).fetchall()
    )
    return {
        "current_version": current[0] if current else None,
        "stale": outcomes.get("stale", 0),
        "duplicate": outcomes.get("duplicate", 0),
        "conflict": outcomes.get("conflict", 0),
    }
