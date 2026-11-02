"""NDCG arithmetic, label handling and the blinded pool. Labels here are synthetic test values."""

import csv
import math
from uuid import uuid4

import pytest

from pipelines.catalog import relevance
from tests.catalog.helpers import import_rows, seed_stock
from tests.catalog.service_helpers import catalogue


def test_ndcg_matches_the_evaluation_spec_formula():
    judged = {"a": 3, "b": 2, "c": 0}
    assert relevance.ndcg_at_5(["a", "b", "c"], judged) == pytest.approx(1.0)
    worst = relevance.ndcg_at_5(["c", "b", "a"], judged)
    ideal = 7 + 3 / math.log2(3)
    assert worst == pytest.approx((3 / math.log2(3) + 7 / math.log2(4)) / ideal)


def test_no_positive_label_is_not_scored_as_zero():
    assert relevance.ndcg_at_5(["a"], {"a": 0}) is None


def test_unjudged_results_earn_nothing_but_only_top_five_count():
    assert relevance.ndcg_at_5(["x", "y"], {"a": 3}) == 0
    late = relevance.ndcg_at_5(["x", "x", "x", "x", "x", "a"], {"a": 3})
    assert late == 0


def test_labels_must_be_zero_to_three_and_blank_stays_unjudged(tmp_path):
    path = tmp_path / "labels.csv"
    path.write_text("query_id,sku,label\nQ,A,3\nQ,B,\nQ,C,0\n", encoding="utf-8")
    assert relevance.read_labels(path) == {"Q": {"A": 3, "C": 0}}
    path.write_text("query_id,sku,label\nQ,A,4\n", encoding="utf-8")
    with pytest.raises(ValueError):
        relevance.read_labels(path)


def specs():
    def spec(query_id, split, text, **facets):
        intent = dict.fromkeys(
            ("category", "size", "colour", "material", "max_price_minor", "occasion")
        )
        return {
            "query_id": query_id,
            "split": split,
            "request": {
                "top_k": 5,
                "intent": {**intent, "query_text": text, "currency": "INR", **facets},
            },
        }

    return [
        spec("D1", "dev", "blue shirt"),
        spec("H1", "held_out", "watch", category="watches"),
        spec("Z1", "dev", "shirt", max_price_minor=0),
    ]


def test_pool_is_blinded_unlabelled_and_score_needs_labels(
    tmp_path, database_url, db, events, outbox_double
):
    namespace = "bench-h-" + uuid4().hex[:16]
    import_rows(tmp_path, database_url, namespace, catalogue())
    seed_stock(db, events.codec, namespace, ["FK-SHIRT1", "FK-SHIRT2", "FK-WATCH1"])
    out = tmp_path / "pool.csv"
    modes = ("filter_only", "lexical")
    count = relevance.build_pool(db, namespace, out, modes=modes, specs=specs())
    with out.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert count == len(rows) and rows
    assert all(row["label"] == "" for row in rows)
    assert "mode" not in rows[0] and "rank" not in rows[0] and "score" not in rows[0]
    assert {row["query_id"] for row in rows} == {"D1", "H1"}
    empty = relevance.score(db, namespace, out, modes=modes, specs=specs())
    assert empty["status"] == "NOT_RUN" and empty["modes"] == {}
    relevant = {"D1": "FK-SHIRT1", "H1": "FK-WATCH1"}
    for row in rows:
        row["label"] = "3" if row["sku"] == relevant[row["query_id"]] else "0"
    with out.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=relevance.POOL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    report = relevance.score(db, namespace, out, modes=modes, specs=specs())
    assert report["status"] == "MEASURED" and report["judged_queries"] == 2
    lexical = report["modes"]["lexical"]
    assert lexical["dev"]["ndcg_at_5"] == pytest.approx(1.0)
    assert lexical["held_out"]["ndcg_at_5"] == pytest.approx(1.0)
    assert lexical["unjudged_results"] == 0
    assert report["label_sources"] == ["unstated"]
    assert report["uniform_label_queries"] == ["H1"]
    assert lexical["held_out"]["ndcg_at_5_excluding_uniform"] is None
    assert lexical["dev"]["queries_excluding_uniform"] == 1
