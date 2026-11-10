"""Interactive fixed-mode shopping demo over the existing public APIs."""

import argparse
import base64
import json
import os
import sys
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

import httpx
from pydantic import ValidationError

from services.conversation.clients import TransportConfig, retry_delay, strict_json
from services.conversation.provider_contracts import (
    ContractUnavailable,
    ContractViolation,
    Endpoint,
    OpenAPIContracts,
)
from shared.contracts.common import ErrorResponse, RequestContext

ROOT = Path(__file__).resolve().parents[1]
PHASES = {"session", "search", "select", "cart", "quote", "confirm", "checkout", "status", "done"}
ENDPOINTS = {
    "session": Endpoint("conversation", "POST", "/v1/sessions", 201),
    "search": Endpoint("conversation", "POST", "/v1/sessions/{session_id}/turns", 200),
    "cart": Endpoint("conversation", "PUT", "/v1/carts/{cart_id}/items/{sku}", 200),
    "cart_read": Endpoint("conversation", "GET", "/v1/carts/{cart_id}", 200),
    "quote": Endpoint("conversation", "POST", "/v1/carts/{cart_id}/quote", 201),
    "checkout": Endpoint("conversation", "POST", "/v1/carts/{cart_id}/checkout", 202),
    "status": Endpoint("transactions", "GET", "/v1/orders/{order_id}", 200),
}


class DemoError(RuntimeError):
    def __init__(self, message, code=4):
        super().__init__(message)
        self.code = code


class RejectedOperation(DemoError):
    def __init__(self, message, status, error_code):
        super().__init__(message, 3)
        self.status, self.error_code = status, error_code


def utc_now():
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def money(value, currency):
    # All authoritative arithmetic remains on the server; display integers only.
    return f"{currency} {value // 100:,}.{value % 100:02d}"


def display(value):
    """Catalogue text cannot inject terminal controls or become a command."""
    return "".join(c if c.isprintable() else " " for c in str(value))


@contextmanager
def exclusive_state(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(path.suffix + ".lock")
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError:
        raise DemoError(
            "Demo state is in use; inspect its .lock file before resuming.", 2
        ) from None
    try:
        with handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        lock.unlink()


class Journal:
    def __init__(self, path, data):
        self.path, self.data = path, data

    def save(self):
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as output:
            json.dump(self.data, output, ensure_ascii=False, allow_nan=False, indent=2)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(self.path)

    def record(self, value):
        with self.path.with_suffix(self.path.suffix + ".http.jsonl").open(
            "a", encoding="utf-8"
        ) as output:
            output.write(json.dumps({"at": utc_now(), **value}, allow_nan=False) + "\n")
            output.flush()

    def advance(self, phase, **values):
        self.data.update(phase=phase, **values)
        self.save()


class Demo:
    """A restartable client, with no service internals, DB writes or model provider."""

    def __init__(self, journal, client, *, ask=input, tell=print, wait_seconds=60):
        self.journal, self.data, self.http = journal, journal.data, client
        self.ask, self.tell, self.wait_seconds = ask, tell, wait_seconds
        self.contracts = OpenAPIContracts(ROOT / "contracts/http")

    def context(self, request_id):
        return RequestContext(
            **self.data["identity"], request_id=request_id, session_id=self.data.get("session_id")
        )

    def call(self, kind, *, operation=None, body=None):
        endpoint = ENDPOINTS[kind]
        path = endpoint.path
        for field in ("session_id", "cart_id", "sku", "order_id"):
            if "{" + field + "}" in path:
                path = path.replace("{" + field + "}", quote(self.data[field], safe=""))
        if endpoint.method == "GET":
            entry = {"request_id": str(uuid4()), "key": None, "body": None}
        else:
            operations = self.data["operations"]
            entry = operations.get(operation)
            if entry is None:
                entry = {"request_id": str(uuid4()), "key": str(uuid4()), "body": body}
                if kind == "search":
                    entry["body"] = {**body, "request_id": entry["request_id"]}
                entry.update(kind=kind, path=path)
                operations[operation] = entry
                # Persist the exact body and identity BEFORE any mutation is sent.
                self.journal.save()
            elif entry["kind"] != kind or entry["path"] != path:
                raise DemoError("Saved operation does not match this demo step.", 3)
            expected_body = (
                {**body, "request_id": entry["request_id"]} if kind == "search" else body
            )
            if entry["body"] != expected_body:
                raise DemoError(
                    "Saved operation body changed; preserve its original retry input.", 3
                )
            if "response" in entry:
                self.contracts.validate(endpoint, "response", entry["response"])
                return entry["response"]
        headers = self.context(entry["request_id"]).headers(entry["key"])
        if entry["body"] is not None:
            self.contracts.validate(endpoint, "request", entry["body"])
        for attempt in range(3):
            started = time.monotonic()
            self.journal.record(
                {
                    "phase": "request",
                    "kind": kind,
                    "path": path,
                    "headers": headers,
                    "body": entry["body"],
                    "attempt": attempt + 1,
                }
            )
            delay = (0.1, 0.3, 0)[attempt]
            try:
                # M1 owns a 3-second turn deadline. Give its HTTP response room to
                # arrive; do not inherit the provider adapter's 2-second timeout.
                timeout = 5.0 if endpoint.provider == "conversation" else 2.0
                origin = self.data["origins"][endpoint.provider]
                with self.http.stream(
                    endpoint.method,
                    origin + path,
                    headers=headers,
                    json=entry["body"],
                    timeout=timeout,
                ) as response:
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        raw.extend(chunk)
                        if len(raw) > 2 * 1024 * 1024:
                            raise DemoError("Provider response exceeds the client limit.")
                    self.journal.record(
                        {
                            "phase": "response",
                            "kind": kind,
                            "status": response.status_code,
                            "body_base64": base64.b64encode(raw).decode("ascii"),
                            "elapsed_ms": (time.monotonic() - started) * 1000,
                        }
                    )
                    value = strict_json(raw)
                    if response.status_code == endpoint.status:
                        if (
                            response.headers.get("content-type", "").split(";")[0]
                            != "application/json"
                        ):
                            raise DemoError("Provider did not return JSON.")
                        self.contracts.validate(endpoint, "response", value)
                        if operation:
                            entry["response"] = value
                            self.journal.save()
                        return value
                    error = ErrorResponse.model_validate(value).error
                    retryable = response.status_code in {429, 503} and error.retryable
                    message = f"{kind}: HTTP {response.status_code} {error.code.value}."
                    if not retryable:
                        raise RejectedOperation(
                            message + " Inspect saved state before starting a new operation.",
                            response.status_code,
                            error.code.value,
                        )
                    requested = retry_delay(response.headers.get("Retry-After"))
                    delay = max(delay, requested or 0)
                    if delay > 5:
                        raise DemoError(message + " Retry later with --resume and the same state.")
            except httpx.TransportError:
                message = f"{kind}: response unavailable; mutation outcome may be unknown."
                self.journal.record(
                    {
                        "phase": "transport_error",
                        "kind": kind,
                        "elapsed_ms": (time.monotonic() - started) * 1000,
                    }
                )
            if attempt == 2:
                raise DemoError(message + " Resume this state to reuse the same request and key.")
            self.tell(f"{kind}: retrying the same request/key ({attempt + 1}/2).")
            time.sleep(delay)
        raise AssertionError("bounded retry loop exhausted")

    def number(self, prompt, minimum, maximum):
        while True:
            text = self.ask(prompt).strip()
            if text.lower() in {"q", "quit"}:
                raise EOFError
            if text.isascii() and text.isdecimal() and minimum <= int(text) <= maximum:
                return int(text)
            self.tell(f"Enter a number from {minimum} to {maximum}, or q to leave.")

    def show_quote(self):
        value = self.data["quote"]
        self.tell(f"Quote {value['quote_id']} | cart version {value['cart_version']}")
        for line in value["lines"]:
            self.tell(
                f"  {line['sku']} x {line['quantity']} | "
                f"{money(line['unit_price_minor'], value['currency'])} each | "
                f"{money(line['line_total_minor'], value['currency'])}"
            )
        self.tell(f"TOTAL: {money(value['total_amount_minor'], value['currency'])}")
        self.tell(f"Expires: {value['expires_at']} (UTC). Stock is rechecked by checkout.")

    def run(self):
        self.tell(
            "Historical catalogue / simulated stock and payments. Fixed mode: zero LLM calls."
        )
        self.tell(f"State: {self.journal.path}")
        while True:
            phase = self.data["phase"]
            if phase == "session":
                session = self.call("session", operation="session", body={})
                self.journal.advance("search", **session)
            elif phase == "search":
                index = self.data.get("search_index", 0)
                name = f"search:{index}"
                pending = self.data["operations"].get(name)
                query = pending["body"]["text"] if pending else self.data.pop("initial_query", None)
                if query is None:
                    query = self.ask("Search products (or q to leave): ").strip()
                    if query.lower() in {"q", "quit"}:
                        return 0
                turn = self.call("search", operation=name, body={"text": query, "mode": "fixed"})
                if turn["llm_call_count"] != 0 or turn["extractor_source"] == "llm":
                    raise DemoError("Fixed-mode model-call invariant failed.", 3)
                self.tell(display(turn["response_text"]))
                if turn["outcome"] == "dependency_error":
                    # A completed turn is durable; replay would return its old
                    # failure. A later user retry needs a new turn identity.
                    self.journal.advance("search", search_index=index + 1)
                    raise DemoError(
                        "Catalogue unavailable or M1 turn deadline exceeded. "
                        "Resume to search again."
                    )
                if turn["outcome"] == "clarification" or not turn["products"]:
                    self.journal.advance("search", search_index=index + 1)
                    self.tell("Try another query; no purchase was submitted.")
                    continue
                self.journal.advance("select", products=turn["products"])
            elif phase == "select":
                for i, hit in enumerate(self.data["products"], 1):
                    self.tell(
                        f"{i}. {display(hit['title'])} | {hit['sku']} | "
                        f"{money(hit['price_minor'], hit['currency'])} | "
                        f"displayed available {hit['stock_available']} (advisory)"
                    )
                chosen = self.number("Select product number: ", 1, len(self.data["products"]))
                quantity = self.number("Quantity (1-10): ", 1, 10)
                self.journal.advance(
                    "cart", sku=self.data["products"][chosen - 1]["sku"], quantity=quantity
                )
            elif phase == "cart":
                cart = self.call(
                    "cart",
                    operation="cart",
                    body={
                        "quantity": self.data["quantity"],
                        "expected_cart_version": self.data["cart_version"],
                    },
                )
                self.validate_cart(cart)
                if cart["version"] != self.data["cart_version"] + 1 or [
                    (line["sku"], line["quantity"]) for line in cart["lines"]
                ] != [(self.data["sku"], self.data["quantity"])]:
                    raise DemoError("Cart update did not return the selected product/quantity.", 3)
                self.journal.advance("quote", cart_version=cart["version"], cart=cart)
            elif phase == "quote":
                value = self.call(
                    "quote",
                    operation=f"quote:{self.data.get('quote_index', 0)}",
                    body={"expected_cart_version": self.data["cart_version"]},
                )
                if (
                    value["user_id"] != self.data["identity"]["user_id"]
                    or value["cart_id"] != self.data["cart_id"]
                    or value["cart_version"] != self.data["cart_version"]
                    or [(x["sku"], x["quantity"]) for x in value["lines"]]
                    != [(x["sku"], x["quantity"]) for x in self.data["cart"]["lines"]]
                ):
                    raise DemoError("Quote identity/cart binding mismatch.", 3)
                self.journal.advance("confirm", quote=value, quote_expired=False)
            elif phase == "confirm":
                self.show_quote()
                cart = self.call("cart_read")
                self.validate_cart(cart)
                if cart["version"] != self.data["quote"]["cart_version"]:
                    raise DemoError(
                        "Cart changed. This quote cannot be confirmed; start a new demo state.", 3
                    )
                value = self.data["quote"]
                if self.data.get("quote_expired") or datetime.fromisoformat(
                    value["expires_at"].replace("Z", "+00:00")
                ) <= datetime.now(UTC):
                    self.tell("Quote expired. Request a fresh quote and review its price again.")
                    if (
                        self.ask("Type REQUOTE to continue, or Enter to leave: ").strip()
                        != "REQUOTE"
                    ):
                        return 0
                    self.journal.advance("quote", quote_index=self.data.get("quote_index", 0) + 1)
                    continue
                expected = "CONFIRM " + value["quote_id"]
                if (
                    self.ask(f"Type {expected} to purchase, or Enter to leave: ").strip()
                    != expected
                ):
                    self.tell("No checkout submitted. Resume this state to continue.")
                    return 0
                # This records the human confirmation against exactly this quote
                # and version. A resumed pending checkout reuses it even after expiry.
                self.journal.advance(
                    "checkout", confirmation_id=str(uuid4()), confirmed_at=utc_now()
                )
            elif phase == "checkout":
                try:
                    value = self.call(
                        "checkout",
                        operation="checkout:" + self.data["quote"]["quote_id"],
                        body={
                            "quote_id": self.data["quote"]["quote_id"],
                            "expected_cart_version": self.data["quote"]["cart_version"],
                            "confirmed": True,
                            "confirmation_id": self.data["confirmation_id"],
                        },
                    )
                except RejectedOperation as exc:
                    if exc.status != 409 or exc.error_code != "QUOTE_EXPIRED":
                        raise
                    # A definitive rejection permits a fresh quote and human
                    # confirmation. Uncertain outcomes never enter this branch.
                    self.journal.advance("confirm", quote_expired=True)
                    self.tell("Checkout rejected the expired quote; confirm a fresh quote.")
                    continue
                self.journal.advance("status", order_id=value["order_id"])
                self.tell(f"Order accepted: {value['order_id']} ({value['status']}).")
            elif phase == "status":
                return self.observe()
            elif phase == "done":
                self.tell(f"Order {self.data['order_id']}: {self.data['final_status']}.")
                return 0
            else:
                raise DemoError("Invalid saved demo phase.", 2)

    def validate_cart(self, cart):
        if (
            cart["cart_id"] != self.data["cart_id"]
            or cart["session_id"] != self.data["session_id"]
            or cart["user_id"] != self.data["identity"]["user_id"]
        ):
            raise DemoError("Cart identity mismatch.", 3)

    def observe(self):
        started = time.monotonic()
        while time.monotonic() - started < self.wait_seconds:
            snapshot = self.call("status")
            value = self.data["quote"]
            if (
                snapshot["order_id"] != self.data["order_id"]
                or snapshot["user_id"] != self.data["identity"]["user_id"]
                or snapshot["session_id"] != self.data["session_id"]
                or snapshot["quote_id"] != value["quote_id"]
                or snapshot["total_amount_minor"] != value["total_amount_minor"]
                or snapshot["currency"] != value["currency"]
                or snapshot["lines"] != value["lines"]
            ):
                raise DemoError("Order identity or immutable quote mismatch.", 3)
            previous = self.data.get("snapshot")
            if previous and (
                snapshot["order_version"] < previous["order_version"]
                or (snapshot["order_version"] == previous["order_version"] and snapshot != previous)
            ):
                raise DemoError("Order version regressed or conflicts with its prior snapshot.", 3)
            self.data["snapshot"] = snapshot
            self.journal.save()
            if previous is None or snapshot["order_version"] != previous["order_version"]:
                self.tell(
                    f"Order {snapshot['order_id']}: {snapshot['status']} "
                    f"(version {snapshot['order_version']}, failure={snapshot['failure_code']})."
                )
            if snapshot["status"] in {"CONFIRMED", "CANCELLED"}:
                self.journal.advance("done", final_status=snapshot["status"])
                return 0
            if snapshot["status"] == "MANUAL_REVIEW":
                raise DemoError(
                    "Order needs manual review; final outcome is unresolved. Resume to observe."
                )
            time.sleep(min(0.5, max(0, self.wait_seconds - (time.monotonic() - started))))
        raise DemoError(
            "Order is still unresolved; resume to observe. A client timeout does not cancel it."
        )


def add_arguments(parser):
    paths = parser.add_mutually_exclusive_group()
    paths.add_argument(
        "--state", type=Path, help="new state file (default: artifacts/demo/<id>/state.json)"
    )
    paths.add_argument(
        "--resume", type=Path, help="resume a saved session; reuse pending request keys"
    )
    parser.add_argument("--conversation-url", help="M1 origin; default http://127.0.0.1:8001")
    parser.add_argument("--orders-url", help="Orders origin; default http://127.0.0.1:8003")
    parser.add_argument("--namespace", help="default RUN_NAMESPACE or dev")
    parser.add_argument("--user-id", help="synthetic demo principal; default demo-user")
    parser.add_argument("--query", help="initial fixed-mode search text")
    parser.add_argument(
        "--wait-seconds", type=int, default=60, help="status polling window, 1-120 seconds"
    )


def run(args, *, ask=input, tell=print, client=None):
    path = (
        args.resume or args.state or ROOT / "artifacts/demo" / str(uuid4()) / "state.json"
    ).resolve()
    if not 1 <= args.wait_seconds <= 120:
        raise DemoError("--wait-seconds must be between 1 and 120.", 2)
    with exclusive_state(path):
        if args.resume:
            if path.stat().st_size > 4 * 1024 * 1024:
                raise DemoError("Saved state exceeds the client limit.", 2)
            data = strict_json(path.read_bytes())
            if (
                data.get("schema_version") != 1
                or data.get("mode") != "fixed"
                or data.get("phase") not in PHASES
            ):
                raise DemoError("Unsupported saved demo state.", 2)
            for supplied, saved in (
                (args.namespace, data["identity"]["namespace"]),
                (args.user_id, data["identity"]["user_id"]),
                (args.conversation_url, data["origins"]["conversation"]),
                (args.orders_url, data["origins"]["transactions"]),
            ):
                if supplied is not None and supplied.rstrip("/") != saved:
                    raise DemoError(
                        "Resume cannot change the saved identity or service origins.", 2
                    )
            if args.query is not None:
                raise DemoError(
                    "Resume uses its saved query or prompts for a new search; omit --query.", 2
                )
        else:
            if path.exists():
                raise DemoError("State already exists; use --resume or choose a new --state.", 2)
            data = {
                "schema_version": 1,
                "mode": "fixed",
                "phase": "session",
                "operations": {},
                "identity": {
                    "namespace": args.namespace or os.environ.get("RUN_NAMESPACE", "dev"),
                    "user_id": args.user_id or "demo-user",
                    "run_id": str(uuid4()),
                    "correlation_id": str(uuid4()),
                },
                "origins": {
                    "conversation": args.conversation_url or "http://127.0.0.1:8001",
                    "transactions": args.orders_url or "http://127.0.0.1:8003",
                },
            }
            if args.query is not None:
                data["initial_query"] = args.query
        RequestContext(
            **data["identity"], request_id=str(uuid4()), session_id=data.get("session_id")
        )
        for name, origin in data["origins"].items():
            TransportConfig(origin)  # reuse origin validation; no credentials or redirects
            data["origins"][name] = origin.rstrip("/")
        journal = Journal(path, data)
        journal.save()
        if client is not None:
            return Demo(journal, client, ask=ask, tell=tell, wait_seconds=args.wait_seconds).run()
        with httpx.Client(trust_env=False, follow_redirects=False) as http:
            return Demo(journal, http, ask=ask, tell=tell, wait_seconds=args.wait_seconds).run()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    add_arguments(parser)
    return command(parser.parse_args(argv))


def command(args):
    try:
        return run(args)
    except (EOFError, KeyboardInterrupt):
        print("Stopped. Saved state can be resumed with the same request keys.")
        return 0
    except DemoError as exc:
        print(str(exc))
        return exc.code
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        ValidationError,
        ContractUnavailable,
        ContractViolation,
    ):
        print("Demo configuration, state or provider contract invalid. Inspect retained evidence.")
        return 4


if __name__ == "__main__":
    sys.exit(main())
