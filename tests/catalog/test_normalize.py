"""D-02 pure rules: Jaineel's independent dirty fixture plus parser and money edge cases."""

import json
import random
from pathlib import Path

import pytest

from pipelines.catalog.exports import dirty_case_failures
from pipelines.catalog.normalize import (
    CsvStructureError,
    load_dictionary,
    normalize_catalog_row,
    parse_money,
    parse_specifications,
    read_source,
    root_slug,
    ruby_to_json,
    select_latest_listings,
)
from tests.catalog.helpers import row, spec, write_csv

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = json.loads(
    (ROOT / "contracts/fixtures/catalog/dirty_catalogue.json").read_text(encoding="utf-8")
)
DICTIONARY = load_dictionary()
ROW_CASES = [case for case in FIXTURE["cases"] if "input_rows" in case]


def run(rows):
    observations = [
        normalize_catalog_row(raw, number, DICTIONARY) for number, raw in enumerate(rows, 1)
    ]
    return observations, select_latest_listings(observations)


@pytest.mark.parametrize("case", ROW_CASES, ids=lambda case: case["case_id"])
def test_independent_dirty_fixture(case):
    assert dirty_case_failures(case, DICTIONARY) == []


def test_malformed_width_fails_whole_import_before_any_row(tmp_path):
    case = next(c for c in FIXTURE["cases"] if c["case_id"] == "malformed-csv-width")
    path = tmp_path / "bad.csv"
    path.write_text(case["input_csv"], encoding="utf-8")
    with pytest.raises(CsvStructureError, match="CSV_STRUCTURE_ERROR"):
        list(read_source(path, DICTIONARY))


def test_short_data_row_is_a_structure_failure(tmp_path):
    path = write_csv(tmp_path / "ok.csv", [row("A1")])
    path.write_text(path.read_text(encoding="utf-8") + "only,two\n", encoding="utf-8")
    with pytest.raises(CsvStructureError, match="record 2"):
        list(read_source(path, DICTIONARY))


def test_logical_record_numbers_survive_quoted_newlines(tmp_path):
    path = write_csv(tmp_path / "ok.csv", [row("A1", description="two\nlines"), row("A2")])
    assert [number for number, _ in read_source(path, DICTIONARY)] == [1, 2]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("379", (37900, False)),
        ("1.25", (125, False)),
        ("0.01", (1, False)),
        ("", (None, False)),
        ("  ", (None, False)),
        ("10000000", (1000000000, False)),
        ("10000000.01", (None, True)),
        ("0", (None, True)),
        ("-1", (None, True)),
        ("1.001", (None, True)),
        ("nan", (None, True)),
        ("inf", (None, True)),
        ("abc", (None, True)),
    ],
)
def test_money_is_exact_and_never_imputed(text, expected):
    assert parse_money(text, 1_000_000_000) == expected


def test_ruby_conversion_only_touches_tokens_outside_strings():
    text = '{"a"=>nil, "b"=>"x => nil \\" y"}'
    assert json.loads(ruby_to_json(text)) == {"a": None, "b": 'x => nil " y'}


@pytest.mark.parametrize(
    "cell",
    [
        '__import__("os").system("x")',
        '{"product_specification"=>"text"}',
        '{"other"=>[]}',
        '{"product_specification"=>[{"key"=>1, "value"=>"x"}]}',
        '{"product_specification"=>[{"key"=>"a", "value"=>"unterminated}]}',
        '{"product_specification"=>' + "[" * 9 + "]" * 9 + "}",
    ],
)
def test_unsupported_specifications_are_attribute_level_failures(cell):
    entries, issues = parse_specifications(cell, DICTIONARY["bounds"])
    assert not entries and "SPEC_PARSE_ERROR" in issues


def test_entry_cap_is_enforced():
    cell = spec(**{f"k{i}": "v" for i in range(257)})
    assert parse_specifications(cell, DICTIONARY["bounds"]) == ([], ["SPEC_PARSE_ERROR"])


def test_shuffled_input_gives_identical_selection_digest():
    rows = [
        row("A1"),
        row("A2", uniq_id="old", crawl_timestamp="2015-01-01T00:00:00Z", discounted_price="5"),
        row("A2", uniq_id="new"),
        row("A3", discounted_price=""),
        row("A4", uniq_id="a"),
        row("A4", uniq_id="b"),
    ]
    _, first = run(rows)
    for seed in range(5):
        shuffled = rows[:]
        random.Random(seed).shuffle(shuffled)
        _, other = run(shuffled)
        assert other.digest == first.digest
        assert [i.uniq_id for i in other.canonical] == [i.uniq_id for i in first.canonical]


def test_digest_changes_with_business_content_but_not_provenance():
    _, base = run([row("A1")])
    _, changed = run([row("A1", discounted_price="380")])
    _, moved = run([row("A1", uniq_id="other", product_url="https://example.invalid/other")])
    assert changed.digest != base.digest
    assert moved.digest == base.digest


@pytest.mark.parametrize(
    "tree,expected",
    [
        ('["Bags, Wallets & Belts >> X"]', "bags_wallets_belts"),
        ('["eBooks >> X"]', "ebooks"),
        ('["Home Decor & Festive Needs"]', "home_decor_festive_needs"),
        ('["Clothing"]', "clothing"),
    ],
)
def test_root_slugs(tree, expected):
    _, selection = run([row("A1", product_category_tree=tree)])
    assert selection.canonical[0].fields["category"] == expected
    assert root_slug("eBooks") == "ebooks"


def test_malformed_category_keeps_the_row_and_flags_it():
    observations, selection = run([row("A1", product_category_tree="not json")])
    assert selection.canonical[0].fields["category"] is None
    assert "CATEGORY_UNCLASSIFIED" in observations[0].issues


@pytest.mark.parametrize(
    "value,expected",
    [
        ("Medium", "M"),
        ("  medium ", "M"),
        ("Extra Large", "XL"),
        ("XXXL", "XXXL"),
        ("Free Size", "FREE_SIZE"),
        ("One Size Fits All", "ONE_SIZE"),
        ("This product is sold as L by the Brand", "L"),
        ("42", None),
        ("S, M", None),
    ],
)
def test_conservative_apparel_size(value, expected):
    _, selection = run([row("A1", product_specifications=spec(Size=value))])
    fields = selection.canonical[0].fields
    assert fields["size"] == expected
    assert fields["size_kind"] == ("apparel_alpha" if expected else None)


def test_material_key_order_depends_on_category():
    clothing = spec(Material="A", Fabric="B")
    furniture = spec(Material="A", **{"Primary Material": "B"})
    other = spec(Fabric="B")
    assert (
        run([row("A", product_specifications=clothing)])[1].canonical[0].fields["material"] == "b"
    )
    assert (
        run([row("A", product_specifications=furniture, product_category_tree='["Furniture"]')])[1]
        .canonical[0]
        .fields["material"]
        == "b"
    )
    assert (
        run([row("A", product_specifications=other, product_category_tree='["Watches"]')])[1]
        .canonical[0]
        .fields["material"]
        is None
    )


def test_price_above_retail_is_flagged_but_kept():
    observations, selection = run([row("A1", discounted_price="1000", retail_price="999")])
    assert selection.canonical[0].fields["price_minor"] == 100000
    assert "PRICE_INCONSISTENT" in observations[0].issues


def test_invalid_rating_and_disagreement_are_flags_not_zero():
    observations, selection = run([row("A1", product_rating="7", overall_rating="4.50")])
    assert selection.canonical[0].fields["rating"] == "4.5"
    assert {"INVALID_RATING", "RATING_DISAGREEMENT"} <= set(observations[0].issues)


def test_dictionary_hash_ignores_checkout_line_endings(tmp_path):
    lf = tmp_path / "lf.json"
    crlf = tmp_path / "crlf.json"
    text = (ROOT / "contracts/dictionaries/catalog/flipkart-v1.json").read_text(encoding="utf-8")
    lf.write_bytes(text.encode("utf-8"))
    crlf.write_bytes(text.replace("\n", "\r\n").encode("utf-8"))
    assert load_dictionary(lf)["sha256"] == load_dictionary(crlf)["sha256"]
