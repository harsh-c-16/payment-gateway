"""Unit tests for payment authorization logic — mocked DB."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from services.payments.errors import ServiceError


def _context():
    ctx = MagicMock()
    ctx.namespace = "dev"
    ctx.run_id = "test-run"
    ctx.user_id = "user-1"
    ctx.correlation_id = "corr-1"
    ctx.request_id = "req-1"
    ctx.session_id = "sess-1"
    return ctx


def _mock_db():
    db = MagicMock()
    tx = MagicMock()
    db.transaction.return_value.__enter__ = MagicMock(return_value=tx)
    db.transaction.return_value.__exit__ = MagicMock(return_value=False)
    return db, tx


class TestAuthorize:
    def test_idempotent_returns_existing_attempt(self):
        from services.payments.authorize import authorize

        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        request = MagicMock()
        request.order_id = "o1"
        request.attempt_number = 1
        request.amount_minor = 5000
        request.currency = "INR"

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            cursor = MagicMock()
            if call_count["n"] == 1:  # INSERT payment_orders
                return cursor
            elif call_count["n"] == 2:  # SELECT quiesced
                cursor.fetchone.return_value = {"quiesced": False}
                return cursor
            elif call_count["n"] == 3:  # INSERT attempt ON CONFLICT
                cursor.fetchone.return_value = None  # already exists
                return cursor
            elif call_count["n"] == 4:  # SELECT existing attempt
                cursor.fetchone.return_value = {
                    "payment_id": "p-existing",
                    "status": "SUCCESS",
                    "amount_minor": 5000,
                }
                return cursor
            elif call_count["n"] == 5:  # _attempt_snapshot
                cursor.fetchone.return_value = {
                    "payment_id": "p-existing",
                    "order_id": "o1",
                    "attempt_number": 1,
                    "status": "SUCCESS",
                    "amount_minor": 5000,
                    "currency": "INR",
                    "failure_code": None,
                    "debit_id": "d1",
                    "reversal_id": None,
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
                return cursor
            return cursor

        tx.execute.side_effect = side_effect
        result = authorize(db, events, "dev", request, ctx)
        assert result["payment_id"] == "p-existing"
        assert result["status"] == "SUCCESS"

    def test_rejects_quiesced_order(self):
        from services.payments.authorize import authorize

        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        request = MagicMock()
        request.order_id = "o1"
        request.attempt_number = 1
        request.amount_minor = 5000
        request.currency = "INR"

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            cursor = MagicMock()
            if call_count["n"] == 1:  # INSERT payment_orders
                return cursor
            elif call_count["n"] == 2:  # SELECT quiesced
                cursor.fetchone.return_value = {"quiesced": True}
                return cursor
            return cursor

        tx.execute.side_effect = side_effect

        with pytest.raises(ServiceError) as exc_info:
            authorize(db, events, "dev", request, ctx)
        assert exc_info.value.status == 409

    @patch("services.payments.authorize.random")
    def test_simulated_success_creates_debit(self, mock_random):
        from services.payments.authorize import authorize

        mock_random.random.return_value = 0.9  # > 0.15 → success
        mock_random.choice.return_value = "SIMULATED_DECLINE"

        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        request = MagicMock()
        request.order_id = "o1"
        request.attempt_number = 1
        request.amount_minor = 5000
        request.currency = "INR"

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            cursor = MagicMock()
            if call_count["n"] == 1:  # INSERT payment_orders
                return cursor
            elif call_count["n"] == 2:  # SELECT quiesced
                cursor.fetchone.return_value = {"quiesced": False}
                return cursor
            elif call_count["n"] == 3:  # INSERT attempt
                cursor.fetchone.return_value = {"payment_id": "p1"}
                return cursor
            elif call_count["n"] == 4:  # UPDATE status SUCCESS
                return cursor
            elif call_count["n"] == 5:  # INSERT ledger DEBIT
                return cursor
            elif call_count["n"] == 6:  # UPDATE payment_orders
                return cursor
            elif call_count["n"] == 7:  # _attempt_snapshot
                cursor.fetchone.return_value = {
                    "payment_id": "p1",
                    "order_id": "o1",
                    "attempt_number": 1,
                    "status": "SUCCESS",
                    "amount_minor": 5000,
                    "currency": "INR",
                    "failure_code": None,
                    "debit_id": "d1",
                    "reversal_id": None,
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
                return cursor
            return cursor

        tx.execute.side_effect = side_effect
        result = authorize(db, events, "dev", request, ctx)
        assert result["status"] == "SUCCESS"
        events.append.assert_called_once()
        event_kwargs = events.append.call_args
        assert event_kwargs[1]["event_type"] == "PAYMENT_SUCCESS"

    @patch("services.payments.authorize.random")
    def test_simulated_failure_no_debit(self, mock_random):
        from services.payments.authorize import authorize

        mock_random.random.return_value = 0.05  # < 0.15 → failure
        mock_random.choice.return_value = "SIMULATED_DECLINE"

        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        request = MagicMock()
        request.order_id = "o1"
        request.attempt_number = 1
        request.amount_minor = 5000
        request.currency = "INR"

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            cursor = MagicMock()
            if call_count["n"] == 1:
                return cursor
            elif call_count["n"] == 2:
                cursor.fetchone.return_value = {"quiesced": False}
                return cursor
            elif call_count["n"] == 3:
                cursor.fetchone.return_value = {"payment_id": "p1"}
                return cursor
            elif call_count["n"] == 4:  # UPDATE status FAILED
                return cursor
            elif call_count["n"] == 5:  # UPDATE payment_orders
                return cursor
            elif call_count["n"] == 6:  # _attempt_snapshot
                cursor.fetchone.return_value = {
                    "payment_id": "p1",
                    "order_id": "o1",
                    "attempt_number": 1,
                    "status": "FAILED",
                    "amount_minor": 5000,
                    "currency": "INR",
                    "failure_code": "SIMULATED_DECLINE",
                    "debit_id": None,
                    "reversal_id": None,
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
                return cursor
            return cursor

        tx.execute.side_effect = side_effect
        result = authorize(db, events, "dev", request, ctx)
        assert result["status"] == "FAILED"
        assert result["failure_code"] == "SIMULATED_DECLINE"
        events.append.assert_called_once()
        assert events.append.call_args[1]["event_type"] == "PAYMENT_FAILED"


class TestGetPaymentOrder:
    def test_returns_empty_for_nonexistent(self):
        from services.payments.authorize import get_payment_order

        db, tx = _mock_db()
        tx.execute.return_value.fetchone.return_value = None

        result = get_payment_order(db, "dev", "o1")
        assert result["attempts"] == []
        assert result["quiesced"] is False
        assert result["net_debit_minor"] == 0


class TestReversePayments:
    def test_quiesces_and_reverses_success(self):
        from services.payments.authorize import reverse_payments

        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            cursor = MagicMock()
            if call_count["n"] == 1:  # SELECT quiesced FOR UPDATE
                cursor.fetchone.return_value = {"quiesced": False}
                return cursor
            elif call_count["n"] == 2:  # UPDATE quiesced
                return cursor
            elif call_count["n"] == 3:  # SELECT attempts
                cursor.fetchall.return_value = [
                    {
                        "payment_id": "p1",
                        "order_id": "o1",
                        "attempt_number": 1,
                        "status": "SUCCESS",
                        "amount_minor": 5000,
                        "currency": "INR",
                        "failure_code": None,
                        "debit_id": "d1",
                        "reversal_id": None,
                        "created_at": datetime.now(UTC),
                        "updated_at": datetime.now(UTC),
                    }
                ]
                return cursor
            elif call_count["n"] == 4:  # INSERT reversal ledger entry
                return cursor
            elif call_count["n"] == 5:  # UPDATE attempt REVERSED
                return cursor
            # get_payment_order call
            elif call_count["n"] == 6:
                cursor.fetchone.return_value = {"quiesced": True}
                return cursor
            elif call_count["n"] == 7:
                cursor.fetchall.return_value = [
                    {
                        "payment_id": "p1",
                        "order_id": "o1",
                        "attempt_number": 1,
                        "status": "REVERSED",
                        "amount_minor": 5000,
                        "currency": "INR",
                        "failure_code": None,
                        "debit_id": "d1",
                        "reversal_id": "rev1",
                        "created_at": datetime.now(UTC),
                        "updated_at": datetime.now(UTC),
                    }
                ]
                return cursor
            elif call_count["n"] == 8:
                cursor.fetchone.return_value = {"net": 0}
                return cursor
            return cursor

        tx.execute.side_effect = side_effect
        result = reverse_payments(db, events, "dev", "o1", "compensation", ctx)
        assert result["quiesced"] is True
        events.append.assert_called_once()
        assert events.append.call_args[1]["event_type"] == "PAYMENT_REVERSED"

    def test_creates_quiesced_order_if_none_exists(self):
        from services.payments.authorize import reverse_payments

        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()

        tx.execute.return_value.fetchone.return_value = None
        result = reverse_payments(db, events, "dev", "o1", "compensation", ctx)
        assert result["quiesced"] is True
        assert result["net_debit_minor"] == 0


class TestNetDebit:
    def test_zero_with_no_payments(self):
        from services.payments.authorize import _net_debit

        db, tx = _mock_db()
        result = _net_debit(tx, "dev", [])
        assert result == 0

    def test_calculates_net(self):
        from services.payments.authorize import _net_debit

        db, tx = _mock_db()
        tx.execute.return_value.fetchone.return_value = {"net": 5000}

        result = _net_debit(tx, "dev", ["p1"])
        assert result == 5000


class TestEventPayloads:
    """Verify event payloads contain all required fields for the event models."""

    @patch("services.payments.authorize.random")
    def test_success_event_has_all_fields(self, mock_random):
        from services.payments.authorize import authorize

        mock_random.random.return_value = 0.9  # success
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        request = MagicMock()
        request.order_id = "o1"
        request.attempt_number = 1
        request.amount_minor = 5000
        request.currency = "INR"

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            cursor = MagicMock()
            if call_count["n"] == 2:
                cursor.fetchone.return_value = {"quiesced": False}
            elif call_count["n"] == 3:
                cursor.fetchone.return_value = {"payment_id": "p1"}
            elif call_count["n"] == 7:
                cursor.fetchone.return_value = {
                    "payment_id": "p1",
                    "order_id": "o1",
                    "attempt_number": 1,
                    "status": "SUCCESS",
                    "amount_minor": 5000,
                    "currency": "INR",
                    "failure_code": None,
                    "debit_id": "d1",
                    "reversal_id": None,
                    "created_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            return cursor

        tx.execute.side_effect = side_effect
        authorize(db, events, "dev", request, ctx)

        payload = events.append.call_args[1]["payload"]
        required_fields = [
            "payment_id",
            "order_id",
            "attempt_number",
            "status",
            "amount_minor",
            "currency",
            "attempt_created_at",
            "failure_code",
            "debit_id",
            "reversal_id",
        ]
        for field in required_fields:
            assert field in payload, f"Missing required field: {field}"
