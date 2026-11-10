"""Unit tests for payment authorization logic — mocked DB."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

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
    @pytest.mark.parametrize("roll,expected_failure", [(0.9, None), (0.0, "DECLINED")])
    def test_authorize_persists_pending_plan_without_debit_or_event(self, roll, expected_failure):
        from services.payments.authorize import authorize
        from tests.transactions.test_saga_logic import _context

        db, tx = _mock_db()
        events = MagicMock()
        tx.execute.return_value.fetchall.return_value = []
        pending = {"payment_id": "p1", "status": "PENDING"}
        tx.execute.return_value.fetchone.side_effect = [{"quiesced": False}, pending]
        request = MagicMock(order_id="o1", attempt_number=1, amount_minor=5000, currency="INR")
        with patch("services.payments.authorize.random.random", return_value=roll):
            assert authorize(db, events, "dev", request, _context()) == pending
        statements = [call.args[0] for call in tx.execute.call_args_list]
        assert not any("INSERT INTO ledger_entries" in sql for sql in statements)
        insert = next(
            call
            for call in tx.execute.call_args_list
            if "INSERT INTO payment_attempts" in call.args[0]
        )
        assert insert.args[1][6] == expected_failure
        assert "interval '100 milliseconds'" in insert.args[0]
        events.append.assert_not_called()

    def test_rejects_quiesced_order(self):
        from services.payments.authorize import authorize

        db, tx = _mock_db()
        tx.execute.return_value.fetchall.return_value = []
        tx.execute.return_value.fetchone.return_value = {"quiesced": True}
        with pytest.raises(ServiceError, match="quiesced"):
            authorize(db, MagicMock(), "dev", MagicMock(), _context())

    def test_same_attempt_reads_existing_without_new_plan(self):
        from services.payments.authorize import authorize

        db, tx = _mock_db()
        tx.execute.return_value.fetchall.return_value = [
            {"payment_id": "p1", "attempt_number": 1, "amount_minor": 5000, "currency": "INR"}
        ]
        tx.execute.return_value.fetchone.side_effect = [{"quiesced": True}, {"status": "CANCELLED"}]
        request = MagicMock(order_id="o1", attempt_number=1, amount_minor=5000, currency="INR")
        assert authorize(db, MagicMock(), "dev", request, _context())["status"] == "CANCELLED"
        assert not any(
            "INSERT INTO payment_attempts" in c.args[0] for c in tx.execute.call_args_list
        )


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
            if call_count["n"] == 2:  # SELECT quiesced FOR UPDATE after creating guard
                cursor.fetchone.return_value = {"quiesced": False}
                return cursor
            elif call_count["n"] == 3:  # Database clock after locking guard
                cursor.fetchone.return_value = {"now": datetime.now(UTC)}
                return cursor
            elif call_count["n"] == 4:  # UPDATE quiesced
                return cursor
            elif call_count["n"] == 5:  # SELECT attempts
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
            elif call_count["n"] == 6:  # INSERT reversal ledger entry
                return cursor
            elif call_count["n"] == 7:  # UPDATE attempt REVERSED
                return cursor
            # get_payment_order call
            elif call_count["n"] == 8:
                cursor.fetchone.return_value = {"quiesced": True}
                return cursor
            elif call_count["n"] == 9:
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
            elif call_count["n"] == 10:
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

        tx.execute.return_value.fetchone.side_effect = [
            {"quiesced": False},
            {"now": datetime.now(UTC)},
            {"quiesced": True},
        ]
        tx.execute.return_value.fetchall.return_value = []
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
    @pytest.mark.parametrize(
        "failure,status,event",
        [(None, "SUCCESS", "PAYMENT_SUCCESS"), ("DECLINED", "FAILED", "PAYMENT_FAILED")],
    )
    def test_worker_event_contains_original_context_and_all_fields(self, failure, status, event):
        from datetime import timedelta

        from services.payments.authorize import _complete_payment
        from shared.contracts.events import PaymentEvent
        from tests.transactions.test_saga_logic import _context

        db, tx = _mock_db()
        events = MagicMock()
        now = datetime.now(UTC)
        ctx = _context()
        attempt = {
            "status": "PENDING",
            "completion_due_at": now - timedelta(seconds=1),
            "planned_failure_code": failure,
            "origin_context": ctx.model_dump(mode="json"),
            "attempt_number": 1,
            "amount_minor": 5000,
            "currency": "INR",
            "created_at": now,
        }
        tx.execute.return_value.fetchone.side_effect = [{"quiesced": False}, attempt, {"now": now}]
        assert (
            _complete_payment(
                db,
                events,
                {
                    "namespace": "dev",
                    "order_id": str(uuid4()),
                    "payment_id": str(uuid4()),
                },
            )
            == 1
        )
        kwargs = events.append.call_args.kwargs
        PaymentEvent.model_validate(kwargs["payload"])
        assert kwargs["payload"]["status"] == status
        assert kwargs["event_type"] == event
        assert kwargs["context"] == ctx
