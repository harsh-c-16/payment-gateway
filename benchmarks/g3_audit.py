"""G3 consumer projections from read-only HTTP and producer receipts, never reducers."""

from collections import Counter
from urllib.parse import quote

from projectctl.artifacts import content_hash
from projectctl.providers import DependencyError
from shared.contracts.catalog import ProductResponse
from shared.contracts.events import EventEnvelope
from shared.contracts.transactions import OrderSnapshot, PaymentOrderSnapshot, StockSnapshot


def scoped(value, context):
    if any(value.get(k) != context[k] for k in ("namespace", "run_id", "case_id")):
        raise DependencyError("G3 evidence scope mismatch")
    if value.get("collection_complete") is not True:
        raise DependencyError("G3 read-only collection incomplete")


def source_expectations(proof, context, planned_counts):
    """Learn only runtime IDs/immutable source hashes from producer/broker inputs.

    Owners supply the raw outbox envelope and broker delivery coordinates. The
    independently reviewed fixture freezes logical counts per type beforehand.
    Neither Silver nor Gold may supply this proof.
    """
    scoped(proof, context)
    if not planned_counts or any(type(n) is not int or n < 1 for n in planned_counts.values()):
        raise DependencyError("G3 positive integer logical event plan required")
    if (
        proof.get("origin") != "producer_outbox_and_broker"
        or type(proof.get("pending_outbox")) is not int
        or proof["pending_outbox"] != 0
    ):
        raise DependencyError("G3 complete producer/outbox/broker evidence unavailable")
    events, dispositions, coordinates, counts = {}, {}, set(), Counter()
    for row in proof["deliveries"]:
        wire = row["event"]
        event = EventEnvelope.model_validate(wire)
        coordinate = (row["topic"], row["partition"], row["offset"])
        if (
            event.namespace != context["namespace"]
            or event.run_id != context["run_id"]
            or row["topic"] != event.topic()
            or any(type(row[k]) is not int or row[k] < 0 for k in ("partition", "offset"))
            or coordinate in coordinates
            or not isinstance(row["record_id"], str)
            or not row["record_id"]
            or row["record_id"] in dispositions
        ):
            raise DependencyError("G3 source identity/coordinates conflict")
        coordinates.add(coordinate)
        digest = content_hash(wire)
        prior = events.get(event.event_id)
        if prior is not None and prior != digest:
            raise DependencyError("G3 immutable producer event conflict")
        dispositions[row["record_id"]] = "new_valid" if prior is None else "duplicate_delivery"
        if prior is None:
            counts[event.event_type] += 1
        events[event.event_id] = digest
    manifests = proof.get("source_manifest_ids")
    if (
        not events
        or dict(counts) != planned_counts
        or not isinstance(manifests, list)
        or not manifests
        or any(not isinstance(value, str) or not value for value in manifests)
        or len(set(manifests)) != len(manifests)
    ):
        raise DependencyError("G3 producer cohort differs from frozen event plan")
    return {"events": events, "source_dispositions": dispositions, "source_manifest_ids": manifests}


def validate_order_sources(proof, state, quoted):
    required = {"ORDER_CREATED", "ORDER_" + state["outcome"]}
    found = set()
    for row in proof["deliveries"]:
        event = row["event"]
        if event["event_type"] not in {"ORDER_CREATED", "ORDER_CONFIRMED", "ORDER_CANCELLED"}:
            continue
        payload = event["payload"]
        if (
            any(
                payload.get(k) != state[k]
                for k in ("order_id", "quote_id", "user_id", "session_id")
            )
            or payload.get("total_amount_minor") != quoted["total_amount_minor"]
            or payload.get("currency") != quoted["currency"]
        ):
            raise DependencyError("G3 producer order facts differ from captured transaction/quote")
        found.add(event["event_type"])
    if found != required:
        raise DependencyError("G3 created/final order source facts missing or contradictory")


def items(page):
    rows = page["items"]
    if type(page["count"]) is not int or page["count"] != len(rows) or len(rows) >= 1000:
        raise DependencyError("G3 bounded audit is incomplete or requires pagination")
    return rows


async def transaction_audit(http, context, principal, state, replenishment):
    """Read namespace lists to catch extra effects, then canonical resource snapshots.

    Ledger endpoint stores positive magnitudes for both kinds. Normalize the
    sign exactly once here; never use its clamped net_debit_minor summary.
    """

    async def get(service, path, model=None):
        return await http.call(context, principal, service, "GET", path, model=model)

    order_id, sku = state["order_id"], state["sku"]
    order_rows = items(await get("orders", "/internal/v1/audit/orders"))
    if [row["order_id"] for row in order_rows] != [order_id]:
        raise DependencyError("G3 isolated namespace must contain exactly the captured order")
    order = await get("orders", f"/v1/orders/{order_id}", OrderSnapshot)
    if any(order[k] != state[k] for k in ("order_id", "quote_id", "user_id", "session_id")):
        raise DependencyError("G3 order identity changed")
    reservations = items(await get("inventory", "/internal/v1/audit/reservations"))
    payment_rows = items(await get("payments", "/internal/v1/audit/payments"))
    if [row["order_id"] for row in payment_rows] != [order_id]:
        raise DependencyError("G3 payment guard cohort incomplete or unexpected")
    payment = await get(
        "payments", f"/internal/v1/payments/by-order/{order_id}", PaymentOrderSnapshot
    )
    ledger = items(await get("payments", "/internal/v1/audit/ledger"))
    signed = []
    for entry in ledger:
        amount = entry["amount_minor"]
        if (
            type(amount) is not int
            or not 0 < amount < 2**63
            or entry["kind"] not in {"DEBIT", "REVERSAL"}
        ):
            raise DependencyError(
                "G3 owner ledger requires positive int64 magnitudes and known kinds"
            )
        signed.append({**entry, "amount_minor": amount if entry["kind"] == "DEBIT" else -amount})
    stock = await get("inventory", f"/internal/v1/inventory/{quote(sku, safe='')}", StockSnapshot)
    product = await get("catalog", f"/v1/products/{quote(sku, safe='')}", ProductResponse)
    projection = product["stock"]
    if stock["sku"] != sku or product["product"]["sku"] != sku:
        raise DependencyError("G3 stock/projection SKU mismatch")
    projection_matches = projection is not None and all(
        type(projection[k]) is type(stock[k]) and projection[k] == stock[k]
        for k in ("sku", "on_hand", "reserved", "available", "stock_version", "changed_at")
    )
    if set(replenishment) != {sku} or type(replenishment[sku]) is not int:
        raise DependencyError("G3 independent replenishment evidence unavailable")
    return {
        "orders": [order],
        "reservations": reservations,
        "payments": payment["attempts"],
        "payment_guards": {order_id: {"quiesced": payment["quiesced"]}},
        "ledger": signed,
        "stocks": [{**stock, "replenished": replenishment[sku]}],
    }, projection_matches
