"""Executable offline provider checks with explicit, byte-pinned review receipts.

Compatibility is checked on every invocation. A review cannot turn a failed
validator into a pass, and a validator alone cannot invent an owner's approval.
"""

import hashlib
import importlib
import inspect
import json
from pathlib import Path

from jsonschema.validators import validator_for

from projectctl.artifacts import canonical_json, file_hash

SURFACES = {
    "shared/outbox": ("Aditya", {"append_outbox": ("db_transaction", "event"), "OutboxRelay": ()}),
    "shared/event_transport": (
        "Vichitr",
        {
            "build_event": ("event_type", "payload", "context"),
            "validate_event": ("raw_bytes",),
            "KafkaPublisher": (),
            "ConsumerGroup": (),
        },
    ),
    "shared/local_diagnostics": (
        "Vichitr",
        {"quarantine_local_diagnostic": ("db_transaction", "diagnostic")},
    ),
    "contracts/events": ("Vichitr", None),
    "contracts/data/catalog": ("Harsh", None),
    "contracts/dictionaries/catalog": ("Harsh", None),
}


def references(root, surface):
    """Pin the complete executable/schema surface, including SQL templates."""
    return [
        {"path": p.relative_to(root).as_posix(), "sha256": file_hash(p)}
        for p in sorted((root / surface).rglob("*"))
        if p.is_file() and p.suffix in {".py", ".sql", ".json"}
    ]


def validate_surface(root, surface):
    _, exports = SURFACES[surface]
    if exports is not None:
        module = importlib.import_module(surface.replace("/", "."))
        if Path(module.__file__).resolve() != (root / surface / "__init__.py").resolve():
            raise ValueError("validator imported a different provider checkout")
        for name, parameters in exports.items():
            callback = getattr(module, name)
            if (
                not callable(callback)
                or not set(parameters) <= inspect.signature(callback).parameters.keys()
            ):
                raise ValueError("provider public signature changed")
    elif surface == "contracts/events":
        manifest = json.loads((root / surface / "manifest.json").read_text("utf-8"))
        subjects = set()
        for entry in manifest["schemas"]:
            path = (root / entry["schema_path"]).resolve()
            if not path.is_relative_to((root / surface).resolve()):
                raise ValueError("event schema escapes its contract directory")
            schema = json.loads(path.read_text("utf-8"))
            validator_for(schema).check_schema(schema)
            if hashlib.sha256(canonical_json(schema)).hexdigest() != entry["sha256"]:
                raise ValueError("event schema differs from owner manifest")
            if entry["subject"] in subjects:
                raise ValueError("duplicate event subject")
            subjects.add(entry["subject"])
        if len(subjects) != 6 or manifest["compatibility"] != "BACKWARD_TRANSITIVE":
            raise ValueError("five domain schemas and DLQ with declared compatibility required")
    elif surface == "contracts/data/catalog":
        schemas = list((root / surface).glob("*.schema.json"))
        if not schemas:
            raise ValueError("catalogue schemas missing")
        for path in schemas:
            schema = json.loads(path.read_text("utf-8"))
            validator_for(schema).check_schema(schema)
    else:
        dictionary = json.loads((root / surface / "flipkart-v1.json").read_text("utf-8"))
        if (
            dictionary["dictionary_version"] != "flipkart-v1"
            or len(dictionary["source_header"]) != 15
            or len(set(dictionary["source_header"])) != 15
            or len(set(dictionary["roots"])) != 32
            or dictionary["bounds"]["price_minor_max"] != 1_000_000_000
        ):
            raise ValueError("catalogue dictionary differs from frozen interface")


def inspect_surface(root, surface, *, review=None):
    owner, _ = SURFACES[surface]
    refs = references(root, surface)
    result = {
        "name": surface,
        "owner": owner,
        "status": "MISSING",
        "detail": "provider surface absent",
        "validation": "NOT_RUN",
    }
    if not refs:
        return result
    try:
        validate_surface(root, surface)
    except Exception as exc:
        return result | {
            "status": "FAIL",
            "validation": "FAIL",
            "detail": "offline provider validation failed: " + type(exc).__name__,
        }
    result.update(
        status="UNREVIEWED",
        validation="PASS",
        detail="offline compatibility passed; byte-pinned owner/consumer review missing",
    )
    if review is None:
        return result
    try:
        receipt = json.loads(Path(review).read_text("utf-8"))
        if (
            not isinstance(receipt, dict)
            or type(receipt.get("schema_version")) is not int
            or receipt["schema_version"] != 1
            or not isinstance(receipt.get("surfaces"), dict)
        ):
            raise ValueError("review must declare version 1 and an object of surfaces")
        entry = receipt["surfaces"].get(surface)
        if entry is None:
            return result
        if not isinstance(entry, dict):
            raise ValueError("surface review must be an object")
        if entry.get("status") == "REVIEW_REQUIRED":
            return result
        if (
            entry["status"] != "APPROVED"
            or not isinstance(entry["reviewers"], list)
            or not all(isinstance(name, str) for name in entry["reviewers"])
            or not {owner, "Jaineel"} <= set(entry["reviewers"])
            or entry["contracts"] != refs
        ):
            raise ValueError("review is incomplete or stale")
    except (OSError, ValueError, KeyError, TypeError):
        return result | {
            "status": "FAIL",
            "detail": "provider review malformed, stale or incomplete",
        }
    return result | {
        "status": "PASS",
        "detail": "reviewed bytes and executable offline validation passed",
    }
