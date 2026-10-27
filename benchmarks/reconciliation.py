"""Read-only independent oracle over harness evidence projections.

These projections are not provider DTOs. P3 tests supply explicit doubles;
real-provider export/schema bindings require the explicit P8 review handoff.
"""

import re
from collections import Counter, defaultdict

from benchmarks.metrics import nonnegative


def reconcile_run(expected, observed, *, binding_review=None):
    """Return common ReconciliationResult inside a truthful harness status wrapper.

    Never imports reducers/normalizers, mutates inputs or issues corrective writes.
    Missing evidence cannot become a successful reconciliation of an empty run.
    """
    failures, missing, unexpected, conflicting = [], set(), set(), set()
    result = {
        "passed": False,
        "counts_by_disposition": {},
        "missing_ids": [],
        "unexpected_ids": [],
        "conflicting_ids": [],
        "totals_by_currency": {},
        "invariant_failures": failures,
        "source_manifest_ids": [],
    }
    report = {
        "schema_version": 1,
        "test_mode": observed.get("test_mode", "undeclared"),
        "status": "INCOMPLETE",
        "unresolved_count": 0,
        "reconciliation": result,
    }

    def fail(code, identifier=""):
        failures.append(code + (":" + str(identifier) if identifier else ""))

    def unique(rows, key, code):
        index = {}
        for row in rows:
            identity = row[key]
            if not isinstance(identity, str) or not identity:
                raise ValueError("evidence identities must be nonempty strings")
            if identity in index:
                fail(code, identity)
                conflicting.add(identity)
            index[identity] = row
        return index

    def money(value, *, signed=False):
        if type(value) is not int or not -(2**63) <= value < 2**63 or (not signed and value < 0):
            raise ValueError("evidence money must be int64 minor units")
        return value

    try:
        if observed["test_mode"] not in {"stub", "real"}:
            raise ValueError("explicit evidence test mode required")
        if type(observed["collection_complete"]) is not bool:
            raise ValueError("collection completeness must be an explicit Boolean")
        if observed["namespace"] != expected["namespace"]:
            fail("NAMESPACE_MISMATCH")
        expected_events = expected["events"]
        if not isinstance(expected_events, dict) or not expected_events:
            raise ValueError("nonempty independent event expectations required")
        if any(not isinstance(identity, str) or not identity for identity in expected_events):
            raise ValueError("independent logical event identities required")
        if any(not re.fullmatch(r"[0-9a-f]{64}", digest) for digest in expected_events.values()):
            raise ValueError("expected immutable content SHA-256 required")
        wanted_dispositions = expected["source_dispositions"]
        receipts = unique(
            observed["source_dispositions"], "record_id", "DUPLICATE_SOURCE_DISPOSITION"
        )
        for identity in set(wanted_dispositions) | set(receipts):
            if identity not in receipts:
                fail("MISSING_SOURCE_DISPOSITION", identity)
            elif identity not in wanted_dispositions:
                fail("UNEXPECTED_SOURCE_DISPOSITION", identity)
            elif receipts[identity]["disposition"] != wanted_dispositions[identity]:
                fail("WRONG_SOURCE_DISPOSITION", identity)
        result["counts_by_disposition"] = dict(
            Counter(row["disposition"] for row in receipts.values())
        )
        silver = unique(observed["silver_events"], "event_id", "DUPLICATE_SILVER_EFFECT")
        missing.update(set(expected_events) - silver.keys())
        unexpected.update(silver.keys() - set(expected_events))
        for identity in set(expected_events) & silver.keys():
            if silver[identity]["content_sha256"] != expected_events[identity]:
                conflicting.add(identity)
                fail("EVENT_CONTENT_CONFLICT", identity)
        gold = observed["active_gold"]
        if not re.fullmatch(r"[0-9a-f]{64}", gold["manifest_sha256"]):
            raise ValueError("active manifest SHA-256 required")
        nonnegative(gold["generation"], integer=True)
        if (
            gold["generation"] < 1
            or gold["generation"] != gold["query_generation"]
            or gold["manifest_sha256"] != gold["query_manifest_sha256"]
        ):
            fail("STALE_MANIFEST_OR_QUERY_GENERATION")
        if gold["namespace"] != expected["namespace"]:
            fail("GOLD_NAMESPACE_MISMATCH")
        if set(gold["source_manifest_ids"]) != set(expected["source_manifest_ids"]):
            fail("STALE_SOURCE_MANIFEST_REFERENCE")
        result["source_manifest_ids"] = list(gold["source_manifest_ids"])
        membership_counts = Counter(gold["membership_ids"])
        if any(not isinstance(identity, str) or not identity for identity in membership_counts):
            raise ValueError("active membership identities must be nonempty strings")
        for identity, count in membership_counts.items():
            if count != 1:
                fail("DUPLICATE_GOLD_EFFECT", identity)
        members = set(membership_counts)
        missing.update(set(expected_events) - members)
        unexpected.update(members - set(expected_events))
        if not members <= silver.keys():
            fail("GOLD_EVENT_WITHOUT_SILVER")
        visibility = unique(gold["visibility_receipts"], "event_id", "DUPLICATE_VISIBILITY_RECEIPT")
        for identity, receipt in visibility.items():
            if (
                identity not in members
                or receipt["generation"] != gold["generation"]
                or receipt["manifest_sha256"] != gold["manifest_sha256"]
            ):
                fail("FALSE_GOLD_VISIBILITY", identity)
        if members - visibility.keys():
            fail("MISSING_VISIBILITY_MEMBERSHIP_PROOF")
        for total in gold["totals_by_currency"].values():
            money(total)
        result["totals_by_currency"] = dict(gold["totals_by_currency"])
        if result["totals_by_currency"] != expected["gold_totals_by_currency"]:
            fail("BAD_GOLD_MONETARY_TOTAL")
        if gold["business_rows"] != expected["gold_business_rows"]:
            fail("BAD_GOLD_BUSINESS_ROWS")

        orders = unique(observed["orders"], "order_id", "DUPLICATE_ORDER")
        reservations = unique(observed["reservations"], "order_id", "DUPLICATE_RESERVATION")
        payments = unique(observed["payments"], "payment_id", "DUPLICATE_PAYMENT")
        unique(observed["ledger"], "entry_id", "DUPLICATE_LEDGER_ID")
        unique(observed["stocks"], "sku", "DUPLICATE_STOCK_SNAPSHOT")
        attempts = set()
        active_payments = Counter()
        for payment in payments.values():
            attempt = (payment["order_id"], payment["attempt_number"])
            if attempt in attempts:
                fail("DUPLICATE_PAYMENT_ATTEMPT", payment["order_id"])
            attempts.add(attempt)
            nonnegative(payment["attempt_number"], integer=True)
            if payment["attempt_number"] not in {1, 2}:
                fail("ILLEGAL_PAYMENT_ATTEMPT", payment["order_id"])
            active_payments[payment["order_id"]] += payment["status"] in {"PENDING", "SUCCESS"}
        for order_id, count in active_payments.items():
            if count > 1:
                fail("OVERLAPPING_PAYMENT_ATTEMPTS", order_id)
        ledger_by_order, ledger_by_payment = defaultdict(list), defaultdict(list)
        for entry in observed["ledger"]:
            amount = money(entry["amount_minor"], signed=True)
            if (
                entry["kind"] not in {"DEBIT", "REVERSAL"}
                or (entry["kind"] == "DEBIT" and amount <= 0)
                or (entry["kind"] == "REVERSAL" and amount >= 0)
            ):
                fail("ILLEGAL_LEDGER_SIGN", entry["entry_id"])
            payment = payments.get(entry["payment_id"])
            if payment is None or payment["order_id"] != entry["order_id"]:
                fail("LEDGER_PAYMENT_BINDING", entry["entry_id"])
            if payment is not None and entry["currency"] != payment["currency"]:
                fail("LEDGER_CURRENCY_MISMATCH", entry["entry_id"])
            ledger_by_order[entry["order_id"]].append(entry)
            ledger_by_payment[entry["payment_id"]].append(entry)
        for order_id, entries in ledger_by_order.items():
            if sum(entry["kind"] == "DEBIT" for entry in entries) > 1:
                fail("DUPLICATE_DEBIT_EFFECT", order_id)
        for payment_id, payment in payments.items():
            if observed["payment_guards"][payment["order_id"]]["quiesced"] is True and payment[
                "status"
            ] in {"PENDING", "SUCCESS"}:
                fail("QUIESCED_PAYMENT_STATE_CONFLICT", payment_id)
            if (
                payment["order_id"] in orders
                and payment["currency"] != orders[payment["order_id"]]["currency"]
            ):
                fail("PAYMENT_CURRENCY_MISMATCH", payment_id)
            entries = ledger_by_payment[payment_id]
            debits = [entry for entry in entries if entry["kind"] == "DEBIT"]
            reversals = [entry for entry in entries if entry["kind"] == "REVERSAL"]
            amount = money(payment["amount_minor"])
            if len(debits) > 1 or len(reversals) > 1:
                fail("DUPLICATE_PAYMENT_EFFECT", payment_id)
            if (
                any(entry["amount_minor"] != amount for entry in debits)
                or any(entry["amount_minor"] != -amount for entry in reversals)
                or (reversals and not debits)
            ):
                fail("BAD_PAYMENT_LEDGER_AMOUNT", payment_id)
            status = payment["status"]
            if status not in {"PENDING", "SUCCESS", "FAILED", "CANCELLED", "REVERSED"}:
                fail("ILLEGAL_PAYMENT_STATE", payment_id)
            if status == "SUCCESS" and (len(debits) != 1 or reversals):
                fail("SUCCESS_WITHOUT_UNREVERSED_DEBIT", payment_id)
            if status == "REVERSED" and (len(debits) != 1 or len(reversals) != 1):
                fail("REVERSED_WITHOUT_LEDGER_PROOF", payment_id)
            if status in {"PENDING", "FAILED", "CANCELLED"} and entries:
                fail("PAYMENT_STATE_LEDGER_CONFLICT", payment_id)

        held, sold = Counter(), Counter()
        for order_id, reservation in reservations.items():
            state = reservation["state"]
            if state not in {"ACTIVE", "COMMITTED", "RELEASED", "EXPIRED"}:
                fail("ILLEGAL_RESERVATION_STATE", order_id)
            reserved_skus = set()
            for line in reservation["items"]:
                if line["sku"] in reserved_skus:
                    fail("DUPLICATE_RESERVATION_LINE", order_id)
                reserved_skus.add(line["sku"])
                quantity = nonnegative(line["quantity"], integer=True)
                if not 1 <= quantity <= 10:
                    fail("ILLEGAL_RESERVATION_QUANTITY", order_id)
                if state == "ACTIVE":
                    held[line["sku"]] += quantity
                elif state == "COMMITTED":
                    sold[line["sku"]] += quantity
        expected_orders = expected["orders"]
        if orders.keys() != expected_orders.keys():
            fail("ORDER_SET_MISMATCH")
        for order_id, quote in expected_orders.items():
            if order_id not in orders:
                missing.add(order_id)
                continue
            order = orders[order_id]
            if any(
                order[field] != quote[field]
                for field in (
                    "quote_id",
                    "currency",
                    "total_amount_minor",
                    "lines",
                    "user_id",
                    "session_id",
                )
            ):
                fail("IMMUTABLE_QUOTE_ORDER_MISMATCH", order_id)
            total = money(order["total_amount_minor"])
            line_sum, skus = 0, set()
            for line in order["lines"]:
                quantity = nonnegative(line["quantity"], integer=True)
                version = nonnegative(line["catalog_version"], integer=True)
                unit = money(line["unit_price_minor"])
                if (
                    not 1 <= quantity <= 10
                    or version < 1
                    or not 1 <= unit <= 1_000_000_000
                    or line["sku"] in skus
                ):
                    fail("ILLEGAL_ORDER_LINE", order_id)
                skus.add(line["sku"])
                if money(line["line_total_minor"]) != quantity * unit:
                    fail("BAD_ORDER_LINE_TOTAL", order_id)
                line_sum += line["line_total_minor"]
            if not 1 <= len(skus) <= 20 or line_sum != total:
                fail("BAD_ORDER_TOTAL", order_id)
            entries = ledger_by_order[order_id]
            net = sum(entry["amount_minor"] for entry in entries)
            reservation = reservations.get(order_id)
            if order["status"] == "CONFIRMED":
                if (
                    reservation is None
                    or reservation["state"] != "COMMITTED"
                    or net != total
                    or sum(entry["kind"] == "DEBIT" for entry in entries) != 1
                ):
                    fail("UNRECONCILED_CONFIRMATION", order_id)
                successful = [
                    payment
                    for payment in payments.values()
                    if payment["order_id"] == order_id and payment["status"] == "SUCCESS"
                ]
                if len(successful) != 1:
                    fail("CONFIRMED_WITHOUT_SUCCESS_PAYMENT", order_id)
            elif order["status"] == "CANCELLED":
                if (
                    net != 0
                    or observed["payment_guards"][order_id]["quiesced"] is not True
                    or reservation is None
                    or reservation["state"] not in {"RELEASED", "EXPIRED"}
                    or any(
                        payment["status"] in {"SUCCESS", "PENDING"}
                        for payment in payments.values()
                        if payment["order_id"] == order_id
                    )
                ):
                    fail("UNRECONCILED_CANCELLATION", order_id)
            elif order["status"] in {
                "PENDING",
                "RESERVING",
                "PAYMENT_PENDING",
                "COMMITTING_STOCK",
                "COMPENSATING",
                "MANUAL_REVIEW",
            }:
                report["unresolved_count"] += 1
            else:
                fail("ILLEGAL_ORDER_STATE", order_id)
            if (
                reservation is not None
                and (reservation["items"] or reservation["state"] in {"ACTIVE", "COMMITTED"})
                and Counter({line["sku"]: line["quantity"] for line in reservation["items"]})
                != Counter({line["sku"]: line["quantity"] for line in order["lines"]})
            ):
                fail("RESERVATION_ORDER_ITEMS_MISMATCH", order_id)
        stock_skus = set()
        for stock in observed["stocks"]:
            sku = stock["sku"]
            stock_skus.add(sku)
            for field in ("on_hand", "reserved", "available", "replenished"):
                if type(stock[field]) is not int:
                    raise ValueError("stock counts must be integers")
                if stock[field] < 0:
                    fail("ILLEGAL_STOCK_STATE", sku)
            opening = expected["opening_stock"][sku]
            nonnegative(opening, integer=True)
            replenished = expected["replenishment"][sku]
            nonnegative(replenished, integer=True)
            if stock["replenished"] != replenished:
                fail("UNEXPECTED_REPLENISHMENT", sku)
            if (
                stock["reserved"] > stock["on_hand"]
                or stock["available"] != stock["on_hand"] - stock["reserved"]
            ):
                fail("ILLEGAL_STOCK_STATE", sku)
            if opening + replenished - sold[sku] != stock["on_hand"]:
                fail("INVENTORY_CONSERVATION", sku)
            if stock["reserved"] != held[sku]:
                fail("ACTIVE_RESERVATION_STOCK_MISMATCH", sku)
        if stock_skus != set(expected["opening_stock"]) or (set(held) | set(sold)) - stock_skus:
            fail("STOCK_SET_MISMATCH")
        if (
            set(reservations) - orders.keys()
            or set(ledger_by_order) - orders.keys()
            or {payment["order_id"] for payment in payments.values()} - orders.keys()
        ):
            fail("ORPHAN_TRANSACTION_EFFECT")
        if missing:
            fail("MISSING_EXPECTED_IDS")
        if unexpected:
            fail("UNEXPECTED_IDS")
        reviewed = (
            isinstance(binding_review, dict)
            and binding_review.get("namespace") == expected["namespace"]
            and set(binding_review.get("reviewers", []))
            == {"Jaineel", "Harsh", "Aditya", "Vichitr"}
            and re.fullmatch(r"[0-9a-f]{64}", binding_review.get("review_sha256", ""))
            and bool(binding_review.get("contracts"))
        )
        incomplete = (
            not observed["collection_complete"]
            or (observed["test_mode"] == "real" and not reviewed)
            or report["unresolved_count"] > 0
        )
        if observed["test_mode"] == "real" and not reviewed:
            report["dependency"] = (
                "real provider audit/membership bindings pending owner review; "
                "no real integration pass"
            )
        report["status"] = "FAIL" if failures else "INCOMPLETE" if incomplete else "PASS"
        result["passed"] = report["status"] == "PASS"
    except (KeyError, TypeError, ValueError) as error:
        fail("MISSING_OR_INVALID_EVIDENCE", type(error).__name__)
        report["status"] = "FAIL"
    result.update(
        missing_ids=sorted(missing),
        unexpected_ids=sorted(unexpected),
        conflicting_ids=sorted(conflicting),
    )
    return report


def compare_fixture_output(expected, observed):
    """Compare independently authored partial-field expectations without learning labels."""
    failures = []

    def compare(wanted, actual, path):
        if isinstance(wanted, dict):
            if not isinstance(actual, dict):
                failures.append(path)
                return
            for key, value in wanted.items():
                if key not in actual:
                    failures.append(path + "/" + key)
                else:
                    compare(value, actual[key], path + "/" + key)
        elif type(wanted) is not type(actual) or wanted != actual:
            failures.append(path)

    compare(expected, observed, "")
    return {"passed": not failures, "mismatched_paths": failures}
