"""Jaineel's real gateway and fixed workflow against the real catalogue over real HTTP.

p7_workflow.md asks me to review this binding. His code is exercised here, never changed.
"""

from threading import Thread
from time import sleep
from uuid import uuid4

import pytest
import uvicorn

from services.catalog.app import create_app
from services.conversation.gateway import Gateway
from services.conversation.workflow import FixedWorkflow
from tests.catalog.conftest import make_context


@pytest.fixture
def live(world, db, events):
    _, namespace, _ = world
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(db=db, events=events), host="127.0.0.1", port=0, log_level="error"
        )
    )
    thread = Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        sleep(0.01)
    base = f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"
    yield FixedWorkflow(None, Gateway(base, base)), namespace
    server.should_exit = True
    thread.join(5)


def session(namespace):
    return make_context(namespace, session=str(uuid4()))


@pytest.mark.parametrize(
    ("intent", "expected"),
    [
        ({"query_text": "blue shirt"}, "FK-SHIRT1"),
        ({"query_text": "shirt", "category": "clothing", "colour": "blue"}, "FK-SHIRT1"),
        ({"query_text": "watch", "max_price_minor": 600000}, "FK-WATCH1"),
    ],
)
def test_workflow_accepts_real_search_where_eligible_exceeds_text_matches(live, intent, expected):
    workflow, namespace = live
    context = session(namespace)
    result = workflow.structured_search(intent, context, key=str(uuid4()))
    assert result["hits"][0]["sku"] == expected
    assert result["candidate_count"] >= result["eligible_count"] >= result["returned_count"]


def test_facets_product_and_quote_pass_the_consumer_contract(live):
    workflow, namespace = live
    context = session(namespace)
    dictionary = workflow.call("facets", context, params={"namespace": namespace})
    assert {"key": "acme", "label": "Acme"} in dictionary["brands"]
    assert workflow.call("product", context, sku="FK-SHIRT1")["product"]["sku"] == "FK-SHIRT1"
    body = {
        "cart_id": str(uuid4()),
        "cart_version": 1,
        "lines": [{"sku": "FK-SHIRT1", "quantity": 1}],
    }
    quote = workflow.call("quote", context, body=body, key=str(uuid4()))
    assert quote["lines"][0]["sku"] == "FK-SHIRT1"


def test_workflow_accepts_a_real_brand_filter(live):
    workflow, namespace = live
    result = workflow.structured_search(
        {"query_text": "shirt", "brand": "acme"}, session(namespace), key=str(uuid4())
    )
    assert result["hits"]
    assert all(hit["brand"].casefold() == "acme" for hit in result["hits"])
