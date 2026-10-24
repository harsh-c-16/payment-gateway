"""Explicit in-process HTTP/SSE doubles. Never a real integration adapter."""

import copy
import json

import httpx

from .provisional import NOW


def common_error(code="DEPENDENCY_UNAVAILABLE", retryable=True):
    return {
        "error": {
            "code": code,
            "message": "Synthetic contract-test failure",
            "retryable": retryable,
            "details": {},
        },
        "correlation_id": "p2-correlation",
    }


class ScriptedProvider:
    def __init__(self, *steps):
        self.steps = list(steps)
        self.requests = []

    async def __call__(self, request):
        self.requests.append(request)
        if not self.steps:
            raise AssertionError("unexpected extra provider call")
        step = self.steps.pop(0)
        if isinstance(step, Exception):
            raise step
        if callable(step):
            return await step(request)
        return httpx.Response(step[0], json=step[1], headers=step[2] if len(step) == 3 else {})


class LostOrderResponse:
    """Test-only key ledger, demonstrating consumer retries after acceptance + response loss."""

    def __init__(self, accepted):
        self.accepted = copy.deepcopy(accepted)
        self.requests = []
        self.bindings = {}
        self.effects = 0
        self.lose_first = True

    async def __call__(self, request):
        self.requests.append(request)
        scope = tuple(
            request.headers[field] for field in ("X-Namespace", "X-User-ID", "Idempotency-Key")
        )
        body = json.loads(request.content)
        if scope in self.bindings:
            if self.bindings[scope] != body:
                return httpx.Response(409, json=common_error("IDEMPOTENCY_CONFLICT", False))
        else:
            self.bindings[scope] = body
            self.effects += 1
        if self.lose_first:
            self.lose_first = False
            raise httpx.ReadTimeout(
                "explicit lost response after simulated acceptance", request=request
            )
        return httpx.Response(202, json=self.accepted)


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


def sse(snapshot, event_id=None):
    event_id = snapshot["order_version"] if event_id is None else event_id
    return (
        f": heartbeat {NOW}\nid: {event_id}\nevent: snapshot\ndata: {json.dumps(snapshot)}\n\n"
    ).encode()
