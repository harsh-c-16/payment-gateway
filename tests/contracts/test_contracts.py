import copy
import json

import pytest
import yaml
from pydantic import ValidationError

import projectctl.artifacts as artifacts
import projectctl.config as config
from projectctl.cli import main
from projectctl.contract_checks import PARTICIPANTS, inspect_contracts
from projectctl.conversation_contract import document
from services.conversation.provider_contracts import (
    ENDPOINTS,
    ContractUnavailable,
    ContractViolation,
    OpenAPIContracts,
)
from shared.contracts.conversation import (
    CartSnapshot,
    CartUpdateRequest,
    CheckoutRequest,
    TurnRequest,
    TurnResponse,
)

from .provisional import NOW, REQUESTS, RESPONSES, ROOT, ProvisionalContracts, uid


def test_every_provisional_pair_matches_explicit_test_schema(pairs):
    contracts = ProvisionalContracts()
    covered = set()
    for pair in pairs.values():
        endpoint = ENDPOINTS[pair["endpoint"]]
        if pair["request"] is not None:
            contracts.validate(endpoint, "request", pair["request"])
        contracts.validate(endpoint, "response", pair["response"])
        covered.add(pair["endpoint"])
    assert covered == ENDPOINTS.keys()


@pytest.mark.parametrize("bad_money", ["39900", 39900.0, 39900.5, True, -1, 2**63])
def test_wrong_money_type_or_bounds_rejected(bad_money, pairs):
    quote = copy.deepcopy(pairs["changed-price-authoritative-quote"]["response"])
    quote["total_amount_minor"] = bad_money
    with pytest.raises(ContractViolation):
        ProvisionalContracts().validate(ENDPOINTS["quote"], "response", quote)


def test_misspelled_required_field_is_rejected(pairs):
    response = copy.deepcopy(pairs["five-hits"]["response"])
    response["returned_cout"] = response.pop("returned_count")
    with pytest.raises(ContractViolation):
        ProvisionalContracts().validate(ENDPOINTS["search"], "response", response)


def test_missing_and_null_facet_are_different(pairs):
    response = copy.deepcopy(pairs["fewer-than-five-null-facets"]["response"])
    assert response["hits"][0]["size"] is None
    ProvisionalContracts().validate(ENDPOINTS["search"], "response", response)
    del response["hits"][0]["size"]
    with pytest.raises(ContractViolation):
        ProvisionalContracts().validate(ENDPOINTS["search"], "response", response)


def test_hard_filter_example_preserves_explicit_constraint(pairs):
    pair = pairs["five-hits"]
    request = pair["request"]
    assert request["intent"]["max_price_minor"] == 50000
    assert all(
        hit["price_minor"] <= request["intent"]["max_price_minor"]
        for hit in pair["response"]["hits"]
    )
    # A size requirement cannot be fulfilled by an unknown size; fixture truth remains empty.
    strict_size = copy.deepcopy(request)
    strict_size["intent"].update(category="clothing", size="M")
    ProvisionalContracts().validate(ENDPOINTS["search"], "request", strict_size)
    assert pairs["no-results"]["response"]["hits"] == []


def test_conversation_openapi_owned_schemas_and_exact_endpoints():
    actual = yaml.safe_load((ROOT / "contracts/http/conversation.yaml").read_text(encoding="utf-8"))
    assert actual == document()
    endpoints = {(method, path) for path, item in actual["paths"].items() for method in item}
    assert endpoints == {
        ("post", "/v1/sessions"),
        ("post", "/v1/sessions/{session_id}/turns"),
        ("get", "/v1/carts/{cart_id}"),
        ("put", "/v1/carts/{cart_id}/items/{sku}"),
        ("post", "/v1/carts/{cart_id}/quote"),
        ("post", "/v1/carts/{cart_id}/checkout"),
        ("get", "/health/live"),
        ("get", "/health/ready"),
        ("get", "/metrics"),
    }
    for path, item in actual["paths"].items():
        for method, operation in item.items():
            if path.startswith("/v1"):
                headers = {p["name"] for p in operation["parameters"] if p["in"] == "header"}
                assert "X-Correlation-ID" in headers
                assert ("Idempotency-Key" in headers) == (method != "get")
    schemas = actual["components"]["schemas"]
    assert (
        not {"Quote", "Product", "ProductHit", "ShoppingIntent", "OrderSnapshot", "OrderAccepted"}
        & schemas.keys()
    )
    assert schemas["TurnResponse"]["properties"]["products"]["items"]["$ref"].startswith(
        "catalog.yaml#"
    )


@pytest.mark.parametrize("bad", [1.5, "1", True, -1, 11])
def test_cart_quantity_strict_and_removal_allowed(bad):
    with pytest.raises(ValidationError):
        CartUpdateRequest(quantity=bad, expected_cart_version=1)
    assert CartUpdateRequest(quantity=0, expected_cart_version=1).quantity == 0


@pytest.mark.parametrize("bad", [False, "true", 1])
def test_checkout_requires_explicit_boolean_confirmation(bad):
    with pytest.raises(ValidationError):
        CheckoutRequest(
            quote_id=uid(4), expected_cart_version=1, confirmation_id=uid(7), confirmed=bad
        )


def test_conversation_input_bounds_and_extra_fields():
    assert TurnRequest(request_id=uid(1), text="hello").mode == "fixed"
    for changes in [
        {"text": "x" * 2001},
        {"mode": "autonomous"},
        {"request_id": "not-a-uuid"},
        {"user_id": "override"},
    ]:
        with pytest.raises(ValidationError):
            TurnRequest.model_validate({"request_id": uid(1), "text": "hello", **changes})


def test_cart_snapshot_null_display_money_uniqueness_and_utc():
    snapshot = {
        "cart_id": uid(5),
        "session_id": uid(2),
        "user_id": "p2-user",
        "version": 1,
        "lines": [{"sku": "FK-P2-001", "quantity": 1, "display_price_minor": None}],
        "updated_at": NOW,
    }
    assert CartSnapshot.model_validate(snapshot).lines[0].display_price_minor is None
    for changes in [
        {"updated_at": "2026-10-25T10:00:00"},
        {"updated_at": "2026-10-25T10:00:00+05:30"},
        {"lines": snapshot["lines"] * 2},
        {"lines": [{**snapshot["lines"][0], "display_price_minor": "123"}]},
    ]:
        with pytest.raises(ValidationError):
            CartSnapshot.model_validate({**snapshot, **changes})


def test_disabled_model_has_no_latency_sample():
    response = {
        "turn_id": uid(12),
        "response_text": "Synthetic clarification",
        "intent": None,
        "search_id": None,
        "products": [],
        "proposed_action": None,
        "outcome": "clarification",
        "extractor_source": "clarification",
        "llm_call_count": 0,
        "timings_ms": {"parse": 1, "llm": None, "search": 0, "compose": 1, "total": 2},
    }
    assert TurnResponse.model_validate(response).llm_call_count == 0
    response["timings_ms"]["llm"] = 0
    with pytest.raises(ValidationError):
        TurnResponse.model_validate(response)


def write_owner_contracts(root):
    """Synthetic merged-contract sandbox to exercise binding without editing owner paths."""
    target = root / "contracts/http"
    target.mkdir(parents=True, exist_ok=True)
    (target / "conversation.yaml").write_text(yaml.safe_dump(document()), encoding="utf-8")
    for provider in {endpoint.provider for endpoint in ENDPOINTS.values()}:
        paths = {}
        for name, endpoint in ENDPOINTS.items():
            if endpoint.provider != provider:
                continue
            operation = {
                "responses": {
                    str(endpoint.status): {
                        "content": {
                            "text/event-stream" if endpoint.stream else "application/json": {
                                "schema": RESPONSES[name]
                            }
                        }
                    }
                }
            }
            if name in REQUESTS:
                operation["requestBody"] = {
                    "content": {"application/json": {"schema": REQUESTS[name]}}
                }
            paths[endpoint.path] = {endpoint.method.lower(): operation}
        if provider == "transactions":
            for method, path in PARTICIPANTS:
                paths.setdefault(path, {})[method.lower()] = {}
        for path in ("/health/live", "/health/ready", "/metrics"):
            paths[path] = {"get": {}}
        doc = {
            "openapi": "3.1.0",
            "paths": paths,
            "components": {
                "schemas": {
                    "OrderSnapshot": RESPONSES["order_status"],
                    "ShoppingIntent": REQUESTS["search"]["properties"]["intent"],
                    "ProductHit": RESPONSES["search"]["properties"]["hits"]["items"],
                    "Quote": RESPONSES["quote"],
                    "OrderAccepted": RESPONSES["order_create"],
                }
            },
        }
        (target / (provider + ".yaml")).write_text(yaml.safe_dump(doc), encoding="utf-8")
    fixtures = root / "contracts/fixtures/p2"
    fixtures.mkdir(parents=True)
    (fixtures / "pairs.json").write_bytes((ROOT / "contracts/fixtures/p2/pairs.json").read_bytes())
    return OpenAPIContracts(target)


def test_clients_and_examples_bind_to_merged_owner_schema(tmp_path, pairs):
    contracts = write_owner_contracts(tmp_path)
    for pair in pairs.values():
        endpoint = ENDPOINTS[pair["endpoint"]]
        if pair["request"] is not None:
            contracts.validate(endpoint, "request", pair["request"])
        contracts.validate(endpoint, "response", pair["response"])
    checks = inspect_contracts(tmp_path)
    assert all(item["status"] == "PASS" for item in checks if item["name"].startswith("example:"))
    # Simulate provider drift. A formerly accepted example must fail compatibility.
    target = tmp_path / "contracts/http/catalog.yaml"
    doc = yaml.safe_load(target.read_text(encoding="utf-8"))
    schema = doc["paths"]["/v1/search"]["post"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ]
    schema["required"].append("provider_new_required_field")
    schema["properties"]["provider_new_required_field"] = {"type": "string"}
    target.write_text(yaml.safe_dump(doc), encoding="utf-8")
    checks = inspect_contracts(tmp_path)
    assert any(item["name"] == "example:five-hits" and item["status"] == "FAIL" for item in checks)


def test_external_schema_resolution_is_local_and_required(tmp_path, pairs):
    contracts = write_owner_contracts(tmp_path)
    base = (tmp_path / "contracts/http/conversation.yaml").as_uri()
    schema = {"$ref": "catalog.yaml#/components/schemas/Quote"}
    contracts.validate_schema(base, schema, pairs["changed-price-authoritative-quote"]["response"])
    with pytest.raises(ContractUnavailable):
        contracts.validate_schema(base, {"$ref": "https://invalid.test/remote.json"}, {})


def test_declared_schema_dialect_cannot_relax_wire_integer_types(tmp_path):
    directory = tmp_path / "contracts/http"
    directory.mkdir(parents=True)
    contracts = OpenAPIContracts(directory)
    schema = {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "integer"}
    for candidate in [schema, {"anyOf": [schema, {"type": "null"}]}]:
        with pytest.raises(ContractViolation):
            contracts.validate_schema("urn:p2:strict", candidate, 1.0)
        contracts.validate_schema("urn:p2:strict", candidate, 1)
    local_schema = tmp_path / "contracts/integer.schema.json"
    local_schema.write_text(json.dumps(schema), encoding="utf-8")
    base = (directory / "owner.yaml").as_uri()
    (directory / "owner.yaml").write_text("openapi: 3.1.0\n", encoding="utf-8")
    with pytest.raises(ContractViolation):
        contracts.validate_schema(base, {"$ref": "../integer.schema.json"}, 1.0)
    contracts.validate_schema(base, {"$ref": "../integer.schema.json"}, 1)
    with pytest.raises(ContractUnavailable, match="dialect"):
        contracts.validate_schema(
            "urn:p2:unsupported", {"$schema": "https://invalid.test/dialect", "type": "integer"}, 1
        )


def test_http_client_uses_merged_schema_binding(tmp_path, pairs, context):
    import asyncio

    import httpx

    from services.conversation.clients import CatalogClient, ProviderHTTP, TransportConfig

    from .doubles import ScriptedProvider

    write_owner_contracts(tmp_path)

    class ExplicitOwnerContractDouble(OpenAPIContracts):
        mode = "stub"

    contracts = ExplicitOwnerContractDouble(tmp_path / "contracts/http")
    double = ScriptedProvider((200, pairs["five-hits"]["response"]))

    async def run():
        config = TransportConfig(
            "http://explicit-owner-contract.test", mode="stub", purpose="contract_test"
        )
        async with ProviderHTTP(config, contracts, transport=httpx.MockTransport(double)) as http:
            return await CatalogClient(http).search(
                pairs["five-hits"]["request"], context, key="owner-schema"
            )

    assert asyncio.run(run()) == pairs["five-hits"]["response"]


def test_contracts_check_all_preserves_missing_handoffs_in_evidence(tmp_path, monkeypatch, capsys):
    # Run the real offline checker against real repo contracts; redirect evidence only.
    monkeypatch.setattr(artifacts, "ROOT", tmp_path)
    assert config.ROOT == ROOT
    assert main(["contracts", "check", "--all"]) == 4
    output = json.loads(capsys.readouterr().out)
    assert output["test_mode"] == "offline"
    assert any(
        "MISSING: contracts/http/catalog.yaml (Harsh)" in reason for reason in output["reasons"]
    )
    assert any(
        "MISSING: contracts/http/transactions.yaml (Aditya)" in reason
        for reason in output["reasons"]
    )
    assert any(
        "MISSING: contracts/http/analytics.yaml (Vichitr)" in reason for reason in output["reasons"]
    )
    evidence = tmp_path / output["evidence_dir"]
    assert (evidence / "summary.json").is_file()
    manifest = json.loads((evidence / "manifest.json").read_text())
    assert manifest["correctness_passed"] is None
    assert all(
        metric["status"] == "NOT_RUN" and metric["value"] is None for metric in output["metrics"]
    )
