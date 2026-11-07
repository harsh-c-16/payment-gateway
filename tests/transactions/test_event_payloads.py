"""Validate that event payloads our services emit match the registered Pydantic models."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from shared.contracts.events import InventoryEvent, OrderConfirmed, OrderEvent, PaymentEvent


class TestInventoryEventPayloads:
    """Verify payloads emitted by reservation.py match InventoryEvent."""

    def test_reserved_event_valid(self):
        payload = {
            "sku": "SKU-001",
            "on_hand": 10000,
            "reserved": 2,
            "available": 9998,
            "stock_version": 2,
            "changed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "order_id": str(uuid4()),
            "reservation_id": str(uuid4()),
            "reason_code": None,
        }
        event = InventoryEvent(**payload)
        assert event.available == event.on_hand - event.reserved

    def test_committed_event_valid(self):
        payload = {
            "sku": "SKU-001",
            "on_hand": 9998,
            "reserved": 0,
            "available": 9998,
            "stock_version": 3,
            "changed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "order_id": str(uuid4()),
            "reservation_id": str(uuid4()),
            "reason_code": None,
        }
        event = InventoryEvent(**payload)
        assert event.on_hand == 9998

    def test_released_event_valid(self):
        payload = {
            "sku": "SKU-001",
            "on_hand": 10000,
            "reserved": 0,
            "available": 10000,
            "stock_version": 4,
            "changed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "order_id": str(uuid4()),
            "reservation_id": str(uuid4()),
            "reason_code": None,
        }
        event = InventoryEvent(**payload)
        assert event.available == 10000

    def test_available_invariant_enforced(self):
        with pytest.raises(ValidationError, match="available"):
            InventoryEvent(
                sku="SKU-001",
                on_hand=100,
                reserved=10,
                available=85,  # Wrong: should be 90
                stock_version=1,
                changed_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                order_id=str(uuid4()),
                reservation_id=str(uuid4()),
                reason_code=None,
            )

    def test_reserved_exceeds_on_hand_rejected(self):
        with pytest.raises(ValidationError):
            InventoryEvent(
                sku="SKU-001",
                on_hand=5,
                reserved=10,
                available=-5,
                stock_version=1,
                changed_at=datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                order_id=str(uuid4()),
                reservation_id=str(uuid4()),
                reason_code=None,
            )


class TestPaymentEventPayloads:
    """Verify payloads emitted by authorize.py match PaymentEvent."""

    def test_success_event_valid(self):
        payload = {
            "payment_id": str(uuid4()),
            "order_id": str(uuid4()),
            "attempt_number": 1,
            "status": "SUCCESS",
            "amount_minor": 5000,
            "currency": "INR",
            "attempt_created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "failure_code": None,
            "debit_id": str(uuid4()),
            "reversal_id": None,
        }
        event = PaymentEvent(**payload)
        assert event.status == "SUCCESS"
        assert event.debit_id is not None

    def test_failed_event_valid(self):
        payload = {
            "payment_id": str(uuid4()),
            "order_id": str(uuid4()),
            "attempt_number": 1,
            "status": "FAILED",
            "amount_minor": 5000,
            "currency": "INR",
            "attempt_created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "failure_code": "SIMULATED_DECLINE",
            "debit_id": None,
            "reversal_id": None,
        }
        event = PaymentEvent(**payload)
        assert event.status == "FAILED"
        assert event.failure_code == "SIMULATED_DECLINE"

    def test_reversed_event_valid(self):
        payload = {
            "payment_id": str(uuid4()),
            "order_id": str(uuid4()),
            "attempt_number": 1,
            "status": "REVERSED",
            "amount_minor": 5000,
            "currency": "INR",
            "attempt_created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "failure_code": None,
            "debit_id": str(uuid4()),
            "reversal_id": str(uuid4()),
        }
        event = PaymentEvent(**payload)
        assert event.status == "REVERSED"
        assert event.reversal_id is not None

    def test_attempt_number_positive(self):
        """PaymentEvent allows any positive attempt_number (constraint is in the DTO, not the event)."""
        base = {
            "payment_id": str(uuid4()),
            "order_id": str(uuid4()),
            "status": "SUCCESS",
            "amount_minor": 5000,
            "currency": "INR",
            "attempt_created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "failure_code": None,
            "debit_id": str(uuid4()),
            "reversal_id": None,
        }
        PaymentEvent(**base, attempt_number=1)
        PaymentEvent(**base, attempt_number=2)
        with pytest.raises(ValidationError):
            PaymentEvent(**base, attempt_number=0)
        with pytest.raises(ValidationError):
            PaymentEvent(**base, attempt_number=-1)


class TestOrderEventPayloads:
    """Verify payloads emitted by commands.py and saga.py match OrderEvent/OrderConfirmed."""

    def test_created_event_valid(self):
        payload = {
            "order_id": str(uuid4()),
            "order_status": "PENDING",
            "total_amount_minor": 15000,
            "currency": "INR",
            "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "user_id": "user-1",
            "session_id": str(uuid4()),
            "quote_id": str(uuid4()),
            "failure_code": None,
        }
        event = OrderEvent(**payload)
        assert event.order_status == "PENDING"

    def test_cancelled_event_valid(self):
        payload = {
            "order_id": str(uuid4()),
            "order_status": "CANCELLED",
            "total_amount_minor": 15000,
            "currency": "INR",
            "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "user_id": "user-1",
            "session_id": str(uuid4()),
            "quote_id": str(uuid4()),
            "failure_code": "PAYMENT_FAILED",
        }
        event = OrderEvent(**payload)
        assert event.failure_code == "PAYMENT_FAILED"

    def test_confirmed_event_valid(self):
        payload = {
            "order_id": str(uuid4()),
            "order_status": "CONFIRMED",
            "total_amount_minor": 15000,
            "currency": "INR",
            "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "user_id": "user-1",
            "session_id": str(uuid4()),
            "quote_id": str(uuid4()),
            "failure_code": None,
            "reservation_id": str(uuid4()),
            "payment_id": str(uuid4()),
        }
        event = OrderConfirmed(**payload)
        assert event.reservation_id is not None
        assert event.payment_id is not None

    def test_confirmed_requires_ids(self):
        payload = {
            "order_id": str(uuid4()),
            "order_status": "CONFIRMED",
            "total_amount_minor": 15000,
            "currency": "INR",
            "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "user_id": "user-1",
            "session_id": str(uuid4()),
            "quote_id": str(uuid4()),
        }
        with pytest.raises(ValidationError):
            OrderConfirmed(**payload)

    def test_currency_must_be_inr(self):
        payload = {
            "order_id": str(uuid4()),
            "order_status": "PENDING",
            "total_amount_minor": 15000,
            "currency": "USD",
            "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "user_id": "user-1",
            "session_id": str(uuid4()),
            "quote_id": str(uuid4()),
        }
        with pytest.raises(ValidationError):
            OrderEvent(**payload)
