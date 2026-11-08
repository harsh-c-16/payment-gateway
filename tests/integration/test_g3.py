"""Explicit double tests; no PostgreSQL/Kafka/provider integration claim."""

import asyncio
import base64
import copy
import json
from dataclasses import replace
from uuid import uuid4

import httpx
import pytest

from benchmarks.g3 import G3Binding, G3Owners, dependencies, register_g3
from benchmarks.g3_audit import source_expectations, transaction_audit, validate_order_sources
from benchmarks.g3_http import G3HTTP
from benchmarks.g3_recovery import probe_quote_expiry
from benchmarks.integration import bind_runtime_inputs, execute_reconciliation, run_cases
from benchmarks.integration_cases import BY_ID
from projectctl.config import load_config
from projectctl.providers import DependencyError, Invocation, ProviderRegistry
from shared.contracts.common import RequestContext

from .g3_double import G3Double


def execute(workspace, double):
    registry = ProviderRegistry()
    registry.register_case(double.case, double.adapter().binding())
    invocation = Invocation(
        "eval run", {"suite": ["smoke"]}, load_config(), str(uuid4()), "bench-" + uuid4().hex
    )
    result = asyncio.run(run_cases(invocation, registry, allow_test_doubles=True))
    directory = workspace / result["evidence_dir"]
    rows = [json.loads(line) for line in (directory / "tests.jsonl").read_text().splitlines()]
    row = next(row for row in rows if row["case_id"] == double.case)
    case_dir = directory / next(r["path"].split("/")[0] for r in row["artifact_refs"])
    return result, row, case_dir


@pytest.mark.parametrize("status", ["CONFIRMED", "CANCELLED"])
@pytest.mark.parametrize("lost", [0, 1, 2])
def test_g3_http_slice_preserves_identity_and_independently_reconciles(workspace, status, lost):
    double = G3Double(workspace, status, lost=lost)
    result, row, directory = execute(workspace, double)
    assert row["status"] == "PASS", row
    assert row["test_mode"] == "stub" and result["exit_code"] == 4  # other smoke cases absent
    observed = json.loads((directory / "observed.json").read_text())
    assert observed["facts"]["terminal_status"] == status
    assert double.callbacks == ["prepare", "drain", "producer", "analytics"]
    checkouts = [r for r in double.requests if r["path"].endswith("/checkout")]
    assert len(checkouts) == min(lost + 1, 2)
    assert all(
        r["body"] == checkouts[0]["body"] and r["headers"] == checkouts[0]["headers"]
        for r in checkouts
    )
    assert len({r["headers"]["x-request-id"] for r in double.requests}) == 1
    assert all(r["headers"]["x-session-id"] == double.ids["session"] for r in double.requests[1:])
    assert json.loads((directory / "transaction.json").read_text())["finality_seconds"] >= 0
    assert "explicit-test-token" not in (directory / "http.jsonl").read_text()
    original = json.loads((directory / "fixture.json").read_text())
    receipt = json.loads((directory / "exercise_receipt.json").read_text())
    bound = json.loads((directory / "bound_fixture.json").read_text())
    assert bind_runtime_inputs(original, receipt) == bound
    assert len(bound["expected"]["events"]) == 2
    assert len(bound["expected"]["source_dispositions"]) == 3
    assert bound["expected"]["orders"][double.ids["order"]]["total_amount_minor"] == 100
    if lost == 2:
        assert any(r["path"] == "/internal/v1/audit/orders" for r in double.requests)
    recheck = execute_reconciliation(
        Invocation(
            "benchmark reconcile",
            {"run_dir": result["evidence_dir"]},
            None,
            str(uuid4()),
            "bench-recheck",
        )
    )
    assert recheck["exit_code"] == 4  # missing G1/other G3 never turn green
    replayed = json.loads((workspace / recheck["evidence_dir"] / "correctness.json").read_text())
    assert next(r for r in replayed["cases"] if r["case_id"] == double.case)["status"] == "PASS"


def corrupt_total(path, value):
    if path.startswith("/v1/orders/"):
        value["total_amount_minor"] = 101


def corrupt_ledger(path, value):
    if path == "/internal/v1/audit/ledger":
        value["items"].append({**value["items"][0], "entry_id": "second-debit"})
        value["count"] += 1


def corrupt_stock(path, value):
    if path.startswith("/internal/v1/inventory/"):
        value.update(on_hand=10, available=10)


def corrupt_projection(path, value):
    if path.startswith("/v1/products/"):
        value["stock"]["stock_version"] = 2


@pytest.mark.parametrize(
    "corrupt", [corrupt_total, corrupt_ledger, corrupt_stock, corrupt_projection]
)
def test_g3_rejects_corrupt_real_shaped_snapshots(workspace, corrupt):
    double = G3Double(workspace, corrupt=corrupt)
    _, row, _ = execute(workspace, double)
    assert row["status"] == "FAIL", row
    assert any(not item["passed"] for item in row["assertions"])


@pytest.mark.parametrize("missing", ["ledger", "active_gold", "receipts", "producer"])
def test_missing_owner_evidence_blocks_pass(workspace, missing):
    double = G3Double(workspace)
    if missing == "ledger":
        double.corrupt = lambda path, value: (
            value.clear() if path.endswith("audit/ledger") else None
        )
    elif missing == "producer":

        async def producer(context):
            return {"collection_complete": False}

        double.owners = replace(double.owners, producer_receipts=producer)
    else:

        async def analytics(context):
            value = await double.analytics(context)
            value.pop("active_gold" if missing == "active_gold" else "source_dispositions")
            return value

        double.owners = replace(double.owners, analytics_audit=analytics)
    _, row, _ = execute(workspace, double)
    assert row["status"] == "INCOMPLETE", row


def test_manual_review_timeout_keeps_unknown_and_null_finality(workspace):
    double = G3Double(workspace)

    def pending(path, result):
        if path.startswith("/v1/orders/"):
            result["status"] = "MANUAL_REVIEW"

    double.corrupt = pending
    _, row, directory = execute(workspace, double)
    assert row["status"] == "INCOMPLETE"
    state = json.loads((directory / "transaction.json").read_text())
    assert state["outcome"] == "UNKNOWN" and state["finality_seconds"] is None
    assert double.callbacks == ["prepare"]
    assert json.loads((directory / "latest_order.json").read_text())["status"] == "MANUAL_REVIEW"


def test_changed_quote_is_rejected_before_explicit_confirmation(workspace):
    double = G3Double(workspace)

    def wrong_quote(path, value):
        if path.endswith("/quote"):
            value["lines"][0]["unit_price_minor"] = 101
            value["lines"][0]["line_total_minor"] = value["total_amount_minor"] = 101

    double.corrupt = wrong_quote
    _, row, _ = execute(workspace, double)
    assert row["status"] == "INCOMPLETE"
    assert not any(r["path"].endswith("/checkout") for r in double.requests)


def test_real_binding_needs_review_before_setup_and_refuses_http_doubles(workspace):
    double = G3Double(workspace)
    adapter = G3Binding(double.case, double.fixture_path, G3Owners(), double.http)
    assert dependencies() and not double.callbacks
    with pytest.raises(DependencyError, match="unavailable"):
        asyncio.run(adapter.prepare({"namespace": "bench-test"}))
    with pytest.raises(DependencyError, match="mixed real/test"):
        adapter.client()
    with pytest.raises(ValueError, match="real bindings"):
        register_g3(ProviderRegistry(), {double.case: double.adapter()})
    with pytest.raises(ValueError, match="real HTTP"):
        G3HTTP(
            {"orders": "http://orders.test"}, "token", transport=httpx.MockTransport(lambda _: None)
        )


@pytest.mark.parametrize("change", ["offset", "hash", "scope", "count", "missing"])
def test_producer_cohort_has_independent_counts_and_immutable_duplicates(workspace, change):
    double = G3Double(workspace)
    context = {
        "namespace": "bench-source",
        "run_id": "source-test",
        "case_id": double.case,
        "transaction": {"request_id": str(uuid4())},
    }
    proof = asyncio.run(double.producer(context))
    if change == "offset":
        proof["deliveries"][-1]["offset"] = 0
    elif change == "hash":
        proof["deliveries"][-1]["event"]["produced_at"] = "2026-11-07T12:00:01Z"
    elif change == "scope":
        proof["deliveries"][0]["event"]["run_id"] = "wrong-run"
    elif change == "count":
        proof["deliveries"] = proof["deliveries"][:1]
    else:
        proof["collection_complete"] = False
    with pytest.raises(DependencyError):
        source_expectations(proof, context, double.fixture["input"]["logical_event_counts"])


def test_compaction_boundary_is_not_stale_manifest_rejection():
    from analytics.compaction.faults import BARRIER, TARGET

    assert (BARRIER, TARGET) == ("after_candidate_files_before_publish", "compaction")
    stale = BY_ID["T-12/stale-compaction"]
    assert (stale.barrier, stale.target) == ("before_manifest_swap", "compaction-publisher")
    assert not any((case.barrier, case.target) == (BARRIER, TARGET) for case in BY_ID.values())


@pytest.mark.parametrize("raw", [b'{"a":1,"a":2}', b'{"a":NaN}', b"\xff"])
def test_http_preserves_invalid_response_bytes_before_refusal(workspace, raw):
    principal = RequestContext(
        namespace="bench-invalid",
        run_id="invalid",
        user_id="fixture",
        request_id=str(uuid4()),
        correlation_id=str(uuid4()),
        session_id=None,
    )

    async def read():
        async with G3HTTP(
            {"orders": "http://orders.test"},
            "secret-test-token",
            mode="stub",
            transport=httpx.MockTransport(lambda _: httpx.Response(200, content=raw)),
        ) as http:
            await http.call(
                {"directory": str(workspace)},
                principal,
                "orders",
                "GET",
                "/internal/v1/audit/orders",
            )

    with pytest.raises(ValueError):
        asyncio.run(read())
    rows = [json.loads(line) for line in (workspace / "http.jsonl").read_text().splitlines()]
    assert base64.b64decode(rows[-1]["body_base64"]) == raw
    assert "secret-test-token" not in (workspace / "http.jsonl").read_text()


def test_http_whole_response_deadline_retains_unknown_and_closes(workspace, monkeypatch):
    import benchmarks.g3_http as boundary

    monkeypatch.setattr(boundary, "REQUEST_TIMEOUT_SECONDS", 0.05, raising=False)

    class SlowStream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b'{"value":'
            await asyncio.sleep(0.2)
            yield b"1}"

        async def aclose(self):
            self.closed = True

    stream = SlowStream()
    principal = RequestContext(
        namespace="bench-timeout",
        run_id="timeout",
        user_id="fixture",
        request_id=str(uuid4()),
        correlation_id=str(uuid4()),
        session_id=None,
    )

    async def run():
        async with G3HTTP(
            {"orders": "http://orders.test"},
            "explicit-test-token",
            mode="stub",
            transport=httpx.MockTransport(
                lambda _: httpx.Response(
                    202, stream=stream, headers={"content-type": "application/json"}
                )
            ),
        ) as http:
            await http.call(
                {"directory": str(workspace)},
                principal,
                "orders",
                "POST",
                "/v1/orders",
                status=202,
                body={},
                key="original-key",
            )

    with pytest.raises(boundary.UnknownOutcome):
        asyncio.run(run())
    assert stream.closed
    rows = [json.loads(line) for line in (workspace / "http.jsonl").read_text().splitlines()]
    assert rows[-1]["phase"] == "unknown" and rows[-1]["finality_seconds"] is None


def test_signed_reversal_uses_raw_ledger_and_never_clamped_summary(workspace):
    double = G3Double(workspace, "CANCELLED")
    payment = double.payment()
    double.payment = lambda: {**payment, "status": "REVERSED"}

    def reversed_ledger(path, page):
        if path.endswith("audit/ledger"):
            entry = {
                "entry_id": "debit",
                "order_id": double.ids["order"],
                "payment_id": double.ids["payment"],
                "currency": "INR",
                "amount_minor": 100,
            }
            page.update(
                items=[
                    {**entry, "kind": "DEBIT"},
                    {**entry, "entry_id": "reversal", "kind": "REVERSAL"},
                ],
                count=2,
                net_debit_minor=999999,
            )

    double.corrupt = reversed_ledger
    principal = RequestContext(
        namespace="bench-reversal",
        run_id="reversal",
        user_id=double.user,
        request_id=str(uuid4()),
        correlation_id=str(uuid4()),
        session_id=double.ids["session"],
    )
    state = {
        "order_id": double.ids["order"],
        "quote_id": double.ids["quote"],
        "user_id": double.user,
        "session_id": double.ids["session"],
        "sku": double.sku,
    }

    async def collect():
        async with double.http() as http:
            return await transaction_audit(
                http, {"directory": str(workspace)}, principal, state, {double.sku: 0}
            )

    audit, projection = asyncio.run(collect())
    assert projection and [e["amount_minor"] for e in audit["ledger"]] == [100, -100]
    assert sum(e["amount_minor"] for e in audit["ledger"]) == 0
    assert all(r["method"] == "GET" for r in double.requests)


def test_producer_order_payload_must_match_captured_quote_and_order(workspace):
    double = G3Double(workspace)
    context = {
        "namespace": "bench-source",
        "run_id": "source-test",
        "case_id": double.case,
        "transaction": {"request_id": str(uuid4())},
    }
    proof = asyncio.run(double.producer(context))
    state = {
        "order_id": double.ids["order"],
        "quote_id": double.ids["quote"],
        "user_id": double.user,
        "session_id": double.ids["session"],
        "outcome": "CONFIRMED",
    }
    validate_order_sources(proof, state, {"total_amount_minor": 100, "currency": "INR"})
    proof["deliveries"][0]["event"]["payload"]["total_amount_minor"] = 101
    with pytest.raises(DependencyError, match="differ"):
        validate_order_sources(proof, state, {"total_amount_minor": 100, "currency": "INR"})


def test_decline_case_needs_actual_declined_payment(workspace):
    double = G3Double(workspace, "CANCELLED")
    payment = double.payment()
    double.payment = lambda: {**payment, "failure_code": "RETRYABLE_PROVIDER_FAILURE"}
    _, row, _ = execute(workspace, double)
    assert row["status"] == "INCOMPLETE"
    assert "DECLINED" in row["failure_reason"] or "DependencyError" in row["failure_reason"]


@pytest.mark.parametrize("defect", [None, "reject-retry", "accept-expired", "ignore-conflict"])
def test_quote_expiry_idempotency_consumer_regression(workspace, defect):
    """HTTP scripts define the consumer contract; real Orders probe remains NOT_RUN."""
    ids = {key: str(uuid4()) for key in ("session", "quote", "fresh", "order", "cart", "confirm")}
    principal = RequestContext(
        namespace="bench-expiry",
        run_id="expiry",
        user_id="fixture-user",
        correlation_id=str(uuid4()),
        request_id=str(uuid4()),
        session_id=ids["session"],
    )
    request = {
        "quote_id": ids["quote"],
        "session_id": ids["session"],
        "confirmation_id": ids["confirm"],
    }
    original = copy.deepcopy(request)
    seen = []

    def error(code):
        return httpx.Response(
            409,
            json={
                "error": {"code": code, "message": "fixture", "retryable": False, "details": {}},
                "correlation_id": principal.correlation_id,
            },
        )

    def handle(req):
        if req.method == "GET":
            return httpx.Response(
                200,
                json={
                    "quote_id": req.url.path.rsplit("/", 1)[1],
                    "user_id": principal.user_id,
                    "cart_id": ids["cart"],
                    "cart_version": 1,
                    "lines": [
                        {
                            "sku": "fixture",
                            "quantity": 1,
                            "unit_price_minor": 100,
                            "line_total_minor": 100,
                            "catalog_version": 1,
                        }
                    ],
                    "total_amount_minor": 100,
                    "currency": "INR",
                    "created_at": "2000-01-01T00:00:00Z",
                    "expires_at": "2000-01-01T00:01:00Z",
                },
            )
        body, key = json.loads(req.content), req.headers["idempotency-key"]
        seen.append((body, key))
        if body["quote_id"] == ids["quote"] and defect == "reject-retry":
            return error("QUOTE_EXPIRED")
        if body["quote_id"] != ids["quote"] and defect != "accept-expired":
            if key == "original" and defect == "ignore-conflict":
                return error("QUOTE_EXPIRED")
            return error("IDEMPOTENCY_CONFLICT" if key == "original" else "QUOTE_EXPIRED")
        return httpx.Response(
            202,
            json={
                "order_id": ids["order"],
                "status": "PENDING",
                "status_url": "/v1/orders/" + ids["order"],
            },
        )

    async def probe():
        async with G3HTTP(
            {"catalog": "http://catalog.test", "orders": "http://orders.test"},
            "token",
            mode="stub",
            transport=httpx.MockTransport(handle),
        ) as http:
            return await probe_quote_expiry(
                http,
                {"directory": str(workspace)},
                principal,
                accepted_request=request,
                order_id=ids["order"],
                original_key="original",
                retry_key="new-key",
                fresh_expired_request={**request, "quote_id": ids["fresh"]},
            )

    if defect:
        with pytest.raises(DependencyError):
            asyncio.run(probe())
    else:
        assert asyncio.run(probe())["changed_input_conflicted"]
        assert seen[:2] == [(original, "original"), (original, "new-key")]
    assert request == original
