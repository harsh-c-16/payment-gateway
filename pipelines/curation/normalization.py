"""Typed event payloads; catalogue attributes are never inferred or recleaned here."""

from shared.contracts.events import EVENTS, EventEnvelope


def normalize_payload(event):
    if not isinstance(event, EventEnvelope):
        raise TypeError("Silver accepts business events, not DLQ notices")
    return EVENTS[event.event_type][4].model_validate(event.payload).model_dump(mode="json")
