"""The written labelling rules, and that the committed labels are the ones those rules produce."""

import csv
import json

import pytest

from pipelines.catalog import relevance

SHIRT = {
    "product": ["shirt"],
    "not_product": ["t-shirt"],
    "exclude": ["bra"],
    "related": ["t-shirt"],
    "attributes": [["cotton"]],
    "conflicts": ["linen"],
}


def row(title, description="", brand=""):
    return {"title": title, "description": description, "brand": brand}


@pytest.mark.parametrize(
    ("title", "description", "brand", "expected"),
    [
        ("Women's T-Shirt Bra", "", "", 0),
        ("Men's Trousers", "wear it with a shirt", "", 0),
        ("Printed Men's T-Shirt", "cotton", "", 1),
        ("Linen Shirt", "", "", 1),
        ("Formal Shirt", "", "", 2),
        ("Formal Shirt", "Fabric: Cotton", "", 3),
        ("Cotton Shirt", "", "", 3),
        ("Cotton World Formal Shirt", "Cotton World makes this", "Cotton World", 2),
    ],
)
def test_first_matching_rule_decides(title, description, brand, expected):
    assert relevance.rule_label(SHIRT, row(title, description, brand))[0] == expected


def test_a_query_without_a_key_stays_unjudged():
    assert relevance.rule_label(None, row("Anything"))[0] is None


def test_a_close_match_is_capped_below_an_exact_one():
    key = {"product": ["bedsheet", "top sheet"], "cap": ["top sheet"]}
    assert relevance.rule_label(key, row("Double Top Sheet"))[0] == 2
    assert relevance.rule_label(key, row("Double Bedsheet"))[0] == 3


def test_a_product_named_only_in_the_description_is_a_close_match():
    key = {"product": ["pendant"], "description_product": ["pendant"], "related": ["necklace"]}
    assert relevance.rule_label(key, row("Alloy Necklace", "with a bold pendant"))[0] == 2
    assert relevance.rule_label(key, row("Alloy Necklace", "plain chain"))[0] == 1
    assert relevance.rule_label(key, row("Alloy Bangle", "plain"))[0] == 0


def test_key_covers_exactly_the_queries_that_have_text_and_candidates():
    key = json.loads(relevance.KEY.read_text(encoding="utf-8"))
    queries = json.loads(relevance.QUERIES.read_text(encoding="utf-8"))["queries"]
    expected = {
        query["query_id"]
        for query in queries
        if query["request"]["intent"]["query_text"] and query["stratum"] != "zero"
    }
    assert set(key["queries"]) == expected
    assert "not judged row by row" in key["provenance"]


def test_committed_labels_name_their_source_and_carry_no_product_text():
    with relevance.LABELS.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert tuple(rows[0]) == relevance.LABEL_COLUMNS
    assert len({row["label_source"] for row in rows}) == 1
    assert rows[0]["label_source"].startswith("rules-v2:")
    labelled = relevance.read_labels(relevance.LABELS)
    assert sum(len(judged) for judged in labelled.values()) == 829
    assert len(rows) == 903
