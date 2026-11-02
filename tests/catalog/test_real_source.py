"""D-01/D-02 against the exact uploaded CSV, compared with Jaineel's independent reader."""

import hashlib
from collections import Counter

from benchmarks.dataset_checks import EXPECTED, EXPECTED_SELECTED, SOURCE_SHA256, inspect_source
from pipelines.catalog.normalize import (
    load_dictionary,
    normalize_catalog_row,
    profile_catalog,
    read_source,
    select_latest_listings,
)


def test_full_file_profile_matches_file_08_and_independent_counts(source_csv):
    assert hashlib.sha256(source_csv.read_bytes()).hexdigest() == SOURCE_SHA256
    dictionary = load_dictionary()
    rows, observations = [], []
    for number, raw in read_source(source_csv, dictionary):
        rows.append(raw)
        observations.append(normalize_catalog_row(raw, number, dictionary))
    selection = select_latest_listings(observations)
    profile = profile_catalog(rows, selection, observations, SOURCE_SHA256)
    independent = inspect_source(source_csv)
    assert independent["status"] == "PASS"
    selected = profile["selected_counts"]
    assert selected["canonical_active"] == EXPECTED["canonical_active"] == 19920
    assert selected["canonical_inactive_missing_price"] == 78
    assert selected["superseded"] == 2
    assert "rejected_mandatory" not in selected
    assert len(selection.canonical) == EXPECTED["canonical_rows"]
    assert profile["nested_shape_counts"] == {
        "spec_list": 19900,
        "spec_singleton": 33,
        "spec_nil": 53,
        "spec_blank": 14,
    }
    assert profile["identity_counts"] == {"unique_uniq_id": 20000, "unique_pid": 19998}
    assert profile["category_counts"]["unclassified"] == 323
    for root, count in {
        "clothing": 6197,
        "jewellery": 3531,
        "footwear": 1227,
        "mobiles_accessories": 1099,
        "automotive": 1012,
    }.items():
        assert profile["category_counts"][root] == count
    coverage = profile["facet_coverage"]
    assert (coverage["colour"], coverage["material"], coverage["size"]) == (10918, 10439, 4)
    assert (coverage["active_colour"], coverage["active_material"]) == (10890, 10399)
    assert (coverage["active_brand"], coverage["active_category"]) == (14072, 19600)
    assert coverage["active_size"] == 4
    issues = profile["issue_counts"]
    assert issues["SPEC_UNKEYED"] == 11920
    assert issues["SPEC_VALUE_MISSING"] == 1
    assert sum("SPEC_UNKEYED" in o.issues for o in observations) == 7961
    repeated = [
        o
        for o in observations
        if any(len(values) > 1 for values in o.fields["attributes"].values())
    ]
    assert len(repeated) == 41
    assert sum(any(len(set(v)) > 1 for v in o.fields["attributes"].values()) for o in repeated) == 6
    for pid, wanted in EXPECTED_SELECTED.items():
        winner = next(i for i in selection.canonical if i.pid == pid)
        assert (winner.row_number, winner.uniq_id) == (wanted["row_number"], wanted["uniq_id"])
        for superseded in wanted["superseded_rows"]:
            assert selection.dispositions[superseded] == "superseded"


def test_no_price_or_size_is_invented(source_csv):
    dictionary = load_dictionary()
    observations = [
        normalize_catalog_row(raw, number, dictionary)
        for number, raw in read_source(source_csv, dictionary)
    ]
    selection = select_latest_listings(observations)
    inactive = [i for i in selection.canonical if not i.fields["active"]]
    assert len(inactive) == 78
    assert all(i.fields["price_minor"] is None for i in inactive)
    assert all(i.fields["inactive_reason"] == "MISSING_PRICE" for i in inactive)
    sizes = Counter(i.fields["size"] for i in selection.canonical if i.fields["size"])
    assert sum(sizes.values()) == 4
    assert all(i.fields["category"] == "clothing" for i in selection.canonical if i.fields["size"])
    assert all(i.fields["seller_id"] is None for i in selection.canonical)
