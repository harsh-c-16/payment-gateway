"""The 50 frozen W-SEARCH specifications: strata, split and real-catalogue selectivity."""

import json
from collections import Counter
from pathlib import Path
from uuid import uuid4

from pipelines.catalog.adapter import run_import
from services.catalog import search
from shared.contracts.catalog import ShoppingIntent

FIXTURE = json.loads(
    (Path(__file__).resolve().parents[2] / "contracts/fixtures/catalog/queries.json").read_text(
        encoding="utf-8"
    )
)
QUERIES = FIXTURE["queries"]
BOUNDS = {"broad": (300, 20000), "selective": (5, 3500), "zero": (0, 0), "few": (1, 4)}


def test_counts_and_split_are_frozen():
    assert Counter(q["stratum"] for q in QUERIES) == {
        "broad": 20,
        "selective": 20,
        "zero": 5,
        "few": 5,
    }
    assert Counter(q["split"] for q in QUERIES) == {"dev": 30, "held_out": 20}
    assert len({q["query_id"] for q in QUERIES}) == 50


def test_relevance_labels_are_not_invented():
    assert FIXTURE["relevance_labels"] is None
    assert FIXTURE["review_status"] == "awaiting_human_review"


def test_strata_hold_on_the_real_catalogue(tmp_path, database_url, db, source_csv):
    namespace = "bench-h-" + uuid4().hex[:16]
    run_import(
        source_csv,
        load_mode="copy",
        namespace=namespace,
        out=tmp_path / namespace,
        url=database_url,
    )
    with db.transaction() as tx:
        tx.execute(
            "INSERT INTO stock_projection (namespace,sku,on_hand,reserved,stock_version,"
            "changed_at,event_id) SELECT namespace,sku,10000,0,1,clock_timestamp(),"
            "gen_random_uuid() FROM products WHERE namespace=%s AND active",
            (namespace,),
        )
    with db.transaction() as tx:
        counts = {
            q["query_id"]: search.filter_catalog(
                tx, ShoppingIntent(**q["request"]["intent"]), namespace
            )[2]
            for q in QUERIES
        }
    outside = {
        q["query_id"]: counts[q["query_id"]]
        for q in QUERIES
        if not BOUNDS[q["stratum"]][0] <= counts[q["query_id"]] <= BOUNDS[q["stratum"]][1]
    }
    assert not outside
