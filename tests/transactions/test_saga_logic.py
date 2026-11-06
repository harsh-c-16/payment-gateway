"""Unit tests for saga orchestration logic — mocked DB and HTTP calls."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch, call

import pytest

from services.orders.saga import (
    MAX_SAGA_ATTEMPTS,
    BACKOFF_BASE_SECONDS,
    _advance,
    _backoff,
    _execute_step,
    _finalize,
    _internal_headers,
    _retry_step,
    run_pending_sagas,
)


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


class TestInternalHeaders:
    def test_includes_required_headers(self):
        ctx = _context()
        headers = _internal_headers(ctx, "token-123")
        assert headers["X-Namespace"] == "dev"
        assert headers["X-User-ID"] == "user-1"
        assert headers["Authorization"] == "Bearer token-123"
        assert headers["X-Session-ID"] == "sess-1"

    def test_omits_session_if_none(self):
        ctx = _context()
        ctx.session_id = None
        headers = _internal_headers(ctx, "")
        assert "X-Session-ID" not in headers
        assert "Authorization" not in headers


class TestRunPendingSagas:
    def test_returns_zero_when_no_jobs(self):
        db, tx = _mock_db()
        tx.execute.return_value.fetchall.return_value = []
        events = MagicMock()
        ctx = _context()

        result = run_pending_sagas(
            db, events, ctx,
            inventory_url="http://inventory:8004",
            payments_url="http://payments:8005",
            internal_token="",
        )
        assert result == 0

    def test_processes_jobs_and_counts(self):
        db, tx = _mock_db()
        jobs = [
            {"namespace": "dev", "order_id": "o1", "planned_step": "CONFIRM", "attempt": 0},
        ]
        tx.execute.return_value.fetchall.return_value = jobs
        events = MagicMock()
        ctx = _context()

        with patch("services.orders.saga._execute_step") as mock_exec:
            result = run_pending_sagas(
                db, events, ctx,
                inventory_url="http://inventory:8004",
                payments_url="http://payments:8005",
                internal_token="",
            )
        assert result == 1
        mock_exec.assert_called_once()

    def test_backoff_on_exception(self):
        db, tx = _mock_db()
        jobs = [
            {"namespace": "dev", "order_id": "o1", "planned_step": "RESERVE", "attempt": 0},
        ]
        tx.execute.return_value.fetchall.return_value = jobs
        events = MagicMock()
        ctx = _context()

        with patch("services.orders.saga._execute_step", side_effect=RuntimeError("boom")):
            with patch("services.orders.saga._backoff") as mock_backoff:
                result = run_pending_sagas(
                    db, events, ctx,
                    inventory_url="http://inventory:8004",
                    payments_url="http://payments:8005",
                    internal_token="",
                )
        assert result == 0
        mock_backoff.assert_called_once()


class TestBackoff:
    def test_increments_attempt(self):
        db, tx = _mock_db()
        job = {"namespace": "dev", "order_id": "o1", "attempt": 0}

        _backoff(db, job)
        sql = tx.execute.call_args[0][0]
        assert "UPDATE saga_jobs" in sql

    def test_manual_review_at_max_attempts(self):
        db, tx = _mock_db()
        job = {"namespace": "dev", "order_id": "o1", "attempt": MAX_SAGA_ATTEMPTS - 1}

        _backoff(db, job)
        calls = tx.execute.call_args_list
        found_manual_review = any("MANUAL_REVIEW" in str(c) for c in calls)
        assert found_manual_review, "Expected MANUAL_REVIEW status update"


class TestExecuteStepReserve:
    @patch("services.orders.saga.httpx")
    def test_reserve_success_advances_to_authorize(self, mock_httpx):
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        job = {"namespace": "dev", "order_id": "o1", "planned_step": "RESERVE", "attempt": 0}

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"reservation_id": "r1"}
        mock_httpx.post.return_value = mock_response

        tx.execute.return_value.fetchone.return_value = {
            "order_id": "o1", "total_amount_minor": 5000,
            "reservation_id": None, "payment_id": None, "failure_code": None,
        }
        tx.execute.return_value.fetchall.return_value = [
            {"sku": "SKU-001", "quantity": 2}
        ]

        with patch("services.orders.saga._advance") as mock_advance:
            _execute_step(
                db, events, job, ctx,
                inventory_url="http://inventory:8004",
                payments_url="http://payments:8005",
                internal_token="tok",
            )
        mock_advance.assert_called_once()
        args = mock_advance.call_args
        assert args[0][4] == "RESERVING"
        assert args[0][5] == "AUTHORIZE_PAYMENT"

    @patch("services.orders.saga.httpx")
    def test_reserve_conflict_cancels(self, mock_httpx):
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        job = {"namespace": "dev", "order_id": "o1", "planned_step": "RESERVE", "attempt": 0}

        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_httpx.post.return_value = mock_response

        tx.execute.return_value.fetchone.return_value = {
            "order_id": "o1", "total_amount_minor": 5000,
        }
        tx.execute.return_value.fetchall.return_value = [
            {"sku": "SKU-001", "quantity": 1}
        ]

        with patch("services.orders.saga._advance") as mock_advance:
            _execute_step(
                db, events, job, ctx,
                inventory_url="http://inventory:8004",
                payments_url="http://payments:8005",
                internal_token="",
            )
        args = mock_advance.call_args
        assert args[0][4] == "COMPENSATING"
        assert args[0][5] == "CANCEL"


class TestExecuteStepAuthorizePayment:
    @patch("services.orders.saga.httpx")
    def test_payment_success_advances_to_commit(self, mock_httpx):
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        job = {"namespace": "dev", "order_id": "o1", "planned_step": "AUTHORIZE_PAYMENT", "attempt": 0}

        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.json.return_value = {"attempts": []}

        post_resp = MagicMock()
        post_resp.status_code = 202
        post_resp.json.return_value = {"payment_id": "p1", "status": "SUCCESS"}

        mock_httpx.get.return_value = get_resp
        mock_httpx.post.return_value = post_resp

        tx.execute.return_value.fetchone.return_value = {
            "order_id": "o1", "total_amount_minor": 5000,
            "reservation_id": "r1", "payment_id": None, "failure_code": None,
        }

        with patch("services.orders.saga._advance") as mock_advance:
            _execute_step(
                db, events, job, ctx,
                inventory_url="http://inventory:8004",
                payments_url="http://payments:8005",
                internal_token="",
            )
        args = mock_advance.call_args
        assert args[0][4] == "PAYMENT_PENDING"
        assert args[0][5] == "COMMIT_STOCK"

    @patch("services.orders.saga.httpx")
    def test_payment_fail_attempt1_retries(self, mock_httpx):
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        job = {"namespace": "dev", "order_id": "o1", "planned_step": "AUTHORIZE_PAYMENT", "attempt": 0}

        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.json.return_value = {"attempts": []}

        post_resp = MagicMock()
        post_resp.status_code = 202
        post_resp.json.return_value = {"payment_id": "p1", "status": "FAILED"}

        mock_httpx.get.return_value = get_resp
        mock_httpx.post.return_value = post_resp

        tx.execute.return_value.fetchone.return_value = {
            "order_id": "o1", "total_amount_minor": 5000,
        }

        with patch("services.orders.saga._retry_step") as mock_retry:
            _execute_step(
                db, events, job, ctx,
                inventory_url="http://inventory:8004",
                payments_url="http://payments:8005",
                internal_token="",
            )
        mock_retry.assert_called_once()

    @patch("services.orders.saga.httpx")
    def test_max_attempts_exceeded_compensates(self, mock_httpx):
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        job = {"namespace": "dev", "order_id": "o1", "planned_step": "AUTHORIZE_PAYMENT", "attempt": 0}

        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.json.return_value = {"attempts": [{"id": 1}, {"id": 2}]}

        mock_httpx.get.return_value = get_resp

        tx.execute.return_value.fetchone.return_value = {
            "order_id": "o1", "total_amount_minor": 5000,
        }

        with patch("services.orders.saga._advance") as mock_advance:
            _execute_step(
                db, events, job, ctx,
                inventory_url="http://inventory:8004",
                payments_url="http://payments:8005",
                internal_token="",
            )
        args = mock_advance.call_args
        assert args[0][4] == "COMPENSATING"
        assert args[0][5] == "COMPENSATE_PAYMENT"


class TestExecuteStepCommitStock:
    @patch("services.orders.saga.httpx")
    def test_commit_success_advances_to_confirm(self, mock_httpx):
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        job = {"namespace": "dev", "order_id": "o1", "planned_step": "COMMIT_STOCK", "attempt": 0}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx.post.return_value = mock_response

        tx.execute.return_value.fetchone.return_value = {
            "order_id": "o1", "reservation_id": "r1",
        }

        with patch("services.orders.saga._advance") as mock_advance:
            _execute_step(
                db, events, job, ctx,
                inventory_url="http://inventory:8004",
                payments_url="http://payments:8005",
                internal_token="",
            )
        args = mock_advance.call_args
        assert args[0][4] == "COMMITTING_STOCK"
        assert args[0][5] == "CONFIRM"

    @patch("services.orders.saga.httpx")
    def test_commit_conflict_compensates(self, mock_httpx):
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        job = {"namespace": "dev", "order_id": "o1", "planned_step": "COMMIT_STOCK", "attempt": 0}

        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_httpx.post.return_value = mock_response

        tx.execute.return_value.fetchone.return_value = {
            "order_id": "o1", "reservation_id": "r1",
        }

        with patch("services.orders.saga._advance") as mock_advance:
            _execute_step(
                db, events, job, ctx,
                inventory_url="http://inventory:8004",
                payments_url="http://payments:8005",
                internal_token="",
            )
        args = mock_advance.call_args
        assert args[0][4] == "COMPENSATING"


class TestExecuteStepConfirm:
    def test_confirm_calls_finalize_confirmed(self):
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        job = {"namespace": "dev", "order_id": "o1", "planned_step": "CONFIRM", "attempt": 0}

        with patch("services.orders.saga._finalize") as mock_finalize:
            _execute_step(
                db, events, job, ctx,
                inventory_url="http://inventory:8004",
                payments_url="http://payments:8005",
                internal_token="",
            )
        mock_finalize.assert_called_once()
        assert mock_finalize.call_args[0][4] == "CONFIRMED"


class TestCompensationSteps:
    @patch("services.orders.saga.httpx")
    def test_compensate_payment_then_release(self, mock_httpx):
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        job = {"namespace": "dev", "order_id": "o1", "planned_step": "COMPENSATE_PAYMENT", "attempt": 0}

        mock_httpx.post.return_value = MagicMock(status_code=200)
        tx.execute.return_value.fetchone.return_value = {
            "order_id": "o1", "failure_code": "PAYMENT_FAILED",
        }

        with patch("services.orders.saga._update_saga_step") as mock_update:
            _execute_step(
                db, events, job, ctx,
                inventory_url="http://inventory:8004",
                payments_url="http://payments:8005",
                internal_token="",
            )
        args = mock_update.call_args
        assert args[0][2] == "o1"
        assert args[0][3] == "COMPENSATE_RELEASE"

    @patch("services.orders.saga.httpx")
    def test_compensate_release_then_cancel(self, mock_httpx):
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        job = {"namespace": "dev", "order_id": "o1", "planned_step": "COMPENSATE_RELEASE", "attempt": 0}

        mock_httpx.post.return_value = MagicMock(status_code=200)
        tx.execute.return_value.fetchone.return_value = {
            "order_id": "o1", "failure_code": "PAYMENT_FAILED",
        }

        with patch("services.orders.saga._update_saga_step") as mock_update:
            _execute_step(
                db, events, job, ctx,
                inventory_url="http://inventory:8004",
                payments_url="http://payments:8005",
                internal_token="",
            )
        args = mock_update.call_args
        assert args[0][3] == "CANCEL"

    def test_cancel_calls_finalize_cancelled(self):
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        job = {"namespace": "dev", "order_id": "o1", "planned_step": "CANCEL", "attempt": 0}

        with patch("services.orders.saga._finalize") as mock_finalize:
            _execute_step(
                db, events, job, ctx,
                inventory_url="http://inventory:8004",
                payments_url="http://payments:8005",
                internal_token="",
            )
        mock_finalize.assert_called_once()
        assert mock_finalize.call_args[0][4] == "CANCELLED"


class TestRetryStep:
    def test_retry_schedules_future_attempt(self):
        db, tx = _mock_db()
        now = datetime.now(UTC)

        _retry_step(db, "dev", "o1", "AUTHORIZE_PAYMENT", now)
        sql = tx.execute.call_args[0][0]
        assert "attempt = attempt + 1" in sql
