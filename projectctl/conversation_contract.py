"""Generate/check Jaineel's OpenAPI 3.1 contract without implementing the service."""

import argparse
from pathlib import Path

import yaml

from shared.contracts.common import ErrorResponse
from shared.contracts.conversation import (
    CartQuoteRequest,
    CartSnapshot,
    CartUpdateRequest,
    CheckoutRequest,
    SessionCreated,
    TurnRequest,
    TurnResponse,
)

ROOT = Path(__file__).resolve().parents[1]


def document():
    schemas = {}
    for model in (
        ErrorResponse,
        SessionCreated,
        TurnRequest,
        TurnResponse,
        CartSnapshot,
        CartUpdateRequest,
        CartQuoteRequest,
        CheckoutRequest,
    ):
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        schemas.update(schema.pop("$defs", {}))
        schemas[model.__name__] = schema
    schemas["TurnResponse"]["properties"]["intent"] = {
        "anyOf": [{"$ref": "catalog.yaml#/components/schemas/ShoppingIntent"}, {"type": "null"}]
    }
    schemas["TurnResponse"]["properties"]["products"]["items"] = {
        "$ref": "catalog.yaml#/components/schemas/ProductHit"
    }
    schemas["CheckoutRequest"]["properties"]["confirmed"] = {"type": "boolean", "const": True}
    headers = [
        {
            "name": name,
            "in": "header",
            "required": True,
            "schema": {"type": "string", "minLength": 1},
        }
        for name in ("X-Namespace", "X-Run-ID", "X-User-ID", "X-Correlation-ID", "X-Request-ID")
    ]
    paths = {}
    rows = [
        ("/v1/sessions", "post", "create_session", None, "201", "SessionCreated"),
        (
            "/v1/sessions/{session_id}/turns",
            "post",
            "submit_turn",
            "TurnRequest",
            "200",
            "TurnResponse",
        ),
        ("/v1/carts/{cart_id}", "get", "get_cart", None, "200", "CartSnapshot"),
        (
            "/v1/carts/{cart_id}/items/{sku}",
            "put",
            "update_cart",
            "CartUpdateRequest",
            "200",
            "CartSnapshot",
        ),
        (
            "/v1/carts/{cart_id}/quote",
            "post",
            "quote_cart",
            "CartQuoteRequest",
            "201",
            "catalog.yaml#/components/schemas/Quote",
        ),
        (
            "/v1/carts/{cart_id}/checkout",
            "post",
            "checkout_cart",
            "CheckoutRequest",
            "202",
            "transactions.yaml#/components/schemas/OrderAccepted",
        ),
    ]
    for path, method, operation, request, status, response in rows:
        parameters = [dict(item) for item in headers]
        for name in ("session_id", "cart_id", "sku"):
            if "{" + name + "}" in path:
                parameters.append(
                    {
                        "name": name,
                        "in": "path",
                        "required": True,
                        "schema": {
                            "type": "string",
                            **(
                                {"format": "uuid"}
                                if name != "sku"
                                else {"pattern": "^[!-~]{1,64}$"}
                            ),
                        },
                    }
                )
        if method != "get":
            parameters.append(
                {
                    "name": "Idempotency-Key",
                    "in": "header",
                    "required": True,
                    "schema": {"type": "string", "minLength": 1, "maxLength": 128},
                }
            )
        ref = response if ".yaml#" in response else "#/components/schemas/" + response
        value = {
            "operationId": operation,
            "parameters": parameters,
            "responses": {
                status: {
                    "description": "Accepted contract response",
                    "content": {"application/json": {"schema": {"$ref": ref}}},
                }
            },
        }
        for error in ("400", "401", "403", "404", "409", "422", "429", "503"):
            value["responses"][error] = {
                "description": "Common error; never a success-shaped fallback",
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}
                },
            }
        if request:
            body = {"$ref": "#/components/schemas/" + request}
        else:
            body = {"type": "object", "additionalProperties": False, "maxProperties": 0}
        if method != "get":
            value["requestBody"] = {
                "required": True,
                "content": {"application/json": {"schema": body}},
            }
        paths[path] = {method: value}
    for kind in ("live", "ready"):
        paths["/health/" + kind] = {
            "get": {
                "responses": {
                    "200": {"description": "Healthy"},
                    "503": {"description": "Unavailable"},
                }
            }
        }
    paths["/metrics"] = {
        "get": {
            "responses": {
                "200": {
                    "description": "Prometheus metrics",
                    "content": {"text/plain": {"schema": {"type": "string"}}},
                }
            }
        }
    }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Conversation API",
            "version": "1.0.0",
            "description": (
                "P2 contract only. External provider schemas and proposed identity header "
                "bindings require G0 review. No running service is implied."
            ),
        },
        "servers": [{"url": "http://conversation:8001"}],
        "paths": paths,
        "components": {"schemas": schemas},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    target = ROOT / "contracts/http/conversation.yaml"
    expected = document()
    if args.check:
        if not target.is_file() or yaml.safe_load(target.read_text(encoding="utf-8")) != expected:
            print("conversation OpenAPI is missing or differs from its owned DTOs/generator")
            return 3
        print("conversation OpenAPI current; external provider references require owner review")
    else:
        target.write_text(
            yaml.safe_dump(expected, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
