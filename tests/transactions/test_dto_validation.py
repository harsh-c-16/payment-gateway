"""Unit tests for shared transaction DTOs — pure validation, no database."""

import pytest
from pydantic import ValidationError

from shared.contracts.transactions import (
    AuthorizePaymentRequest,
    CreateOrderRequest,
    OrderAccepted,
    PaymentOrderSnapshot,
    QuoteLine,
    ReserveItem,
    ReserveRequest,
    StockSnapshot,
)


class TestQuoteLine:
    def test_valid(self):
        line = QuoteLine(
            sku="SKU-001",
            quantity=2,
            unit_price_minor=500,
            line_total_minor=1000,
            catalog_version=1,
        )
        assert line.line_total_minor == 1000

    def test_line_total_mismatch(self):
        with pytest.raises(ValidationError, match="line_total"):
            QuoteLine(
                sku="SKU-001",
                quantity=2,
                unit_price_minor=500,
                line_total_minor=999,
                catalog_version=1,
            )

    def test_quantity_bounds(self):
        with pytest.raises(ValidationError):
            QuoteLine(
                sku="SKU-001",
                quantity=0,
                unit_price_minor=100,
                line_total_minor=0,
                catalog_version=1,
            )
        with pytest.raises(ValidationError):
            QuoteLine(
                sku="SKU-001",
                quantity=11,
                unit_price_minor=100,
                line_total_minor=1100,
                catalog_version=1,
            )

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError, match="extra"):
            QuoteLine(
                sku="SKU-001",
                quantity=1,
                unit_price_minor=100,
                line_total_minor=100,
                catalog_version=1,
                extra=1,
            )


class TestCreateOrderRequest:
    def test_valid(self):
        req = CreateOrderRequest(
            quote_id="12345678-1234-1234-1234-123456789abc",
            session_id="12345678-1234-1234-1234-123456789abc",
            confirmation_id="12345678-1234-1234-1234-123456789abc",
        )
        assert req.quote_id == "12345678-1234-1234-1234-123456789abc"

    def test_invalid_uuid(self):
        with pytest.raises(ValidationError):
            CreateOrderRequest(quote_id="not-a-uuid", session_id="x", confirmation_id="y")


class TestReserveRequest:
    def test_valid(self):
        req = ReserveRequest(
            order_id="12345678-1234-1234-1234-123456789abc",
            items=[ReserveItem(sku="SKU-001", quantity=1)],
        )
        assert req.ttl_seconds == 30

    def test_empty_items(self):
        with pytest.raises(ValidationError):
            ReserveRequest(
                order_id="12345678-1234-1234-1234-123456789abc",
                items=[],
            )


class TestStockSnapshot:
    def test_valid(self):
        snap = StockSnapshot(
            sku="SKU-001",
            on_hand=100,
            reserved=20,
            available=80,
            stock_version=1,
            changed_at="2025-01-01T00:00:00Z",
        )
        assert snap.available == 80

    def test_invariant_violation(self):
        with pytest.raises(ValidationError, match="available"):
            StockSnapshot(
                sku="SKU-001",
                on_hand=100,
                reserved=20,
                available=90,
                stock_version=1,
                changed_at="2025-01-01T00:00:00Z",
            )

    def test_reserved_exceeds_on_hand(self):
        with pytest.raises(ValidationError):
            StockSnapshot(
                sku="SKU-001",
                on_hand=10,
                reserved=20,
                available=-10,
                stock_version=1,
                changed_at="2025-01-01T00:00:00Z",
            )


class TestAuthorizePaymentRequest:
    def test_valid(self):
        req = AuthorizePaymentRequest(
            order_id="12345678-1234-1234-1234-123456789abc",
            attempt_number=1,
            amount_minor=5000,
            currency="INR",
        )
        assert req.attempt_number == 1

    def test_attempt_bounds(self):
        with pytest.raises(ValidationError):
            AuthorizePaymentRequest(
                order_id="12345678-1234-1234-1234-123456789abc",
                attempt_number=3,
                amount_minor=5000,
                currency="INR",
            )

    def test_wrong_currency(self):
        with pytest.raises(ValidationError):
            AuthorizePaymentRequest(
                order_id="12345678-1234-1234-1234-123456789abc",
                attempt_number=1,
                amount_minor=5000,
                currency="USD",
            )


class TestPaymentOrderSnapshot:
    def test_valid(self):
        snap = PaymentOrderSnapshot(attempts=[], quiesced=False, net_debit_minor=0)
        assert snap.net_debit_minor == 0


class TestOrderAccepted:
    def test_status_url_format(self):
        accepted = OrderAccepted(
            order_id="12345678-1234-1234-1234-123456789abc",
            status="PENDING",
            status_url="/v1/orders/12345678-1234-1234-1234-123456789abc",
        )
        assert accepted.status_url == f"/v1/orders/{accepted.order_id}"
