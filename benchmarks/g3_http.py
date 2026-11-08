"""G3 HTTP boundary: canonical DTOs, explicit test transports, retained receipts."""

import asyncio
import base64
import hashlib
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from benchmarks.scheduler import journal, utc_now
from projectctl.providers import DependencyError
from shared.contracts.common import ErrorResponse

REQUEST_TIMEOUT_SECONDS = 2.0


class UnknownOutcome(DependencyError):
    pass


class HTTPFailure(DependencyError):
    def __init__(self, status, code):
        self.status, self.code = status, code
        super().__init__(f"G3 provider HTTP {status}: {code}")


class G3HTTP:
    """No implicit retries, redirects, environment proxies or credential logging.

    The caller chooses the same-key retry explicitly. Audit calls use GET only.
    URLs and tokens stay in memory; journals contain paths and safe identity headers.
    """

    def __init__(self, origins, token, *, mode="real", transport=None):
        if mode not in {"real", "stub"} or (mode == "real") != (transport is None):
            raise ValueError("real HTTP or explicitly labelled test transport required")
        for origin in origins.values():
            url = urlsplit(origin)
            if (
                url.scheme not in {"http", "https"}
                or not url.hostname
                or url.username
                or url.password
                or url.path not in {"", "/"}
                or url.query
                or url.fragment
            ):
                raise ValueError("G3 origins must be HTTP origins without credentials")
        if not token:
            raise DependencyError("explicit internal audit token unavailable")
        self.origins, self.token, self.mode = origins, token, mode
        self.http = httpx.AsyncClient(
            transport=transport or httpx.AsyncHTTPTransport(retries=0),
            timeout=2,
            trust_env=False,
            follow_redirects=False,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.http.aclose()

    async def call(
        self,
        context,
        principal,
        service,
        method,
        path,
        status=200,
        *,
        body=None,
        key=None,
        model=None,
    ):
        if method not in {"GET", "POST", "PUT"} or not path.startswith("/") or "?" in path:
            raise ValueError("explicit public path/method required")
        if method != "GET" and not key:
            raise ValueError("stable mutation idempotency key required")
        headers = principal.headers(key)
        request = {
            "at": utc_now(),
            "service": service,
            "method": method,
            "path": path,
            "body": body,
            "headers": headers,
        }
        with (Path(context["directory"]) / "http.jsonl").open("a", encoding="utf-8") as log:
            journal(log, {"phase": "request", **request})
            outgoing = dict(headers)
            if path.startswith("/internal/"):
                outgoing["Authorization"] = "Bearer " + self.token
            started = time.monotonic()
            try:
                async with (
                    asyncio.timeout(REQUEST_TIMEOUT_SECONDS),
                    self.http.stream(
                        method,
                        self.origins[service].rstrip("/") + path,
                        headers=outgoing,
                        json=body,
                    ) as response,
                ):
                    raw = bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 2 * 1024 * 1024:
                            raise DependencyError("G3 response exceeds bounded audit buffer")
                    # Retain exact provider bytes, including error responses, before validation.
                    journal(
                        log,
                        {
                            "phase": "response",
                            "service": service,
                            "method": method,
                            "path": path,
                            "status": response.status_code,
                            "body_base64": base64.b64encode(raw).decode("ascii"),
                            "body_sha256": hashlib.sha256(raw).hexdigest(),
                            "elapsed_seconds": time.monotonic() - started,
                        },
                    )
                    value = json.loads(raw, parse_constant=_invalid, object_pairs_hook=_unique)
                    if response.status_code != status:
                        error = ErrorResponse.model_validate(value)
                        raise HTTPFailure(response.status_code, error.error.code.value)
                    if response.headers.get("content-type", "").split(";")[0] != "application/json":
                        raise DependencyError("G3 provider content type mismatch")
                    return model.model_validate(value).model_dump(mode="json") if model else value
            except (httpx.TransportError, TimeoutError):
                journal(
                    log,
                    {
                        "phase": "unknown",
                        "service": service,
                        "method": method,
                        "path": path,
                        "finality_seconds": None,
                        "elapsed_seconds": time.monotonic() - started,
                    },
                )
                raise UnknownOutcome(
                    "G3 transport outcome unknown; backend evidence required"
                ) from None


def _invalid(value):
    raise ValueError("nonfinite JSON")


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result
