"""Hard filters, ranking and retrieval events. The outbox is an explicit test double."""

from uuid import uuid4

import pytest
from starlette.testclient import TestClient

from services.catalog.app import create_app
from services.catalog.events import SharedEvents
from services.catalog.search import fuse_rrf
from tests.catalog.service_helpers import captured, search, skus


def test_unknown_stock_and_inactive_are_never_sale_suggestions(world):
    client, namespace, _ = world
    result = search(client, namespace, query_text="blue cotton shirt", top_k=20)
    assert "FK-NOPRICE" not in skus(result)
    assert "FK-NOSTOCK" not in skus(result)
    assert "FK-ZEROSTOCK" not in skus(result)
    assert result["eligible_count"] == 6


@pytest.mark.parametrize(
    "intent,expected",
    [
        ({"category": "watches"}, ["FK-WATCH1"]),
        ({"size": "M"}, ["FK-SHIRT1"]),
        ({"size": "L"}, ["FK-SHIRT2"]),
        ({"size": "XXS"}, []),
        ({"colour": "blue"}, ["FK-SHIRT1"]),
        ({"colour": "Gray"}, ["FK-SHIRT2"]),
        ({"colour": "grey"}, ["FK-SHIRT2"]),
        ({"colour": "green"}, []),
        ({"material": "cotton"}, ["FK-SHIRT1"]),
        ({"material": "cotton lycra"}, ["FK-SHIRT2"]),
        ({"brand": "ACME"}, ["FK-SHIRT1"]),
        ({"brand": "Unknown"}, []),
        ({"max_price_minor": 0}, []),
        ({"max_price_minor": 5000}, ["FK-ODD1"]),
        ({"max_price_minor": 30000}, ["FK-ODD1", "FK-SHIRT2"]),
        ({"category_path_prefix": ["clothing", "dresses"]}, ["FK-DRESS1"]),
        ({"category_path_prefix": ["CLOTHING", "Dresses"]}, ["FK-DRESS1"]),
        ({"category_path_prefix": ["Cloth"]}, []),
        ({"category_path_prefix": ["Watches", "Analog", "Deep"]}, []),
    ],
)
def test_hard_filters_are_never_relaxed(world, intent, expected):
    client, namespace, _ = world
    result = search(client, namespace, mode="filter_only", top_k=20, **intent)
    assert skus(result) == expected
    assert result["eligible_count"] == result["candidate_count"] == len(expected)
    assert result["exhausted"] is True


def test_compound_and_multicolour_do_not_satisfy_exact_facets(world):
    client, namespace, _ = world
    assert "FK-SHIRT3" not in skus(search(client, namespace, colour="blue", mode="filter_only"))
    assert skus(search(client, namespace, colour="multicolor", mode="filter_only")) == ["FK-SHIRT3"]


@pytest.mark.parametrize(
    "intent", [{"size": "42"}, {"category": "mystery"}, {"category_path_prefix": []}]
)
def test_unsupported_filter_is_422_not_silently_dropped(world, intent):
    client, namespace, _ = world
    result = search(client, namespace, expect=422, **intent)
    assert result["error"]["code"] == "UNSUPPORTED_FILTER"


def test_filter_only_orders_by_price_then_sku(world):
    client, namespace, _ = world
    result = search(client, namespace, mode="filter_only", top_k=20, category="clothing")
    prices = [hit["price_minor"] for hit in result["hits"]]
    assert prices == sorted(prices) and prices[0] == 30000
    assert [hit["rank"] for hit in result["hits"]] == list(range(1, len(prices) + 1))
    assert {hit["retrieval_mode"] for hit in result["hits"]} == {"filter_only"}


def test_lexical_ranks_title_above_description_and_is_reproducible(world):
    client, namespace, _ = world
    first = search(client, namespace, query_text="blue shirt", top_k=20)
    assert skus(first)[0] == "FK-SHIRT1"
    assert skus(first).index("FK-SHIRT3") > 0
    assert "FK-WATCH1" not in skus(first)
    assert first["candidate_count"] < first["eligible_count"]
    assert skus(search(client, namespace, query_text="blue shirt", top_k=20)) == skus(first)


def test_query_without_terms_lists_eligible_in_sku_order(world):
    client, namespace, _ = world
    for text in ("", "the and of"):
        result = search(client, namespace, query_text=text, top_k=20, category="watches")
        assert skus(result) == ["FK-WATCH1"] and result["hits"][0]["score"] == 0


def test_top_k_truncates_and_reports_not_exhausted(world):
    client, namespace, _ = world
    result = search(client, namespace, mode="filter_only", top_k=2)
    assert result["returned_count"] == 2 and result["exhausted"] is False
    assert result["eligible_count"] == 6
    search(client, namespace, top_k=21, expect=422)
    search(client, namespace, top_k=0, expect=422)


def test_hostile_query_text_is_data(world):
    client, namespace, _ = world
    result = search(client, namespace, query_text="'; DROP TABLE products; -- & | ! :*")
    assert result["error"] if "error" in result else result["returned_count"] == 0
    assert skus(search(client, namespace, category="watches", mode="filter_only"))


def test_vector_modes_fail_visibly_until_provisioned(world):
    client, namespace, _ = world
    result = search(client, namespace, mode="hybrid_exact", expect=503)
    assert result["error"]["code"] == "DEPENDENCY_UNAVAILABLE"


def test_search_persists_paired_validated_events(world, database_url):
    client, namespace, report = world
    result = search(client, namespace, query_text="watch")
    events = captured(database_url)
    assert [e["event_type"] for e in events] == ["SEARCH_REQUESTED", "PRODUCT_RETRIEVED"]
    assert {e["aggregate_id"] for e in events} == {result["search_id"]}
    assert [e["aggregate_version"] for e in events] == [1, 2]
    assert events[1]["payload"]["skus"] == skus(result)
    assert all(e["metadata"]["dataset_revision"] == report.dataset_revision for e in events)
    assert all(e["source_service"] == "catalog" for e in events)


def test_search_without_shared_outbox_fails_closed(world, db, monkeypatch):
    _, namespace, _ = world
    monkeypatch.delitem(__import__("sys").modules, "shared.outbox", raising=False)
    client = TestClient(create_app(db=db, events=SharedEvents()), raise_server_exceptions=False)
    result = search(client, namespace, expect=503)
    assert result["error"]["code"] == "DEPENDENCY_UNAVAILABLE"
    assert client.get("/health/ready").status_code == 503


def test_rrf_counts_a_sku_once_with_both_contributions_and_breaks_ties_on_sku():
    fused = fuse_rrf(["A", "B"], ["B", "C"], k=60, top_k=5)
    assert fused[0][0] == "B"
    assert fused[0][1] == pytest.approx(1 / 62 + 1 / 61)
    assert [sku for sku, _ in fused] == ["B", "A", "C"]
    assert fuse_rrf(["B"], ["A"]) == [("A", 1 / 61), ("B", 1 / 61)]
    assert len(fuse_rrf(["A", "B", "C"], [], top_k=2)) == 2


@pytest.mark.parametrize("intent", [{"colour": ""}, {"brand": "x" * 257}, {"occasion": ""}])
def test_facet_bounds_fail_as_validation_not_as_an_event_failure(world, intent):
    client, namespace, _ = world
    result = search(client, namespace, expect=422, **intent)
    assert result["error"]["code"] == "VALIDATION_ERROR"


def test_service_without_schema_cache_is_not_ready(world, db, monkeypatch, tmp_path):
    import shared.event_transport as transport

    monkeypatch.setenv("EVENT_SCHEMA_CACHE_PATH", str(tmp_path / "absent.json"))
    monkeypatch.setattr(transport, "_codec", None)
    client = TestClient(create_app(db=db, events=SharedEvents()), raise_server_exceptions=False)
    assert client.get("/health/ready").status_code == 503


def test_namespace_without_a_catalogue_is_not_found(world):
    client, _, _ = world
    other = "bench-h-" + uuid4().hex[:16]
    assert search(client, other, expect=404)["error"]["code"] == "NOT_FOUND"
