"""Explicit model spy; synthetic replies never stand in for live quality/usage."""

import asyncio
import copy
import json

from services.conversation.intent_fallback import ModelReply, ModelSettings


class IntentSpy:
    mode = "stub"

    def __init__(self, *, outcome="valid", delay=0, mutate=None, usage=None):
        self.settings = ModelSettings("test-snapshot-2026-01-01")
        self.outcome, self.delay, self.mutate, self.usage = outcome, delay, mutate, usage
        self.calls = []

    async def complete(self, text, partial, schema, *, timeout_seconds):
        self.calls.append(
            {
                "text": text,
                "partial": copy.deepcopy(partial),
                "schema": copy.deepcopy(schema),
                "timeout_seconds": timeout_seconds,
            }
        )
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.outcome == "exception":
            raise RuntimeError("do not expose provider secret")
        if self.outcome == "timeout":
            raise TimeoutError
        if self.outcome == "invalid":
            return ModelReply("not json", self.usage)
        if self.outcome == "refusal":
            return ModelReply(None, self.usage, True)
        intent = {**partial, "category": "clothing"}
        if self.mutate:
            self.mutate(intent)
        return ModelReply(
            json.dumps(
                {"clarification_required": self.outcome == "clarification", "intent": intent}
            ),
            self.usage,
        )
