"""Tests for A05-A07 saga enhancements: operation keys, fault barriers, finish-forward."""

from unittest.mock import MagicMock, patch

import pytest

from services.orders.saga import (
    FaultBarrier,
    _operation_key,
    _record_operation_key,
)


class TestOperationKey:
    def test_format(self):
        key = _operation_key("order-123", "reserve")
        assert key == "order-123:reserve:v1"

    def test_versioned(self):
        key = _operation_key("order-123", "authorize:1", version=1)
        assert key == "order-123:authorize:1:v1"

    def test_different_orders_different_keys(self):
        k1 = _operation_key("order-1", "reserve")
        k2 = _operation_key("order-2", "reserve")
        assert k1 != k2


class TestRecordOperationKey:
    def test_updates_saga_job(self):
        db = MagicMock()
        tx = MagicMock()
        db.transaction.return_value.__enter__ = MagicMock(return_value=tx)
        db.transaction.return_value.__exit__ = MagicMock(return_value=False)

        _record_operation_key(db, "dev", "o1", "o1:reserve:v1", "RESERVE")
        tx.execute.assert_called_once()
        sql = tx.execute.call_args[0][0]
        assert "operation_key" in sql
        assert "UPDATE saga_jobs" in sql


class TestFaultBarrier:
    def test_noop_outside_benchmark_mode(self):
        db = MagicMock()
        with patch("services.orders.saga._BENCHMARK_MODE", False):
            FaultBarrier.check(db, "dev", "saga.before_reserve")
        db.transaction.assert_not_called()

    @patch("services.orders.saga._BENCHMARK_MODE", True)
    def test_crash_raises(self):
        db = MagicMock()
        tx = MagicMock()
        db.transaction.return_value.__enter__ = MagicMock(return_value=tx)
        db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        tx.execute.return_value.fetchone.return_value = {"action": "CRASH", "delay_ms": 0}

        with pytest.raises(RuntimeError, match="Fault barrier triggered"):
            FaultBarrier.check(db, "dev", "saga.before_reserve")

    @patch("services.orders.saga._BENCHMARK_MODE", True)
    def test_no_barrier_does_nothing(self):
        db = MagicMock()
        tx = MagicMock()
        db.transaction.return_value.__enter__ = MagicMock(return_value=tx)
        db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        tx.execute.return_value.fetchone.return_value = None

        FaultBarrier.check(db, "dev", "saga.nonexistent")

    @patch("services.orders.saga._BENCHMARK_MODE", True)
    @patch("services.orders.saga.time")
    def test_delay_sleeps(self, mock_time):
        db = MagicMock()
        tx = MagicMock()
        db.transaction.return_value.__enter__ = MagicMock(return_value=tx)
        db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        tx.execute.return_value.fetchone.return_value = {"action": "DELAY", "delay_ms": 500}

        FaultBarrier.check(db, "dev", "saga.before_commit")
        mock_time.sleep.assert_called_once_with(0.5)


class TestFinishForward:
    """Test that COMPENSATE_RELEASE detects COMMITTED and finishes forward."""

    @patch("services.orders.saga._HTTP")
    def test_release_committed_finishes_forward(self, mock_httpx):
        from services.orders.saga import _execute_step

        db = MagicMock()
        tx = MagicMock()
        db.transaction.return_value.__enter__ = MagicMock(return_value=tx)
        db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        events = MagicMock()
        ctx = MagicMock()
        ctx.namespace = "dev"
        ctx.run_id = "r"
        ctx.user_id = "u"
        ctx.correlation_id = "c"
        ctx.request_id = "r"
        ctx.session_id = "s"

        job = {
            "namespace": "dev",
            "order_id": "o1",
            "planned_step": "COMPENSATE_RELEASE",
            "attempt": 0,
        }

        tx.execute.return_value.fetchone.return_value = {
            "order_id": "o1",
            "failure_code": "COMMIT_FAILED",
            "payment_id": "p1",
        }

        resp = MagicMock()
        resp.status_code = 409
        resp.headers = {"content-type": "application/json"}
        resp.json.return_value = {
            "error": {"code": "ILLEGAL_STATE", "message": "Cannot release a committed reservation."}
        }
        mock_httpx.post.return_value = resp

        with patch("services.orders.saga._advance") as mock_advance:
            _execute_step(
                db,
                events,
                job,
                ctx,
                inventory_url="http://inventory:8004",
                payments_url="http://payments:8005",
                internal_token="",
            )
        args = mock_advance.call_args
        assert args[0][4] == "COMMITTING_STOCK"
        assert args[0][5] == "CONFIRM"
        mock_httpx.post.assert_called_once()
        assert mock_httpx.post.call_args[0][0].endswith("/release")

    @patch("services.orders.saga._HTTP")
    def test_committed_without_recorded_payment_is_not_confirmed(self, mock_httpx):
        from services.orders.saga import _execute_step

        db = MagicMock()
        tx = MagicMock()
        db.transaction.return_value.__enter__ = MagicMock(return_value=tx)
        db.transaction.return_value.__exit__ = MagicMock(return_value=False)
        tx.execute.return_value.fetchone.return_value = {"failure_code": "X", "payment_id": None}
        resp = MagicMock(status_code=409)
        resp.json.return_value = {"error": {"message": "Cannot release a committed reservation."}}
        mock_httpx.post.return_value = resp
        job = {
            "namespace": "dev",
            "order_id": "o1",
            "planned_step": "COMPENSATE_RELEASE",
            "attempt": 0,
        }

        with patch("services.orders.saga._advance") as mock_advance:
            with pytest.raises(RuntimeError, match="without a recorded payment"):
                _execute_step(
                    db,
                    MagicMock(),
                    job,
                    MagicMock(),
                    inventory_url="http://inventory:8004",
                    payments_url="http://payments:8005",
                    internal_token="",
                )
        mock_advance.assert_not_called()
