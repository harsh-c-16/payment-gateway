"""Repair annotations are checked in isolation; no operational promotion endpoint."""

from pydantic import TypeAdapter, ValidationError

from shared.contracts.common import Identifier, UUIDText
from shared.contracts.events import ReasonCode, ValidationFailure


def repair_failure(checked, raw_hash, tx):
    metadata = checked.document.get("metadata", {})
    if metadata.get("original_event_id") is None and metadata.get("repair_reason") is None:
        return None
    try:
        original = metadata.get("original_event_id")
        if original is not None:
            TypeAdapter(UUIDText).validate_python(original)
            if original == checked.envelope.event_id:
                raise ValueError("Repair reused its original event ID")
        TypeAdapter(Identifier).validate_python(metadata.get("source_locator"))
        if (
            not isinstance(metadata.get("repair_reason"), str)
            or not metadata["repair_reason"].strip()
        ):
            raise ValueError("Missing repair reason")
        known = tx.execute(
            "SELECT 1 FROM quarantine WHERE namespace=%s AND raw_locator=%s LIMIT 1",
            (checked.envelope.namespace, metadata["source_locator"]),
        ).fetchone()
        if known is None:
            raise ValueError("Unknown quarantined repair source")
    except (ValueError, ValidationError):
        return ValidationFailure(
            reason_code=ReasonCode.INVARIANT_VIOLATION,
            field_path="metadata",
            diagnostic_message="Repair needs a new event ID, source locator and reason",
            original_content_hash=raw_hash,
        )
    return None
