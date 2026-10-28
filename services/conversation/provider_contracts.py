"""Consume owner OpenAPI schemas. Never load provisional examples in production."""

import json
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.validators import extend
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

StrictValidator = extend(
    Draft202012Validator,
    type_checker=Draft202012Validator.TYPE_CHECKER.redefine(
        "integer", lambda checker, value: type(value) is int
    ),
)


class ContractUnavailable(RuntimeError):
    pass


class ContractViolation(ValueError):
    pass


@dataclass(frozen=True)
class Endpoint:
    provider: str
    method: str
    path: str
    status: int
    internal: bool = False
    stream: bool = False


ENDPOINTS = {
    "search": Endpoint("catalog", "POST", "/v1/search", 200),
    "facets": Endpoint("catalog", "GET", "/v1/catalog/facets", 200),
    "product": Endpoint("catalog", "GET", "/v1/products/{sku}", 200),
    "quote": Endpoint("catalog", "POST", "/v1/quotes", 201),
    "quote_lookup": Endpoint("catalog", "GET", "/internal/v1/quotes/{quote_id}", 200, True),
    "price": Endpoint("catalog", "POST", "/internal/v1/catalog/{sku}/price", 200, True),
    "order_create": Endpoint("transactions", "POST", "/v1/orders", 202),
    "order_status": Endpoint("transactions", "GET", "/v1/orders/{order_id}", 200),
    "order_events": Endpoint(
        "transactions", "GET", "/v1/orders/{order_id}/events", 200, stream=True
    ),
    "active_manifest": Endpoint(
        "analytics", "GET", "/v1/analytics/manifests/{dataset}/active", 200
    ),
    "gold": Endpoint("analytics", "GET", "/v1/analytics/gold/{table}", 200),
    "receipts": Endpoint("analytics", "GET", "/internal/v1/analytics/receipts", 200, True),
    "replay_create": Endpoint("analytics", "POST", "/internal/v1/analytics/replays", 202, True),
    "replay_status": Endpoint(
        "analytics", "GET", "/internal/v1/analytics/replays/{replay_id}", 200, True
    ),
    "quarantine": Endpoint("analytics", "GET", "/internal/v1/analytics/quarantine", 200, True),
}


class OpenAPIContracts:
    """Resolve local OpenAPI 3.1 JSON Schemas; no network schema resolution.

    SSE snapshots bind to the provider's canonical OrderSnapshot schema.
    Unsupported/missing schema bindings fail closed. No inferred field renames.
    """

    mode = "real"

    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.schema_root = self.directory.parent
        self.registry = Registry(retrieve=self._resource)

    def _document(self, path):
        try:
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or not str(value.get("openapi", "")).startswith("3.1."):
                raise ValueError
            self._dialects(value)
            return value
        except (OSError, ValueError, yaml.YAMLError) as exc:
            raise ContractUnavailable("owner OpenAPI 3.1 contract unavailable") from exc

    def _dialects(self, value):
        allowed = {
            "https://json-schema.org/draft/2020-12/schema",
            "https://spec.openapis.org/oas/3.1/dialect/base",
        }
        if isinstance(value, dict):
            for field in ("$schema", "jsonSchemaDialect"):
                if field in value and (
                    not isinstance(value[field], str) or value[field] not in allowed
                ):
                    raise ContractUnavailable("owner schema dialect requires a reviewed binding")

    def _wire_schema(self, schema):
        """Retain the strict integer checker when jsonschema evolves through refs.

        A supported $schema would otherwise select the stock validator class,
        whose mathematical integer definition accepts 1.0. Dialect metadata is
        checked, then removed from the in-memory validation copy only.
        """
        if isinstance(schema, bool):
            return schema
        if not isinstance(schema, dict):
            raise ContractUnavailable("owner schema is not an object or Boolean")
        self._dialects(schema)
        result = {key: value for key, value in schema.items() if key != "$schema"}
        for key in ("properties", "patternProperties", "$defs", "definitions", "dependentSchemas"):
            if key in result:
                result[key] = {
                    name: self._wire_schema(value) for name, value in result[key].items()
                }
        for key in ("allOf", "anyOf", "oneOf", "prefixItems"):
            if key in result:
                result[key] = [self._wire_schema(value) for value in result[key]]
        for key in (
            "items",
            "additionalProperties",
            "unevaluatedProperties",
            "propertyNames",
            "contains",
            "not",
            "if",
            "then",
            "else",
            "unevaluatedItems",
            "contentSchema",
        ):
            if key in result:
                result[key] = self._wire_schema(result[key])
        return result

    def _openapi_copy(self, value):
        if isinstance(value, list):
            return [self._openapi_copy(child) for child in value]
        if not isinstance(value, dict):
            return value
        result = {}
        for key, child in value.items():
            if key == "schema":
                result[key] = self._wire_schema(child)
            elif key == "schemas":
                result[key] = {name: self._wire_schema(item) for name, item in child.items()}
            elif key in {"example", "examples", "default", "enum", "const"}:
                result[key] = child
            else:
                result[key] = self._openapi_copy(child)
        return result

    def _resource(self, uri):
        parsed = urlparse(uri)
        if parsed.scheme != "file":
            raise ContractUnavailable("only repository-local schema references are supported")
        path_text = unquote(parsed.path)
        if len(path_text) > 2 and path_text[0] == "/" and path_text[2] == ":":
            path_text = path_text[1:]
        path = Path(path_text).resolve()
        if not path.is_relative_to(self.schema_root):
            raise ContractUnavailable("schema reference escapes the owner contract directory")
        try:
            contents = yaml.safe_load(path.read_text(encoding="utf-8"))
            if not isinstance(contents, (dict, bool)):
                raise ValueError
            self._dialects(contents)
            if isinstance(contents, dict) and "openapi" in contents:
                contents = self._openapi_copy(contents)
            else:
                contents = self._wire_schema(contents)
            return Resource.from_contents(contents, default_specification=DRAFT202012)
        except (OSError, ValueError, yaml.YAMLError) as exc:
            raise ContractUnavailable("local owner schema unavailable") from exc

    def operation(self, endpoint):
        document = self._document(self.directory / (endpoint.provider + ".yaml"))
        try:
            return document["paths"][endpoint.path][endpoint.method.lower()]
        except (KeyError, TypeError) as exc:
            raise ContractUnavailable("owner endpoint contract unavailable") from exc

    def validate(self, endpoint, direction, value):
        operation = self.operation(endpoint)
        try:
            if direction == "request":
                schema = operation["requestBody"]["content"]["application/json"]["schema"]
            elif endpoint.stream:
                schema = {"$ref": "#/components/schemas/OrderSnapshot"}
            else:
                schema = operation["responses"][str(endpoint.status)]["content"][
                    "application/json"
                ]["schema"]
        except (KeyError, TypeError) as exc:
            raise ContractUnavailable("owner body schema unavailable") from exc
        uri = (self.directory / (endpoint.provider + ".yaml")).as_uri()
        self.validate_schema(uri, schema, value)

    def validate_schema(self, uri, schema, value):
        try:
            # JSON round-trip rejects NaN/infinity, non-JSON Python values and coerced money.
            json.dumps(value, allow_nan=False)
            schema = self._wire_schema(schema)
            # Keep local fragment refs anchored to the entire OpenAPI document,
            # rather than to an extracted response schema with no components.
            root = {}
            if uri.startswith("file:"):
                root = dict(self._resource(uri).contents)
            validator = StrictValidator(
                {**root, "$id": uri, "allOf": [schema]},
                registry=self.registry,
                format_checker=FormatChecker(),
            )
            errors = list(validator.iter_errors(value))
            if errors:
                raise ContractViolation(
                    "payload violates owner schema at "
                    + "/".join(map(str, errors[0].absolute_path))
                )
        except (ContractViolation, ContractUnavailable):
            raise
        except (ValueError, TypeError) as exc:
            raise ContractViolation("payload is not finite JSON") from exc
        except Exception as exc:
            raise ContractUnavailable("owner schema reference unavailable or unsupported") from exc
