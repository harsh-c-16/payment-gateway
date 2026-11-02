"""The consumer stub stays honest: same OpenAPI as the real service, every path exercised."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from starlette.testclient import TestClient

from pipelines.catalog.artifacts import content_hash
from services.conversation.provider_contracts import ENDPOINTS, OpenAPIContracts
from shared.contracts.catalog import SkuManifest
from tests.catalog import stub_provider as stub

ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = OpenAPIContracts(ROOT / "contracts/http")
CLIENT = TestClient(stub.create_stub())


def quote_body(sku):
    return {"cart_id": str(uuid4()), "cart_version": 1, "lines": [{"sku": sku, "quantity": 2}]}


def search_body(text):
    return {
        "request_id": str(uuid4()),
        "session_id": str(uuid4()),
        "top_k": 5,
        "mode": "lexical",
        "intent": {
            "query_text": text,
            "category": None,
            "size": None,
            "colour": None,
            "material": None,
            "max_price_minor": None,
            "occasion": None,
            "currency": "INR",
        },
    }


def test_success_and_empty_search_are_contract_valid():
    for text, count in (("shirt", 1), ("empty", 0)):
        response = CLIENT.post("/v1/search", json=search_body(text)).json()
        CONTRACTS.validate(ENDPOINTS["search"], "response", response)
        assert response["returned_count"] == count


def test_facets_and_quote_are_contract_valid():
    CONTRACTS.validate(ENDPOINTS["facets"], "response", CLIENT.get("/v1/catalog/facets").json())
    response = CLIENT.post("/v1/quotes", json=quote_body("FK-STUB-OK"))
    assert response.status_code == 201
    CONTRACTS.validate(ENDPOINTS["quote"], "response", response.json())


def test_quote_failure_paths():
    assert CLIENT.post("/v1/quotes", json=quote_body("FK-STUB-INACTIVE")).status_code == 409
    assert CLIENT.post("/v1/quotes", json=quote_body("FK-STUB-DOWN")).status_code == 503


def test_internal_lookup_paths_orders_must_handle():
    found = CLIENT.get(f"/internal/v1/quotes/{stub.OK_QUOTE}", headers={"X-User-ID": "buyer"})
    CONTRACTS.validate(ENDPOINTS["quote_lookup"], "response", found.json())
    assert found.json()["user_id"] == "buyer"
    expired = CLIENT.get(f"/internal/v1/quotes/{stub.EXPIRED_QUOTE}").json()
    CONTRACTS.validate(ENDPOINTS["quote_lookup"], "response", expired)
    assert expired["expires_at"] < datetime.now(UTC).isoformat()
    assert CLIENT.get(f"/internal/v1/quotes/{stub.FAILING_QUOTE}").status_code == 503
    assert CLIENT.get(f"/internal/v1/quotes/{stub.OTHER_USER_QUOTE}").status_code == 403
    assert CLIENT.get(f"/internal/v1/quotes/{uuid4()}").status_code == 404


def test_stub_declares_itself():
    assert CLIENT.get("/health/ready").json()["real_provider"] is False


def test_example_sku_manifest_matches_the_published_schema_and_hash():
    path = ROOT / "contracts/fixtures/catalog/sku_manifest.example.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    assert SkuManifest.model_validate(document).sku_count == 3
    assert document["content_sha256"] == content_hash(document)
    assert document["dataset_revision"].startswith("example")
