"""Thin G3 success/decline binding. Owner review and real evidence have no defaults.

Use register_g3 from an explicitly reviewed composition after supplying independent
fixtures and G3Owners callbacks. This module never generates approval records,
seeds databases, controls payments, publishes synthetic order facts or resets data.
"""

import asyncio
import json
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote as path_quote
from uuid import NAMESPACE_URL, uuid5

from benchmarks.g3_audit import (
    scoped,
    source_expectations,
    transaction_audit,
    validate_order_sources,
)
from benchmarks.g3_http import UnknownOutcome
from benchmarks.integration import CaseBinding, validate_review, validate_setup
from benchmarks.scheduler import journal, utc_now
from projectctl.artifacts import canonical_json, write_json
from projectctl.providers import DependencyError
from shared.contracts.catalog import Quote
from shared.contracts.common import RequestContext
from shared.contracts.conversation import CartSnapshot, SessionCreated, TurnResponse
from shared.contracts.transactions import OrderAccepted, OrderSnapshot

CASES = {"smoke/G3-success": "SUCCESS", "smoke/G3-decline": "DECLINED"}
REVIEW_PATHS = {
    "benchmarks/g3.py",
    "benchmarks/g3_http.py",
    "benchmarks/g3_audit.py",
    "benchmarks/g3_recovery.py",
    "benchmarks/integration.py",
    "benchmarks/reconciliation.py",
    "contracts/http/conversation.yaml",
    "contracts/http/catalog.yaml",
    "contracts/http/transactions.yaml",
    "contracts/http/analytics.yaml",
    "shared/contracts/catalog.py",
    "shared/contracts/transactions.py",
    "shared/contracts/conversation.py",
    "shared/contracts/events.py",
}


@dataclass(frozen=True)
class G3Owners:
    # Async harness handoff slots, not invented exports from teammate modules.
    fresh_namespace: object = None  # (context, frozen input) -> setup + initial stock proof
    drain: object = None  # (context with transaction IDs) -> scoped outbox/replenishment proof
    producer_receipts: object = None  # raw outbox envelopes and broker acks, before sink audit
    analytics_audit: object = None  # scoped read-only source/Silver/active Gold projection
    review_path: Path | None = None
    reviewed_exports: tuple[
        str, ...
    ] = ()  # concrete callback implementation paths pinned by review


def dependencies(owners=None):
    owners = owners or G3Owners()
    return [
        f"G3 owner {key} unavailable"
        for key in owners.__dataclass_fields__
        if not getattr(owners, key)
    ]


class G3Binding:
    def __init__(
        self,
        case_id,
        fixture_path,
        owners,
        http_factory,
        *,
        mode="real",
        poll_seconds=0.25,
        finality_seconds=120,
    ):
        if case_id not in CASES or mode not in {"real", "stub"}:
            raise ValueError("explicit G3 case and evidence mode required")
        if not 0 < poll_seconds <= 1 or not 0 < finality_seconds <= 120:
            raise ValueError("bounded polling/finality deadline required")
        self.case_id, self.fixture_path, self.owners = case_id, Path(fixture_path), owners
        self.http_factory, self.mode = http_factory, mode
        self.poll_seconds, self.finality_seconds = poll_seconds, finality_seconds

    def binding(self):
        return CaseBinding(
            self.mode,
            self.fixture_path,
            self.prepare,
            self.exercise,
            self.audit,
            self.owners.review_path,
        )

    def fixture(self):
        fixture = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        if fixture["case_id"] != self.case_id or fixture["input"].get("confirmed") is not True:
            raise DependencyError("G3 frozen explicit confirmation/case input required")
        if set(fixture["expected"]["orders"]) != {"@id:order"}:
            raise DependencyError("G3 fixture must freeze exactly one independent order")
        return fixture

    async def prepare(self, context):
        missing = dependencies(self.owners)
        if self.mode == "real":
            if missing:
                raise DependencyError("; ".join(missing))
            validate_review(self.owners.review_path, context["namespace"], self.fixture_path)
            review = json.loads(self.owners.review_path.read_text(encoding="utf-8"))
            if not REVIEW_PATHS.union(self.owners.reviewed_exports) <= {
                row["path"] for row in review["contracts"]
            }:
                raise DependencyError(
                    "G3 canonical contracts and concrete export mapping review missing"
                )
        fixture = self.fixture()
        setup = await self.owners.fresh_namespace(context, fixture["input"])
        write_json(Path(context["directory"]) / "g3_setup.json", setup)
        validate_setup(setup, context, real=self.mode == "real")
        if (
            setup.get("run_id") != context["run_id"]
            or setup.get("simulator_control_verified") is not True
            or setup.get("payment_outcome") != CASES[self.case_id]
            or canonical_json(setup.get("opening_stock"))
            != canonical_json(fixture["expected"]["opening_stock"])
        ):
            raise DependencyError(
                "G3 isolated opening stock/deterministic simulator proof unavailable"
            )
        return setup

    def client(self):
        client = self.http_factory()
        if client.mode != self.mode:
            raise DependencyError("G3 mixed real/test HTTP refused")
        return client

    async def exercise(self, context, fixture, gate):
        directory = Path(context["directory"])
        data = fixture["input"]
        request_id = str(
            uuid5(NAMESPACE_URL, context["namespace"] + context["run_id"] + self.case_id)
        )
        principal = RequestContext(
            **{key: context[key] for key in ("namespace", "run_id")},
            user_id=data["user_id"],
            correlation_id=request_id,
            request_id=request_id,
            session_id=None,
        )
        workflow = []
        state = {
            "request_id": request_id,
            "user_id": principal.user_id,
            "sku": data["sku"],
            "finality_seconds": None,
            "outcome": "UNKNOWN",
        }

        def save():
            # Preserve every transition before updating the convenient latest view.
            with (directory / "state.jsonl").open("a", encoding="utf-8") as log:
                journal(log, {"at": utc_now(), "transaction": state, "workflow": workflow})
            (directory / "transaction.json").write_bytes(canonical_json(state) + b"\n")
            (directory / "workflow.json").write_bytes(canonical_json(workflow) + b"\n")

        async with self.client() as http:

            async def call(
                service, method, path, status=200, *, body=None, suffix=None, model=None
            ):
                return await http.call(
                    context,
                    principal,
                    service,
                    method,
                    path,
                    status,
                    body=body,
                    key=request_id + ":" + suffix if suffix else None,
                    model=model,
                )

            save()
            session = await call(
                "conversation",
                "POST",
                "/v1/sessions",
                201,
                body={},
                suffix="session",
                model=SessionCreated,
            )
            principal = principal.model_copy(update={"session_id": session["session_id"]})
            state.update(session_id=session["session_id"], cart_id=session["cart_id"])
            turn = await call(
                "conversation",
                "POST",
                f"/v1/sessions/{principal.session_id}/turns",
                body={"request_id": request_id, "text": data["text"], "mode": "fixed"},
                suffix="turn",
                model=TurnResponse,
            )
            if (
                turn["llm_call_count"] != 0
                or turn["outcome"] != "success"
                or data["sku"] not in {item["sku"] for item in turn["products"]}
            ):
                raise DependencyError(
                    "G3 frozen SKU not returned by successful zero-call fixed search"
                )
            workflow.append(
                {
                    "operation": "search",
                    "search_id": turn["search_id"],
                    "llm_calls": turn["llm_call_count"],
                }
            )
            save()
            cart = await call(
                "conversation",
                "PUT",
                f"/v1/carts/{session['cart_id']}/items/{path_quote(data['sku'], safe='')}",
                body={
                    "quantity": data["quantity"],
                    "expected_cart_version": session["cart_version"],
                },
                suffix="cart",
                model=CartSnapshot,
            )
            if (
                cart["cart_id"] != state["cart_id"]
                or cart["session_id"] != principal.session_id
                or cart["user_id"] != principal.user_id
                or cart["version"] != session["cart_version"] + 1
                or [{"sku": r["sku"], "quantity": r["quantity"]} for r in cart["lines"]]
                != [{"sku": data["sku"], "quantity": data["quantity"]}]
            ):
                raise DependencyError("G3 cart identity/contents changed")
            workflow.append(
                {"operation": "cart", "cart_id": cart["cart_id"], "cart_version": cart["version"]}
            )
            save()
            quoted = await call(
                "conversation",
                "POST",
                f"/v1/carts/{cart['cart_id']}/quote",
                201,
                body={"expected_cart_version": cart["version"]},
                suffix="quote",
                model=Quote,
            )
            wanted = fixture["expected"]["orders"]["@id:order"]
            if (
                quoted["user_id"] != principal.user_id
                or quoted["cart_id"] != state["cart_id"]
                or quoted["cart_version"] != cart["version"]
                or any(
                    canonical_json(quoted[k]) != canonical_json(wanted[k])
                    for k in ("lines", "currency", "total_amount_minor")
                )
            ):
                raise DependencyError(
                    "G3 authoritative quote differs from frozen independent fixture"
                )
            state.update(
                quote_id=quoted["quote_id"],
                cart_version=cart["version"],
                confirmation_id=str(uuid5(NAMESPACE_URL, request_id + ":confirmation")),
            )
            binding = {
                k: state[k] for k in ("quote_id", "cart_id", "cart_version", "confirmation_id")
            }
            workflow.append({"operation": "quote", **binding, "displayed_quote": quoted})
            workflow.append({"operation": "confirmation", **binding, "confirmed": True})
            save()  # the exact quote and explicit control are retained BEFORE checkout
            body = {
                "quote_id": state["quote_id"],
                "expected_cart_version": cart["version"],
                "confirmed": True,
                "confirmation_id": state["confirmation_id"],
            }
            started = time.monotonic()
            accepted = None
            for _ in range(2):
                try:
                    accepted = await call(
                        "conversation",
                        "POST",
                        f"/v1/carts/{cart['cart_id']}/checkout",
                        202,
                        body=body,
                        suffix="checkout",
                        model=OrderAccepted,
                    )
                    break
                except UnknownOutcome:
                    save()  # never replace the quote, confirmation, request or key on response loss
            if accepted is None:
                # A second lost response is still unknown. A namespace-scoped backend
                # lookup can establish admission; absence cannot establish cancellation.
                page = await call("orders", "GET", "/internal/v1/audit/orders")
                from benchmarks.g3_audit import items

                matches = [
                    row
                    for row in items(page)
                    if all(row[k] == state[k] for k in ("quote_id", "user_id", "session_id"))
                ]
                if len(matches) != 1:
                    raise UnknownOutcome(
                        "G3 checkout unresolved after same-key retry/backend lookup"
                    )
                accepted = matches[0]
            state["order_id"] = accepted["order_id"]
            workflow.append({"operation": "checkout", **binding, "order_id": state["order_id"]})
            save()
            while time.monotonic() - started < self.finality_seconds:
                try:
                    snapshot = await call(
                        "orders", "GET", f"/v1/orders/{state['order_id']}", model=OrderSnapshot
                    )
                except UnknownOutcome:
                    await asyncio.sleep(self.poll_seconds)
                    continue
                if any(
                    snapshot[k] != state[k]
                    for k in ("order_id", "quote_id", "session_id", "user_id")
                ):
                    raise DependencyError("G3 backend snapshot identity mismatch")
                with (directory / "order_snapshots.jsonl").open("a", encoding="utf-8") as log:
                    journal(log, {"at": utc_now(), "snapshot": snapshot})
                (directory / "latest_order.json").write_bytes(canonical_json(snapshot) + b"\n")
                if snapshot["status"] in {"CONFIRMED", "CANCELLED"}:
                    state.update(
                        outcome=snapshot["status"], finality_seconds=time.monotonic() - started
                    )
                    workflow.append(
                        {
                            "operation": "order",
                            "order_id": state["order_id"],
                            "status": snapshot["status"],
                        }
                    )
                    save()
                    break
                await asyncio.sleep(self.poll_seconds)
            else:
                raise UnknownOutcome(
                    "G3 finality deadline; backend pending/MANUAL_REVIEW remains unresolved"
                )
        callback_context = {**context, "transaction": state}
        drain = await self.owners.drain(callback_context)
        write_json(directory / "drain.json", drain)
        scoped(drain, context)
        if type(drain.get("pending_outbox")) is not int or drain["pending_outbox"] != 0:
            raise DependencyError("G3 outbox drain incomplete")
        proof = await self.owners.producer_receipts(callback_context)
        write_json(directory / "producer_receipts.json", proof)
        sources = source_expectations(proof, context, data["logical_event_counts"])
        validate_order_sources(proof, state, quoted)
        return {
            "identities": {
                "@id:" + k: state[k]
                for k in ("session_id", "cart_id", "quote_id", "confirmation_id", "order_id")
            }
            | {
                "@id:session": state["session_id"],
                "@id:order": state["order_id"],
                "@id:quote": state["quote_id"],
            },
            "source_expectations": sources,
        }

    async def audit(self, context):
        directory = Path(context["directory"])
        state = json.loads((directory / "transaction.json").read_text(encoding="utf-8"))
        principal = RequestContext(
            **{k: context[k] for k in ("namespace", "run_id")},
            **{k: state[k] for k in ("user_id", "session_id", "request_id")},
            correlation_id=state["request_id"],
        )
        drain = json.loads((directory / "drain.json").read_text(encoding="utf-8"))
        async with self.client() as http:
            transactions, matches = await transaction_audit(
                http, context, principal, state, drain["replenishment"]
            )
        analytics = await self.owners.analytics_audit({**context, "transaction": state})
        if self.case_id == "smoke/G3-decline" and not any(
            p["status"] == "FAILED" and p["failure_code"] == "DECLINED"
            for p in transactions["payments"]
        ):
            raise DependencyError("G3 decline requires backend DECLINED payment evidence")
        write_json(directory / "analytics_raw.json", analytics)
        scoped(analytics, context)
        if analytics.get("test_mode") != self.mode:
            raise DependencyError("G3 analytics evidence mode mismatch")
        audit = {k: analytics[k] for k in ("source_dispositions", "silver_events", "active_gold")}
        audit.update(
            transactions,
            namespace=context["namespace"],
            test_mode=self.mode,
            collection_complete=True,
        )
        workflow = json.loads((directory / "workflow.json").read_text(encoding="utf-8"))
        workflow.extend(
            [
                {"operation": "projection", "matches_inventory": matches},
                {"operation": "gold", "generation": audit["active_gold"]["generation"]},
            ]
        )
        quote_binding, confirmation, checkout = workflow[2:5]
        bound = confirmation.get("confirmed") is True and all(
            quote_binding[k] == confirmation[k] == checkout[k]
            for k in ("quote_id", "cart_id", "cart_version", "confirmation_id")
        )
        return {
            **{k: context[k] for k in ("namespace", "run_id", "case_id")},
            "collection_complete": True,
            "workflow": workflow,
            "audit": audit,
            "facts": {
                "terminal_status": transactions["orders"][0]["status"],
                "workflow_ordering_valid": [r["operation"] for r in workflow]
                == [
                    "search",
                    "cart",
                    "quote",
                    "confirmation",
                    "checkout",
                    "order",
                    "projection",
                    "gold",
                ],
                "confirmation_bound_to_quote_cart": bound,
                "projection_matches_inventory": matches,
                "llm_calls": workflow[0]["llm_calls"],
            },
        }


def register_g3(registry, bindings):
    """No implicit missing-owner fallback or registrations labelled as real stubs."""
    for case_id, adapter in bindings.items():
        if case_id != adapter.case_id or adapter.mode != "real":
            raise ValueError("production G3 registration requires matching real bindings")
        registry.register_case(case_id, adapter.binding())
