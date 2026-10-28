"""Bounded HTTP adapters. No fixtures, service business rules, or fallback data."""

import asyncio
import codecs
import copy
import json
import math
import random
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Literal
from urllib.parse import quote, urlparse

import httpx

from services.conversation.provider_contracts import ENDPOINTS, ContractViolation
from shared.contracts.common import ErrorResponse, RequestContext


class DependencyUnavailable(RuntimeError):
    def __init__(self, *, outcome_unknown=False):
        super().__init__("dependency unavailable; no fallback used")
        self.outcome_unknown = outcome_unknown


class RemoteError(RuntimeError):
    def __init__(self, status, payload, retry_after=None):
        super().__init__(f"provider returned HTTP {status}: {payload.error.code}")
        self.status = status
        self.payload = payload
        self.retry_after = retry_after


@dataclass(frozen=True)
class TransportConfig:
    base_url: str
    mode: Literal["real", "stub"] = "real"
    purpose: Literal["integration", "benchmark", "contract_test"] = "integration"
    timeout_seconds: float = 2.0
    get_retries: int = 2
    mutation_retries: int = 0
    jitter_seed: int = 42

    def __post_init__(self):
        parsed = urlparse(self.base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("base URL must be an HTTP service origin without credentials")
        if self.mode not in {"real", "stub"} or self.purpose not in {
            "integration",
            "benchmark",
            "contract_test",
        }:
            raise ValueError("explicit transport mode/purpose required")
        if self.mode == "stub" and self.purpose != "contract_test":
            raise ValueError("stub transport is restricted to explicit contract tests")
        if (
            not 0 < self.timeout_seconds <= 2
            or type(self.get_retries) is not int
            or type(self.mutation_retries) is not int
            or self.get_retries not in range(3)
            or self.mutation_retries not in range(3)
        ):
            raise ValueError("HTTP attempts and timeouts must be bounded")


def strict_json(value):
    def invalid(_):
        raise ValueError("nonfinite JSON")

    def unique(pairs):
        result = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = item
        return result

    try:
        return json.loads(value, parse_constant=invalid, object_pairs_hook=unique)
    except (ValueError, UnicodeError) as exc:
        raise ContractViolation("provider returned malformed JSON") from exc


def retry_delay(value):
    if value is None:
        return None
    try:
        return max(0.0, float(int(value)))
    except ValueError:
        try:
            return max(0.0, (parsedate_to_datetime(value) - datetime.now(UTC)).total_seconds())
        except (ValueError, TypeError, OverflowError):
            raise ContractViolation("invalid Retry-After header") from None


def remaining_time(cutoff):
    remaining = cutoff - time.monotonic()
    if remaining <= 0:
        raise DependencyUnavailable()
    return remaining


def request_cutoff(deadline, timeout_seconds):
    if deadline is not None and (
        isinstance(deadline, bool)
        or not isinstance(deadline, (int, float))
        or not math.isfinite(deadline)
    ):
        raise ValueError("deadline must be a finite monotonic timestamp")
    return min(
        deadline if deadline is not None else float("inf"),
        time.monotonic() + timeout_seconds,
    )


def validate_order_identity(snapshot, order_id, context):
    if (
        snapshot["order_id"] != order_id
        or snapshot["user_id"] != context.user_id
        or (context.session_id is not None and snapshot["session_id"] != context.session_id)
    ):
        raise ContractViolation("order response identity/principal mismatch")


class ProviderHTTP:
    def __init__(self, config: TransportConfig, contracts, *, transport=None, internal_token=None):
        if config.mode == "real":
            if transport is not None or contracts.mode != "real":
                raise ValueError("real execution requires real transport and owner schemas")
            transport = httpx.AsyncHTTPTransport(retries=0)
        elif transport is None or contracts.mode != "stub":
            raise ValueError("stub mode requires an explicit test transport and test schemas")
        self.config = config
        self.contracts = contracts
        self.internal_token = internal_token
        self.http = httpx.AsyncClient(
            base_url=config.base_url,
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=config.timeout_seconds,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.http.aclose()

    def prepare(self, name, context, body, key, path_values, params, headers):
        endpoint = ENDPOINTS[name]
        path = endpoint.path
        for field, value in path_values.items():
            if not isinstance(value, str) or not value or value in {".", ".."}:
                raise ValueError("invalid path identifier")
            path = path.replace("{" + field + "}", quote(value, safe=""))
        if "{" in path:
            raise ValueError("missing path identifier")
        if endpoint.method != "GET" and key is None:
            raise ValueError("mutation requires a stable idempotency key")
        outgoing = context.headers(key)
        if endpoint.internal:
            if not self.internal_token:
                raise ValueError("internal endpoint requires an explicit service token")
            outgoing["Authorization"] = "Bearer " + self.internal_token
        protected = {field.lower() for field in outgoing} | {
            "authorization",
            "idempotency-key",
            "x-session-id",
            "x-trace-id",
        }
        if headers and any(field.lower() in protected for field in headers):
            raise ValueError("extra headers cannot override operation identity or authorization")
        outgoing.update(headers or {})
        if params:
            for field in ("namespace", "user_id", "run_id", "request_id", "session_id"):
                if field in params and params[field] != getattr(context, field):
                    raise ValueError("query/context identity mismatch")
        if body is not None:
            if not isinstance(body, dict):
                raise ValueError("expected a JSON object")
            # Principal fields cannot override context. Only search duplicates request/session IDs.
            if {"namespace", "run_id", "user_id", "correlation_id"} & body.keys():
                raise ValueError("request body cannot override identity context")
            for field in ("request_id", "session_id"):
                if field in body and body[field] != getattr(context, field):
                    raise ValueError("request/context identity mismatch")
            self.contracts.validate(endpoint, "request", body)
        return endpoint, path, outgoing, params

    def error(self, response, content):
        try:
            payload = ErrorResponse.model_validate(strict_json(content))
        except ValueError as exc:
            raise ContractViolation("provider returned an invalid common error") from exc
        return RemoteError(
            response.status_code, payload, retry_delay(response.headers.get("Retry-After"))
        )

    async def request(
        self,
        name,
        context: RequestContext,
        *,
        body=None,
        key=None,
        deadline=None,
        params=None,
        headers=None,
        **path_values,
    ):
        cutoff = request_cutoff(deadline, self.config.timeout_seconds)
        # Snapshot input once so an awaiting caller cannot change a retry's business body.
        body = strict_json(json.dumps(body, allow_nan=False)) if body is not None else None
        params = copy.deepcopy(dict(params)) if params is not None else None
        endpoint, path, outgoing, params = self.prepare(
            name, context, body, key, path_values, params, headers
        )
        retries = (
            self.config.get_retries if endpoint.method == "GET" else self.config.mutation_retries
        )
        jitter = random.Random(self.config.jitter_seed)
        for attempt in range(retries + 1):
            remaining = cutoff - time.monotonic()
            if remaining <= 0:
                raise DependencyUnavailable(outcome_unknown=endpoint.method != "GET")
            failure = None
            try:
                async with asyncio.timeout(remaining):
                    async with self.http.stream(
                        endpoint.method,
                        path,
                        headers=outgoing,
                        params=params,
                        json=body,
                        timeout=remaining,
                    ) as response:
                        chunks = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(chunks) + len(chunk) > 2 * 1024 * 1024:
                                raise ContractViolation(
                                    "provider response exceeds bounded client buffer"
                                )
                            chunks.extend(chunk)
                        if response.status_code == endpoint.status:
                            if (
                                response.headers.get("content-type", "").split(";")[0].strip()
                                != "application/json"
                            ):
                                raise ContractViolation("expected application/json")
                            payload = strict_json(chunks)
                            self.contracts.validate(endpoint, "response", payload)
                            if name == "order_status":
                                validate_order_identity(payload, path_values["order_id"], context)
                            if time.monotonic() >= cutoff:
                                raise DependencyUnavailable(
                                    outcome_unknown=endpoint.method != "GET"
                                )
                            return payload
                        failure = self.error(response, chunks)
                        if (
                            response.status_code not in {429, 503}
                            or not failure.payload.error.retryable
                        ):
                            raise failure
            except (httpx.RequestError, TimeoutError):
                failure = DependencyUnavailable(outcome_unknown=endpoint.method != "GET")
            if attempt == retries:
                raise failure
            wait = (0.1, 0.3)[attempt] + jitter.uniform(0, 0.01)
            if isinstance(failure, RemoteError) and failure.retry_after is not None:
                wait = max(wait, failure.retry_after)
            if time.monotonic() + wait >= cutoff:
                raise failure
            await asyncio.sleep(wait)
        raise AssertionError("bounded request loop exhausted")

    async def events(
        self, order_id, context, *, last_event_id=None, deadline=None
    ) -> AsyncIterator[dict]:
        if last_event_id is not None and (type(last_event_id) is not int or last_event_id < 0):
            raise ValueError("Last-Event-ID must be a nonnegative order version")
        headers = {"Accept": "text/event-stream"}
        if last_event_id is not None:
            headers["Last-Event-ID"] = str(last_event_id)
        endpoint, path, outgoing, _ = self.prepare(
            "order_events", context, None, None, {"order_id": order_id}, None, headers
        )
        cutoff = request_cutoff(deadline, self.config.timeout_seconds)
        cursor = last_event_id if last_event_id is not None else -1
        current_snapshot = None
        first = True
        try:
            async with asyncio.timeout(remaining_time(cutoff)):
                response = await self.http.send(
                    self.http.build_request("GET", path, headers=outgoing), stream=True
                )
            try:
                if response.status_code != 200:
                    async with asyncio.timeout(remaining_time(cutoff)):
                        content = bytearray()
                        async for chunk in response.aiter_bytes():
                            if len(content) + len(chunk) > 2 * 1024 * 1024:
                                raise ContractViolation("provider error exceeds client buffer")
                            content.extend(chunk)
                    raise self.error(response, content)
                if (
                    response.headers.get("content-type", "").split(";")[0].strip()
                    != "text/event-stream"
                ):
                    raise ContractViolation("expected text/event-stream")
                # Bound each frame and partial line, including unterminated input.
                buffer, data, event_id, event_bytes = "", [], None, 0
                iterator = response.aiter_bytes().__aiter__()
                decoder = codecs.getincrementaldecoder("utf-8")("strict")
                while True:
                    try:
                        async with asyncio.timeout(remaining_time(cutoff)):
                            chunk = await anext(iterator)
                    except StopAsyncIteration:
                        break
                    buffer += decoder.decode(chunk)
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        line = line.rstrip("\r")
                        if len(line.encode("utf-8")) + event_bytes > 65536:
                            raise ContractViolation("SSE frame exceeds 64 KiB")
                        if not line:
                            if data:
                                snapshot = strict_json("\n".join(data))
                                self.contracts.validate(endpoint, "response", snapshot)
                                validate_order_identity(snapshot, order_id, context)
                                version = snapshot["order_version"]
                                if event_id != str(version) or snapshot["order_id"] != order_id:
                                    raise ContractViolation("SSE identity/version mismatch")
                                if (
                                    version == cursor
                                    and current_snapshot is not None
                                    and snapshot != current_snapshot
                                ):
                                    raise ContractViolation("SSE conflicting order version")
                                if version > cursor or (first and version == cursor):
                                    remaining_time(cutoff)
                                    current_snapshot = copy.deepcopy(snapshot)
                                    yield snapshot
                                    cursor, first = version, False
                            data, event_id, event_bytes = [], None, 0
                        elif line.startswith("data:"):
                            data.append(line[5:].removeprefix(" "))
                            event_bytes += len(line.encode("utf-8"))
                        elif line.startswith("id:"):
                            event_id = line[3:].strip()
                    if len(buffer.encode("utf-8")) + event_bytes > 65536:
                        raise ContractViolation("SSE frame exceeds 64 KiB")
                decoder.decode(b"", final=True)
                if buffer or data:
                    raise ContractViolation("SSE ended with an incomplete frame")
                if first:
                    raise DependencyUnavailable()
            finally:
                await response.aclose()
        except (httpx.RequestError, TimeoutError):
            raise DependencyUnavailable() from None
        except UnicodeError:
            raise ContractViolation("SSE contains invalid UTF-8") from None


class CatalogClient:
    def __init__(self, http: ProviderHTTP):
        self.http = http

    async def search(self, request, context, *, key, deadline=None):
        return await self.http.request("search", context, body=request, key=key, deadline=deadline)

    async def product(self, sku, context, *, deadline=None):
        return await self.http.request("product", context, sku=sku, deadline=deadline)

    async def facets(self, context, *, dataset_revision=None, deadline=None):
        params = {"namespace": context.namespace}
        if dataset_revision is not None:
            params["dataset_revision"] = dataset_revision
        return await self.http.request("facets", context, params=params, deadline=deadline)

    async def quote(self, request, context, *, key, deadline=None):
        return await self.http.request("quote", context, body=request, key=key, deadline=deadline)


class OrdersClient:
    def __init__(self, http: ProviderHTTP):
        self.http = http

    async def create(self, request, context, *, key, deadline=None):
        return await self.http.request(
            "order_create", context, body=request, key=key, deadline=deadline
        )

    async def status(self, order_id, context, *, deadline=None):
        return await self.http.request(
            "order_status", context, order_id=order_id, deadline=deadline
        )

    def events(self, order_id, context, *, last_event_id=None, deadline=None):
        return self.http.events(order_id, context, last_event_id=last_event_id, deadline=deadline)


class AnalyticsClient:
    def __init__(self, http: ProviderHTTP):
        self.http = http

    def params(self, context, cursor=None, limit=1000, cursor_name="cursor"):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError("page limit must be 1..1000")
        params = {"namespace": context.namespace, "limit": limit}
        if cursor is not None:
            params[cursor_name] = cursor
        return params

    async def active_manifest(self, dataset, context, *, deadline=None):
        if dataset not in {"silver", "gold"}:
            raise ValueError("dataset must be silver or gold")
        return await self.http.request(
            "active_manifest",
            context,
            dataset=dataset,
            params={"namespace": context.namespace},
            deadline=deadline,
        )

    async def gold(self, table, date_from, date_to, context, *, currency=None, deadline=None):
        params = {"namespace": context.namespace, "date_from": date_from, "date_to": date_to}
        if currency is not None:
            params["currency"] = currency
        return await self.http.request(
            "gold", context, table=table, params=params, deadline=deadline
        )

    async def receipts(self, context, *, after_cursor=None, limit=1000, deadline=None):
        return await self.http.request(
            "receipts",
            context,
            params=self.params(context, after_cursor, limit, "after_cursor"),
            deadline=deadline,
        )

    async def quarantine(self, context, *, cursor=None, limit=1000, deadline=None):
        return await self.http.request(
            "quarantine", context, params=self.params(context, cursor, limit), deadline=deadline
        )

    async def replay(self, request, context, *, key, deadline=None):
        target = request.get("target_namespace")
        if (
            not isinstance(target, str)
            or not re.fullmatch(r"replay-[a-z0-9][a-z0-9-]{0,54}", target)
            or target == context.namespace
        ):
            raise ValueError(
                "replay requires a separate isolated target; provider checks emptiness"
            )
        return await self.http.request(
            "replay_create", context, body=request, key=key, deadline=deadline
        )

    async def replay_status(self, replay_id, context, *, deadline=None):
        return await self.http.request(
            "replay_status", context, replay_id=replay_id, deadline=deadline
        )
