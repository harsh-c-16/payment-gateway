"""Pinned schema catalogue and pure wire validation; broker transport is M03."""

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from jsonschema import Draft7Validator, FormatChecker
from jsonschema.validators import extend
from pydantic import ValidationError

from shared.contracts.events import DlqNotice, EventEnvelope, ReasonCode, RegisteredRecord

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "contracts/events/manifest.json"
StrictValidator = extend(
    Draft7Validator,
    type_checker=Draft7Validator.TYPE_CHECKER.redefine(
        "integer", lambda checker, value: type(value) is int
    ),
)


def canonical_json(value):
    return json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def schema_hash(value):
    return hashlib.sha256(canonical_json(value)).hexdigest()


class SchemaUnavailable(RuntimeError):
    """A required schema/mapping cannot be verified; do not claim readiness."""


class RecordInvalid(ValueError):
    def __init__(self, reason, path=None):
        self.reason = ReasonCode(reason)
        self.path = path
        super().__init__(self.reason.value)


def documents():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    result = {}
    for entry in manifest["schemas"]:
        schema = json.loads((ROOT / entry["schema_path"]).read_text(encoding="utf-8"))
        if schema_hash(schema) != entry["sha256"]:
            raise SchemaUnavailable("Repository schema checksum mismatch")
        Draft7Validator.check_schema(schema)
        result[entry["subject"]] = (entry, schema)
    if len(result) != 6:
        raise SchemaUnavailable("All five domain schemas and DLQ schema are required")
    return result


def register_schemas(client: httpx.Client, cache_path: Path):
    """Register only checked-in definitions; cache mappings after all read-backs pass."""
    entries = []
    for subject, (entry, schema) in documents().items():
        response = client.put(f"/config/{subject}", json={"compatibility": "BACKWARD_TRANSITIVE"})
        response.raise_for_status()
        response = client.post(
            f"/subjects/{subject}/versions",
            json={"schemaType": "JSON", "schema": canonical_json(schema).decode()},
        )
        response.raise_for_status()
        identity = response.json()["id"]
        response = client.get(f"/schemas/ids/{identity}")
        response.raise_for_status()
        if (
            response.json().get("schemaType") != "JSON"
            or schema_hash(json.loads(response.json()["schema"])) != entry["sha256"]
        ):
            raise SchemaUnavailable("Registered schema does not match repository checksum")
        response = client.get(f"/subjects/{subject}/versions/latest")
        response.raise_for_status()
        latest = response.json()
        if latest["id"] != identity:
            raise SchemaUnavailable("Subject latest ID does not match registered definition")
        entries.append({**entry, "id": identity, "version": latest["version"], "schema": schema})
    manifest = {"compatibility": "BACKWARD_TRANSITIVE", "schemas": entries}
    SchemaCache(manifest)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    temporary.replace(cache_path)
    return manifest


@dataclass(frozen=True)
class CheckedRecord:
    envelope: RegisteredRecord
    document: dict
    schema_id: int
    canonical_content_hash: str


class SchemaCache:
    """Offline operation trusts only IDs whose cached content matches repo pins."""

    def __init__(self, manifest):
        expected = documents()
        if manifest.get("compatibility") != "BACKWARD_TRANSITIVE":
            raise SchemaUnavailable("Wrong cached compatibility policy")
        self.entries, self.validators = {}, {}
        for entry in manifest["schemas"]:
            subject, identity = entry["subject"], entry["id"]
            if subject not in expected or type(identity) is not int or identity < 1:
                raise SchemaUnavailable("Unknown subject or invalid cached ID")
            if subject in self.entries or identity in self.validators:
                raise SchemaUnavailable("Duplicate schema subject or ID")
            pin = expected[subject][0]["sha256"]
            if entry["sha256"] != pin or schema_hash(entry["schema"]) != pin:
                raise SchemaUnavailable("Cached schema checksum mismatch")
            self.entries[subject] = entry
            # Remove only dialect metadata so nested refs retain strict integer checks.
            schema = {key: value for key, value in entry["schema"].items() if key != "$schema"}
            self.validators[identity] = StrictValidator(schema, format_checker=FormatChecker())
        if self.entries.keys() != expected.keys():
            raise SchemaUnavailable("Incomplete cached schema mapping")

    @classmethod
    def load(cls, path):
        try:
            return cls(json.loads(Path(path).read_text(encoding="utf-8")))
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise SchemaUnavailable("Verified registry mapping is missing or malformed") from exc

    def verify_online(self, client):
        for subject, entry in self.entries.items():
            config = client.get(f"/config/{subject}")
            config.raise_for_status()
            if config.json()["compatibilityLevel"] != "BACKWARD_TRANSITIVE":
                raise SchemaUnavailable("Subject compatibility policy differs")
            response = client.get(f"/subjects/{subject}/versions/{entry['version']}")
            response.raise_for_status()
            item = response.json()
            if (
                item["id"] != entry["id"]
                or item.get("schemaType") != "JSON"
                or schema_hash(json.loads(item["schema"])) != entry["sha256"]
            ):
                raise SchemaUnavailable("Registry subject/ID/hash mapping differs")
        return [
            {key: value for key, value in entry.items() if key != "schema"}
            for entry in self.entries.values()
        ]

    def validate(self, raw_bytes, headers, topic, key, *, ingested_at: datetime | None = None):
        if not isinstance(raw_bytes, bytes) or len(raw_bytes) > 65536:
            raise RecordInvalid(ReasonCode.INVALID_TYPE)
        try:
            text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RecordInvalid(ReasonCode.INVALID_UTF8) from exc

        def unique_object(pairs):
            result = {}
            for name, value in pairs:
                if name in result:
                    raise ValueError("duplicate JSON member")
                result[name] = value
            return result

        def invalid_constant(value):
            raise ValueError("nonfinite JSON number")

        def finite_float(value):
            number = float(value)
            if not math.isfinite(number):
                raise ValueError("nonfinite JSON number")
            return number

        try:
            doc = json.loads(
                text,
                object_pairs_hook=unique_object,
                parse_constant=invalid_constant,
                parse_float=finite_float,
            )
        except (ValueError, RecursionError) as exc:
            raise RecordInvalid(ReasonCode.INVALID_JSON) from exc
        if not isinstance(doc, dict):
            raise RecordInvalid(ReasonCode.INVALID_TYPE)
        if "schema_version" not in doc:
            raise RecordInvalid(ReasonCode.MISSING_REQUIRED, "schema_version")
        if type(doc.get("schema_version")) is not int or doc["schema_version"] != 1:
            raise RecordInvalid(ReasonCode.UNSUPPORTED_SCHEMA, "schema_version")
        if not isinstance(topic, str) or not topic:
            raise RecordInvalid(ReasonCode.KEY_MISMATCH, "topic")
        if topic.endswith(".dead-letter.v1"):
            model, domain = DlqNotice, "dead-letter"
        else:
            from shared.contracts.events import EVENTS

            if "event_type" not in doc:
                raise RecordInvalid(ReasonCode.MISSING_REQUIRED, "event_type")
            if not isinstance(doc.get("event_type"), str) or doc["event_type"] not in EVENTS:
                raise RecordInvalid(ReasonCode.UNKNOWN_EVENT_TYPE, "event_type")
            model, domain = EventEnvelope, EVENTS[doc["event_type"]][0]
        if not isinstance(headers, (list, tuple)) or any(
            not isinstance(header, (list, tuple))
            or len(header) != 2
            or not isinstance(header[0], str)
            for header in headers
        ):
            raise RecordInvalid(ReasonCode.INVALID_TYPE, "headers")
        relevant = [
            (name, value) for name, value in headers if name in ("content-type", "schema-id")
        ]
        header_map = dict(relevant)
        if (
            len(relevant) != 2
            or len(header_map) != 2
            or header_map.get("content-type") != b"application/json"
        ):
            raise RecordInvalid(ReasonCode.INVALID_TYPE, "headers")
        identity_bytes = header_map["schema-id"]
        if (
            not isinstance(identity_bytes, bytes)
            or not identity_bytes.isdigit()
            or len(identity_bytes) > 10
        ):
            raise RecordInvalid(ReasonCode.UNSUPPORTED_SCHEMA, "schema-id")
        identity = int(identity_bytes)
        if identity not in self.validators:
            raise RecordInvalid(ReasonCode.UNSUPPORTED_SCHEMA, "schema-id")
        if self.entries[f"{domain}.v1-value"]["id"] != identity:
            raise RecordInvalid(ReasonCode.SCHEMA_ID_MISMATCH, "schema-id")
        error = next(self.validators[identity].iter_errors(doc), None)
        if error:
            if error.validator == "oneOf":
                branches = self.entries[f"{domain}.v1-value"]["schema"]["oneOf"]
                selected = next(
                    index
                    for index, branch in enumerate(branches)
                    if branch["properties"]["event_type"]["const"] == doc["event_type"]
                )
                error = next(child for child in error.context if child.schema_path[0] == selected)
            while error.context:
                error = error.context[0]
            path = ".".join(str(part) for part in error.absolute_path)
            reason = ReasonCode.INVALID_TYPE
            if error.validator == "required":
                reason = ReasonCode.MISSING_REQUIRED
            elif any(
                part
                in ("event_time", "produced_at", "created_at", "changed_at", "attempt_created_at")
                for part in error.absolute_path
            ):
                reason = ReasonCode.INVALID_TIMESTAMP
            elif any(
                part in ("amount_minor", "total_amount_minor", "price_minor")
                for part in error.absolute_path
            ):
                reason = ReasonCode.INVALID_AMOUNT
            elif "quantity_after" in error.absolute_path:
                reason = ReasonCode.INVALID_QUANTITY
            raise RecordInvalid(reason, path)
        try:
            record = model.model_validate(doc)
        except ValidationError as exc:
            raise RecordInvalid(ReasonCode.INVARIANT_VIOLATION) from exc
        if record.topic() != topic or record.kafka_key().encode("utf-8") != key:
            raise RecordInvalid(ReasonCode.KEY_MISMATCH)
        if isinstance(record, EventEnvelope) and ingested_at is not None:
            if record.event_time > ingested_at + timedelta(seconds=5):
                raise RecordInvalid(ReasonCode.FUTURE_TIMESTAMP, "event_time")
        return CheckedRecord(record, doc, identity, schema_hash(doc))
