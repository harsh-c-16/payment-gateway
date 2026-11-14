"""vector_exact, hybrid_exact and hybrid_ann with the real locked model and a real HNSW index."""

from uuid import uuid4

import psycopg
import pytest
from starlette.testclient import TestClient

from pipelines.catalog.embeddings import build_embeddings
from pipelines.catalog.migrate import apply_variant
from services.catalog import search as search_module
from services.catalog.app import create_app
from services.catalog.embedding import vector_text
from shared.contracts.catalog import ShoppingIntent
from tests.catalog.helpers import import_rows, seed_stock
from tests.catalog.service_helpers import TOKEN, catalogue, headers, search, skus


@pytest.fixture
def semantic(tmp_path, database_url, db, events, encoder, monkeypatch, outbox_double):
    monkeypatch.setenv("INTERNAL_API_TOKEN", TOKEN)
    namespace = "bench-h-" + uuid4().hex[:16]
    import_rows(tmp_path, database_url, namespace, catalogue())
    seed_stock(
        db,
        events.codec,
        namespace,
        ["FK-SHIRT1", "FK-SHIRT2", "FK-SHIRT3", "FK-DRESS1", "FK-WATCH1", "FK-ODD1"],
    )
    with psycopg.connect(database_url, autocommit=True) as connection:
        build_embeddings(connection, namespace, encoder)
    client = TestClient(create_app(db=db, events=events, encoder=encoder))
    return client, namespace


def test_vector_exact_ranks_by_meaning_and_reports_inference(semantic, encoder):
    client, namespace = semantic
    result = search(client, namespace, query_text="wristwatch", mode="vector_exact")
    assert skus(result)[0] == "FK-WATCH1"
    assert result["embedding_calls"] == 1 and result["timings_ms"]["embedding"] > 0
    assert result["embedding_revision"] == encoder.revision
    scores = [hit["score"] for hit in result["hits"]]
    assert scores == sorted(scores, reverse=True)
    assert {hit["retrieval_mode"] for hit in result["hits"]} == {"vector_exact"}


@pytest.mark.parametrize("mode", ["vector_exact", "hybrid_exact"])
def test_semantic_modes_never_relax_hard_filters(semantic, mode):
    client, namespace = semantic
    assert skus(search(client, namespace, query_text="watch", mode=mode, category="watches")) == [
        "FK-WATCH1"
    ]
    assert skus(search(client, namespace, query_text="watch", mode=mode, max_price_minor=0)) == []
    assert skus(search(client, namespace, query_text="watch", mode=mode, size="XXS")) == []
    assert "FK-NOPRICE" not in skus(search(client, namespace, query_text="shirt", mode=mode))
    assert "FK-NOSTOCK" not in skus(search(client, namespace, query_text="shirt", mode=mode))


def test_hybrid_exact_fuses_lexical_and_vector_with_rrf(semantic):
    client, namespace = semantic
    result = search(client, namespace, query_text="blue shirt", mode="hybrid_exact", top_k=20)
    assert skus(result)[0] == "FK-SHIRT1"
    assert result["hits"][0]["score"] == pytest.approx(2 / 61)
    assert result["embedding_calls"] == 1
    assert result["candidate_count"] >= result["returned_count"]
    assert skus(
        search(client, namespace, query_text="blue shirt", mode="hybrid_exact", top_k=20)
    ) == (skus(result))


def test_stopwords_alone_do_not_feed_sku_order_into_the_fusion(semantic):
    client, namespace = semantic
    hybrid = search(client, namespace, query_text="the and of", mode="hybrid_exact", top_k=20)
    vector = search(client, namespace, query_text="the and of", mode="vector_exact", top_k=20)
    assert skus(hybrid) == skus(vector)


def test_no_text_makes_no_embedding_call(semantic):
    client, namespace = semantic
    result = search(client, namespace, query_text="", mode="hybrid_exact", category="watches")
    assert skus(result) == ["FK-WATCH1"] and result["embedding_calls"] == 0


@pytest.mark.parametrize("damage", ["embedding=NULL", "embedding_revision='old-model'"])
def test_semantic_search_refuses_missing_or_mixed_revision_vectors(semantic, db, damage):
    client, namespace = semantic
    with db.transaction() as tx:
        tx.execute(
            f"UPDATE products SET {damage} WHERE namespace=%s AND sku='FK-SHIRT1'", (namespace,)
        )
    response = client.post(
        "/v1/search",
        headers=headers(namespace),
        json={
            "request_id": str(uuid4()),
            "session_id": str(uuid4()),
            "intent": {**intent().model_dump(), "query_text": "shirt"},
            "mode": "hybrid_exact",
        },
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    caps = client.get("/v1/catalog/capabilities", headers=headers(namespace)).json()
    assert caps["search_modes"] == ["lexical"]


def test_occasion_reaches_the_semantic_query_but_is_not_a_filter(semantic):
    client, namespace = semantic
    result = search(
        client, namespace, query_text="", occasion="time keeping wrist", mode="vector_exact"
    )
    assert result["embedding_calls"] == 1 and result["returned_count"] == 5
    assert skus(result)[0] == "FK-WATCH1"


def intent(**facets):
    values = dict.fromkeys(("category", "size", "colour", "material", "occasion"))
    return ShoppingIntent(query_text="x", max_price_minor=None, **{**values, **facets})


def test_exact_never_uses_hnsw_and_ann_does(semantic, database_url, db, encoder):
    _, namespace = semantic
    with psycopg.connect(database_url, autocommit=True) as connection:
        apply_variant(connection, "r-ann")
    vectors, _ = encoder.encode(["blue shirt"])
    vector = vector_text(vectors[0])
    with db.transaction() as tx:
        where, parameters, _ = search_module.filter_catalog(tx, intent(), namespace)
        values = {**parameters, "vector": vector, "limit": 5}
        exact_plan = "\n".join(
            row["QUERY PLAN"]
            for row in tx.execute(
                "EXPLAIN WITH eligible AS MATERIALIZED (SELECT p.sku, p.embedding FROM "
                f"{search_module.FROM_ELIGIBLE} WHERE {where} AND p.embedding IS NOT NULL) "
                "SELECT sku, embedding <=> %(vector)s::vector AS distance FROM eligible "
                "ORDER BY distance, sku LIMIT %(limit)s",
                values,
            ).fetchall()
        )
        assert "products_r_ann_hnsw" not in exact_plan
        exact = search_module.exact_search(tx, where, parameters, vector, 5)
        ann = search_module.ann_search(tx, where, parameters, vector, 5)
        ann_plan = "\n".join(
            row["QUERY PLAN"]
            for row in tx.execute(
                f"EXPLAIN SELECT p.sku FROM {search_module.FROM_ELIGIBLE} WHERE {where} "
                "AND p.embedding IS NOT NULL ORDER BY p.embedding <=> %(vector)s::vector "
                "LIMIT %(limit)s",
                values,
            ).fetchall()
        )
    assert "products_r_ann_hnsw" in ann_plan
    assert [row["sku"] for row in ann] == [row["sku"] for row in exact]


def test_hybrid_ann_respects_filters_and_settings_do_not_leak(semantic, database_url, db):
    client, namespace = semantic
    with psycopg.connect(database_url, autocommit=True) as connection:
        apply_variant(connection, "r-ann")
    result = search(client, namespace, query_text="watch", mode="hybrid_ann", category="watches")
    assert skus(result) == ["FK-WATCH1"]
    assert {hit["retrieval_mode"] for hit in result["hits"]} == {"hybrid_ann"}
    assert skus(search(client, namespace, query_text="watch", mode="hybrid_ann", size="XXS")) == []
    with db.transaction() as tx:
        assert tx.execute("SELECT current_setting('enable_seqscan') AS v").fetchone()["v"] == "on"
