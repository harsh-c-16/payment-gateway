"""Repeatable presentation checks through public APIs; never submits a purchase."""

import argparse
import base64
import copy
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import httpx

from projectctl import demo
from services.conversation.clients import TransportConfig, strict_json
from services.conversation.provider_contracts import (
    ContractUnavailable,
    ContractViolation,
    Endpoint,
)
from shared.contracts.common import ErrorResponse, RequestContext

REVISION = "flipkart-v1-3a401f32ca99379f8298ce42"
SEARCHES = (
    ("normal", "men's formal shirt", {}),
    ("filtered", "watches under 1000 rupees", {"category": "watches", "max_price_minor": 99999}),
    (
        "unavailable",
        "black watches under 1000 rupees",
        {"category": "watches", "colour": "black", "max_price_minor": 99999},
    ),
)


def validate_search(turn, name, filters):
    if turn["llm_call_count"] != 0 or turn["extractor_source"] != "rules":
        raise demo.DemoError("Fixed-mode search used a model or did not use rules.", 3)
    if turn["outcome"] != "success" or turn["timings_ms"]["total"] > 3000:
        raise demo.DemoError("Search failed or exceeded the unchanged 3-second turn budget.", 3)
    intent = turn["intent"]
    expected = dict.fromkeys(
        (
            "category",
            "size",
            "colour",
            "material",
            "max_price_minor",
            "occasion",
            "brand",
            "category_path_prefix",
        )
    )
    expected.update(filters)
    if (
        not isinstance(intent, dict)
        or intent.get("currency") != "INR"
        or any(intent.get(key) != value for key, value in expected.items())
    ):
        raise demo.DemoError(
            "Search intent is missing or differs from the expected hard filters.", 3
        )
    hits = turn["products"]
    if name == "unavailable":
        if hits:
            raise demo.DemoError("Unavailable colour returned products; inspect the data/rules.", 3)
        return
    if len(hits) != 5 or len({hit["sku"] for hit in hits}) != 5:
        raise demo.DemoError("Expected five distinct eligible presentation products.", 3)
    for hit in hits:
        if (
            hit["dataset_revision"] != REVISION
            or hit["currency"] != "INR"
            or hit["price_minor"] <= 0
            or hit["stock_available"] <= 0
            or any(hit[key] != value for key, value in filters.items() if key != "max_price_minor")
            or ("max_price_minor" in filters and hit["price_minor"] > filters["max_price_minor"])
        ):
            raise demo.DemoError("Product violates a hard filter, stock or dataset identity.", 3)


def validate_gold(result, state):
    snapshot = state["snapshot"]
    matches = [row for row in result["rows"] if row.get("order_id") == state["order_id"]]
    if not matches:
        return False
    if len(matches) != 1:
        raise demo.DemoError("Active Gold contains duplicate order facts.", 3)
    row = matches[0]
    version = row.get("order_version")
    if type(version) is not int:
        raise demo.DemoError("Gold order version is missing or invalid.", 3)
    if version < snapshot["order_version"]:
        return False  # A published older version is valid while the pipeline catches up.
    expected = {
        key: snapshot[key]
        for key in (
            "order_id",
            "order_version",
            "user_id",
            "session_id",
            "quote_id",
            "total_amount_minor",
            "currency",
            "failure_code",
            "reservation_id",
            "payment_id",
        )
    }
    expected.update(namespace=state["identity"]["namespace"], order_status=snapshot["status"])
    if any(
        key not in row or type(row[key]) is not type(value) or row[key] != value
        for key, value in expected.items()
    ):
        raise demo.DemoError("Active Gold order disagrees with the public order snapshot.", 3)
    generation = row.get("publication_generation")
    if type(generation) is not int or not 1 <= generation <= result["generation"]:
        raise demo.DemoError("Gold row publication generation is invalid.", 3)
    return True


class Presentation:
    def __init__(self, out, client, tell):
        self.out, self.http, self.tell = out, client, tell
        self.journal = demo.Journal(
            out / "checks.json",
            {
                "schema_version": 1,
                "started_at": demo.utc_now(),
                "status": "INCOMPLETE",
                "scope": "prototype acceptance; not the formal evaluation or ledger reconciliation",
                "checks": [],
            },
        )
        self.journal.save()

    def check(self, name, action):
        try:
            detail = action()
        except (
            demo.DemoError,
            OSError,
            ValueError,
            KeyError,
            TypeError,
            httpx.HTTPError,
            ContractUnavailable,
            ContractViolation,
        ) as exc:
            code = exc.code if isinstance(exc, demo.DemoError) else 4
            self.journal.data["checks"].append(
                {
                    "name": name,
                    "status": "FAIL",
                    "exit_code": code,
                    "detail": str(exc) if isinstance(exc, demo.DemoError) else type(exc).__name__,
                }
            )
            self.tell(f"FAIL {name}: inspect {self.out}")
        else:
            self.journal.data["checks"].append({"name": name, "status": "PASS", "detail": detail})
            self.tell(f"PASS {name}")
        self.journal.save()

    def get(self, origin, path, *, headers=None, params=None):
        started = time.monotonic()
        self.journal.record(
            {
                "phase": "request",
                "method": "GET",
                "origin": origin,
                "path": path,
                "params": params,
                "headers": headers,
            }
        )
        try:
            with self.http.stream(
                "GET", origin + path, headers=headers, params=params, timeout=2.0
            ) as response:
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 2 * 1024 * 1024:
                        raise demo.DemoError("Public response exceeds the client limit.")
                self.journal.record(
                    {
                        "phase": "response",
                        "status": response.status_code,
                        "body_base64": base64.b64encode(raw).decode("ascii"),
                        "elapsed_ms": (time.monotonic() - started) * 1000,
                    }
                )
                if response.status_code != 200:
                    # Preserve the bounded body on status exceptions. A streamed
                    # httpx response has no .content after iter_bytes alone.
                    httpx.Response(
                        response.status_code,
                        headers=response.headers,
                        content=bytes(raw),
                        request=response.request,
                    ).raise_for_status()
                    raise demo.DemoError("Public GET did not return HTTP 200.")
                if response.headers.get("content-type", "").split(";")[0] != "application/json":
                    raise demo.DemoError("Public API did not return JSON.")
                value = strict_json(raw)
                if not isinstance(value, dict):
                    raise demo.DemoError("Public API did not return a JSON object.")
                return value
        except httpx.HTTPError:
            self.journal.record({"phase": "http_error", "path": path})
            raise

    def search(self, name, query, filters, args):
        data = {
            "schema_version": 1,
            "mode": "fixed",
            "phase": "session",
            "operations": {},
            "identity": {
                "namespace": args.namespace,
                "user_id": "demo-preflight",
                "run_id": str(uuid4()),
                "correlation_id": str(uuid4()),
            },
            "origins": {"conversation": args.conversation_url, "transactions": args.orders_url},
        }
        journal = demo.Journal(self.out / f"{name}-state.json", data)
        journal.save()
        runner = demo.Demo(journal, self.http, tell=self.tell)
        session = runner.call("session", operation="session", body={})
        journal.advance("search", **session)
        turn = runner.call("search", operation="search:0", body={"text": query, "mode": "fixed"})
        validate_search(turn, name, filters)
        return {
            "query": query,
            "intent": turn["intent"],
            "products": turn["products"],
            "llm_call_count": turn["llm_call_count"],
            "timings_ms": turn["timings_ms"],
        }

    def order(self, args):
        if args.state.stat().st_size > 4 * 1024 * 1024:
            raise demo.DemoError("Saved demo state exceeds the client limit.", 2)
        state = copy.deepcopy(strict_json(args.state.read_bytes()))
        demo.validate_state(state)
        if (
            state["phase"] not in {"status", "done"}
            or not state.get("order_id")
            or not state.get("confirmation_id")
        ):
            raise demo.DemoError("Use an accepted order's original demo state.", 2)
        RequestContext(**state["identity"], request_id=str(uuid4()), session_id=state["session_id"])
        for origin in state["origins"].values():
            TransportConfig(origin)
        # Observe a private COPY. Never change or resubmit the original purchase.
        journal = demo.Journal(self.out / "order-state.json", state)
        journal.save()
        runner = demo.Demo(journal, self.http, tell=self.tell, wait_seconds=args.wait_seconds)
        runner.observe()
        created = datetime.fromisoformat(state["snapshot"]["created_at"].replace("Z", "+00:00"))
        day = created.astimezone(UTC).date()
        params = {
            "namespace": state["identity"]["namespace"],
            "date_from": day.isoformat(),
            "date_to": (day + timedelta(days=1)).isoformat(),
        }
        headers = runner.context(str(uuid4())).headers()
        endpoint = Endpoint("analytics", "GET", "/v1/analytics/gold/{table}", 200)
        deadline = time.monotonic() + args.wait_seconds
        consecutive_errors = 0
        while True:
            delay = 1.0
            try:
                value = self.get(
                    args.analytics_url,
                    "/v1/analytics/gold/order_fact",
                    headers=headers,
                    params=params,
                )
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                consecutive_errors += 1
                if isinstance(exc, httpx.HTTPStatusError):
                    if exc.response.status_code not in {429, 503}:
                        raise
                    error = ErrorResponse.model_validate(strict_json(exc.response.content)).error
                    if not error.retryable:
                        raise
                    requested = demo.retry_delay(exc.response.headers.get("Retry-After")) or 0
                else:
                    requested = 0
                if consecutive_errors >= 3:
                    raise
                delay = max((0.1, 0.3)[consecutive_errors - 1], requested)
                self.tell("Analytics temporarily unavailable; retrying the same read.")
            else:
                consecutive_errors = 0
                runner.contracts.validate(endpoint, "response", value)
                if validate_gold(value, state):
                    return {
                        "order_id": state["order_id"],
                        "status": state["final_status"],
                        "gold_generation": value["generation"],
                        "date_from": params["date_from"],
                    }
            remaining = deadline - time.monotonic()
            if remaining <= 0 or delay > remaining:
                raise demo.DemoError(
                    "Order not yet visible at its terminal version in active Gold."
                )
            time.sleep(delay)


def add_arguments(parser):
    parser.add_argument("--namespace", default="dev")
    parser.add_argument("--conversation-url", default="http://127.0.0.1:8001")
    parser.add_argument("--orders-url", default="http://127.0.0.1:8003")
    parser.add_argument("--analytics-url", default="http://127.0.0.1:8006")
    parser.add_argument(
        "--state", type=Path, help="check an accepted demo order in Orders and Gold"
    )
    parser.add_argument(
        "--wait-seconds", type=int, default=120, help="order/Gold polling window, 1-600"
    )
    parser.add_argument(
        "--out", type=Path, help="new evidence directory; default artifacts/presentation/UUID"
    )


def run(args, *, client=None, tell=print):
    if not 1 <= args.wait_seconds <= 600:
        raise demo.DemoError("--wait-seconds must be between 1 and 600.", 2)
    for field in ("conversation_url", "orders_url", "analytics_url"):
        origin = getattr(args, field)
        TransportConfig(origin)
        setattr(args, field, origin.rstrip("/"))
    RequestContext(
        namespace=args.namespace,
        user_id="demo-preflight",
        run_id=str(uuid4()),
        correlation_id=str(uuid4()),
        request_id=str(uuid4()),
        session_id=None,
    )
    out = (args.out or demo.ROOT / "artifacts/presentation" / str(uuid4())).resolve()
    out.mkdir(parents=True, exist_ok=False)
    if client is None:
        with httpx.Client(trust_env=False, follow_redirects=False) as http:
            return _run(args, out, http, tell)
    return _run(args, out, client, tell)


def _run(args, out, client, tell):
    checker = Presentation(out, client, tell)
    tell(f"Evidence: {out}")
    if args.state:
        checker.check("order-to-active-gold", lambda: checker.order(args))
    else:
        for name, origin in (
            ("conversation", args.conversation_url),
            ("orders", args.orders_url),
            ("analytics", args.analytics_url),
        ):

            def ready(origin=origin, name=name):
                value = checker.get(origin, "/health/ready")
                if value.get("status") != "ready" or (
                    name == "conversation" and value.get("mode") != "real"
                ):
                    raise demo.DemoError("Service is not ready with real providers.", 3)
                return value

            checker.check(f"{name}-ready", ready)
        for name, query, filters in SEARCHES:
            checker.check(
                f"search-{name}",
                lambda name=name, query=query, filters=filters: checker.search(
                    name, query, filters, args
                ),
            )
    code = max((check.get("exit_code", 0) for check in checker.journal.data["checks"]), default=4)
    checker.journal.data.update(
        status="PASS" if code == 0 else "INCOMPLETE", exit_code=code, finished_at=demo.utc_now()
    )
    checker.journal.save()
    tell(f"Presentation checks: {checker.journal.data['status']} (exit {code}).")
    return code


def command(args):
    try:
        return run(args)
    except (demo.DemoError, OSError, ValueError, KeyError, TypeError) as exc:
        print("Invalid presentation configuration; use --help and a new evidence directory.")
        return exc.code if isinstance(exc, demo.DemoError) else 4


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    add_arguments(parser)
    sys.exit(command(parser.parse_args()))
