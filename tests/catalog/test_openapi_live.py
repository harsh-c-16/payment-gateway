"""Live responses validated by Jaineel's own schema reader, the way consumers see them."""

from pathlib import Path

from services.conversation.provider_contracts import ENDPOINTS, OpenAPIContracts
from tests.catalog.service_helpers import headers, price, quote, search

ROOT = Path(__file__).resolve().parents[2]


def test_responses_validate_against_published_openapi_as_consumers_see_them(world):
    client, namespace, _ = world
    contracts = OpenAPIContracts(ROOT / "contracts/http")
    result = search(client, namespace, query_text="blue shirt")
    contracts.validate(ENDPOINTS["search"], "response", result)
    empty = search(client, namespace, query_text="blue shirt", max_price_minor=0)
    contracts.validate(ENDPOINTS["search"], "response", empty)
    product = client.get("/v1/products/FK-NOPRICE", headers=headers(namespace)).json()
    contracts.validate(ENDPOINTS["product"], "response", product)
    facets = client.get("/v1/catalog/facets", headers=headers(namespace)).json()
    contracts.validate(ENDPOINTS["facets"], "response", facets)
    created = quote(client, namespace, [{"sku": "FK-SHIRT1", "quantity": 2}])
    contracts.validate(ENDPOINTS["quote"], "response", created)
    contracts.validate(ENDPOINTS["quote_lookup"], "response", created)
    updated = price(client, namespace, "FK-SHIRT1", 38000, 1)
    contracts.validate(ENDPOINTS["price"], "response", updated)
