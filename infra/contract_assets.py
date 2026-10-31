"""Rebuild owned contract assets: python -m infra.contract_assets."""

import copy
import hashlib
import json
from pathlib import Path

import yaml

from shared.contracts import analytics, events
from shared.contracts.common import ErrorResponse

ROOT = Path(__file__).resolve().parents[1]


def canonical(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def draft7(value):
    if isinstance(value, list):
        return [draft7(child) for child in value]
    if not isinstance(value, dict):
        return value
    return {
        "definitions" if key == "$defs" else key: (
            child.replace("#/$defs/", "#/definitions/") if key == "$ref" else draft7(child)
        )
        for key, child in value.items()
    }


def event_schemas():
    domains = sorted({item[0] for item in events.EVENTS.values()})
    schemas = {}
    for domain in domains:
        schema = events.EventEnvelope.model_json_schema()
        definitions = schema.setdefault("$defs", {})
        branches = []
        for name, (topic, owner, aggregate, key, model) in events.EVENTS.items():
            if topic != domain:
                continue
            payload = model.model_json_schema()
            definitions.update(payload.pop("$defs", {}))
            definitions[model.__name__] = payload
            properties = {
                "event_type": {"const": name},
                "payload": {"$ref": f"#/$defs/{model.__name__}"},
                "source_service": {"enum": [owner, "benchmark"]},
                "aggregate_type": {"const": aggregate},
            }
            if key == "session_id":
                properties.update(session_id={"type": "string"}, user_id={"type": "string"})
            linked = domain != "conversation-events" or name in ("ADD_TO_CART", "CHECKOUT_STARTED")
            meta = {"dataset_revision": {"type": "string"}} if linked else {}
            if domain in ("order-events", "inventory-events", "payment-events"):
                meta.update(
                    synthetic={"const": True}, scenario_source={"enum": ["simulation", "benchmark"]}
                )
            if meta:
                properties["metadata"] = {"properties": meta, "required": list(meta)}
            # Constants also expose state/type mismatches to non-Python consumers.
            payload_properties = {}
            if name.startswith("ORDER_"):
                payload_properties["order_status"] = {
                    "const": {
                        "ORDER_CREATED": "PENDING",
                        "ORDER_CONFIRMED": "CONFIRMED",
                        "ORDER_CANCELLED": "CANCELLED",
                    }[name]
                }
            if name.startswith("PAYMENT_"):
                payload_properties["status"] = {"const": name.removeprefix("PAYMENT_")}
            if payload_properties:
                properties["payload"] = {
                    "allOf": [properties["payload"], {"properties": payload_properties}]
                }
            branches.append({"properties": properties})
        schema["properties"]["event_type"] = {
            "enum": [name for name, item in events.EVENTS.items() if item[0] == domain]
        }
        schema["oneOf"] = branches
        schema["allOf"] = [
            {
                "if": {"properties": {"source_service": {"const": "benchmark"}}},
                "then": {
                    "properties": {
                        "namespace": {"pattern": "^bench-"},
                        "metadata": {
                            "properties": {
                                "synthetic": {"const": True},
                                "scenario_source": {"const": "benchmark"},
                            },
                            "required": ["synthetic", "scenario_source"],
                        },
                    }
                },
            }
        ]
        schemas[domain] = draft7(schema)
    schemas["dead-letter"] = draft7(events.DlqNotice.model_json_schema())
    for domain, schema in schemas.items():
        schema["$schema"] = "http://json-schema.org/draft-07/schema#"
        schema["$id"] = f"urn:group3:{domain}:v1"
        schema["properties"]["schema_version"]["type"] = "integer"
    return schemas


def analytics_openapi():
    schemas = {}
    for model in (
        analytics.DatasetManifest,
        analytics.GoldQueryResult,
        analytics.ReceiptPage,
        analytics.QuarantinePage,
        analytics.ReplayRequest,
        analytics.ReplayAccepted,
        analytics.ReplayStatus,
        ErrorResponse,
    ):
        schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
        schemas.update(schema.pop("$defs", {}))
        schemas[model.__name__] = schema

    def parameter(name, location="query", required=True, schema=None):
        return {
            "name": name,
            "in": location,
            "required": required,
            "schema": schema or {"type": "string", "minLength": 1},
        }

    namespace = parameter(
        "namespace",
        schema={"type": "string", "pattern": r"^(dev|(?:bench|replay)-[a-z0-9-]{1,54})$"},
    )
    limit = parameter(
        "limit",
        required=False,
        schema={"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
    )
    paths = {}

    def operation(path, method, name, result, *, params=(), internal=False, body=None, status=200):
        response_schema = {"$ref": f"#/components/schemas/{result}"}
        responses = {
            str(status): {
                "description": "Success",
                "content": {"application/json": {"schema": response_schema}},
            }
        }
        for code in (400, 401, 403, 404, 409, 422, 429, 503):
            responses[str(code)] = {
                "description": "Common error",
                "content": {
                    "application/json": {"schema": {"$ref": "#/components/schemas/ErrorResponse"}}
                },
            }
        op = {"operationId": name, "parameters": list(params), "responses": responses}
        if internal:
            op["security"] = [{"ServiceToken": []}]
        if body:
            op["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {"schema": {"$ref": f"#/components/schemas/{body}"}}
                },
            }
        paths[path] = {method: op}

    operation(
        "/v1/analytics/manifests/{dataset}/active",
        "get",
        "active_manifest",
        "DatasetManifest",
        params=[parameter("dataset", "path", schema={"enum": ["silver", "gold"]}), namespace],
    )
    operation(
        "/v1/analytics/gold/{table}",
        "get",
        "gold",
        "GoldQueryResult",
        params=[
            parameter(
                "table",
                "path",
                schema={
                    "enum": [
                        "pipeline_minute",
                        "order_fact",
                        "daily_conversion",
                        "checkout_funnel",
                        "payment_failures",
                        "inventory_failures",
                        "search_performance",
                        "intent_accuracy",
                        "retrieval_quality",
                    ]
                },
            ),
            namespace,
            parameter("date_from", schema={"type": "string", "format": "date"}),
            parameter("date_to", schema={"type": "string", "format": "date"}),
            parameter("currency", required=False, schema={"const": "INR"}),
        ],
    )
    operation(
        "/internal/v1/analytics/receipts",
        "get",
        "receipts",
        "ReceiptPage",
        params=[namespace, parameter("after_cursor", required=False), limit],
        internal=True,
    )
    operation(
        "/internal/v1/analytics/quarantine",
        "get",
        "quarantine",
        "QuarantinePage",
        params=[namespace, parameter("cursor", required=False), limit],
        internal=True,
    )
    operation(
        "/internal/v1/analytics/replays",
        "post",
        "replay_create",
        "ReplayAccepted",
        params=[
            parameter("X-Namespace", "header"),
            parameter("X-Run-ID", "header"),
            parameter("X-Correlation-ID", "header"),
            parameter(
                "Idempotency-Key",
                "header",
                schema={"type": "string", "minLength": 1, "maxLength": 128},
            ),
        ],
        internal=True,
        body="ReplayRequest",
        status=202,
    )
    operation(
        "/internal/v1/analytics/replays/{replay_id}",
        "get",
        "replay_status",
        "ReplayStatus",
        params=[parameter("replay_id", "path", schema={"type": "string", "format": "uuid"})],
        internal=True,
    )
    for path in ("/health/live", "/health/ready"):
        paths[path] = {
            "get": {
                "responses": {
                    "200": {"description": "Healthy"},
                    "503": {"description": "Not ready"},
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
            "title": "Analytics API",
            "version": "1.0.0",
            "description": "M02 executable contract proposal; no running API is implied. "
            "Pagination, receipt extensions and token binding await G0 consumer review. "
            "Gold date_from is inclusive; date_to is exclusive. Queries pin active files.",
        },
        "servers": [{"url": "http://analytics:8006"}],
        "paths": paths,
        "components": {
            "schemas": schemas,
            "securitySchemes": {
                "ServiceToken": {
                    "type": "http",
                    "scheme": "bearer",
                    "description": "Proposed environment-provided internal service token binding.",
                }
            },
        },
    }


def assets():
    output = {}
    entries = []
    for domain, schema in event_schemas().items():
        path = f"contracts/events/{domain}.v1.schema.json"
        output[path] = json.dumps(schema, indent=2, ensure_ascii=False) + "\n"
        entries.append(
            {
                "subject": f"{domain}.v1-value",
                "schema_path": path,
                "sha256": hashlib.sha256(canonical(schema)).hexdigest(),
            }
        )
    output["contracts/events/manifest.json"] = (
        json.dumps(
            {
                "schema_version": 1,
                "compatibility": "BACKWARD_TRANSITIVE",
                "hash_encoding": "sorted compact UTF-8 JSON",
                "review_status": "PENDING_PRODUCER_CONSUMER_REVIEW",
                "schemas": entries,
            },
            indent=2,
        )
        + "\n"
    )
    output["contracts/dictionaries/events/reasons.v1.json"] = (
        json.dumps(
            {
                "version": 1,
                "source": "docs/specs/02_COMMON_SPEC.md §12",
                "reason_codes": list(events.ReasonCode),
            },
            indent=2,
        )
        + "\n"
    )
    output["contracts/http/analytics.yaml"] = yaml.safe_dump(
        copy.deepcopy(analytics_openapi()), sort_keys=False, allow_unicode=True
    )
    return output


if __name__ == "__main__":
    for path, content in assets().items():
        (ROOT / path).write_text(content, encoding="utf-8", newline="\n")
