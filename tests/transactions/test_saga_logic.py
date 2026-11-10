"""Unit tests for saga orchestration logic — mocked DB and HTTP calls."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from services.orders.saga import (
    BACKOFF_CAP_SECONDS,
    _backoff,
    _execute_step,
    _internal_headers,
    _retry_step,
    run_pending_sagas,
)
from shared.contracts.common import RequestContext


def _context():
    return RequestContext(
        namespace="dev",
        run_id="test-run",
        user_id="user-1",
        correlation_id="corr-1",
        request_id=str(uuid4()),
        session_id=str(uuid4()),
    )


def _mock_db():
    db = MagicMock()
    tx = MagicMock()
    db.transaction.return_value.__enter__ = MagicMock(return_value=tx)
    db.transaction.return_value.__exit__ = MagicMock(return_value=False)
    tx.execute.return_value.fetchone.return_value = {}
    return db, tx


class TestInternalHeaders:
    def test_includes_required_headers(self):
        ctx = _context()
        headers = _internal_headers(ctx, "token-123")
        assert headers["X-Namespace"] == "dev"
        assert headers["X-User-ID"] == "user-1"
        assert headers["Authorization"] == "Bearer token-123"
        assert headers["X-Session-ID"] == ctx.session_id

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
            db,
            events,
            ctx,
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
                db,
                events,
                ctx,
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
                    db,
                    events,
                    ctx,
                    inventory_url="http://inventory:8004",
                    payments_url="http://payments:8005",
                    internal_token="",
                )
        assert result == 0
        mock_backoff.assert_called_once()


def _saga_job_update(tx):
    return next(c for c in tx.execute.call_args_list if "UPDATE saga_jobs" in c[0][0])


class TestBackoff:
    def test_first_retry_after_100ms(self):
        db, tx = _mock_db()
        before = datetime.now(UTC)
        _backoff(db, {"namespace": "dev", "order_id": "o1", "attempt": 0}, RuntimeError("x"))
        attempt, next_at, last_error = _saga_job_update(tx)[0][1][:3]
        assert attempt == 1
        assert timedelta(milliseconds=90) <= next_at - before <= timedelta(milliseconds=500)
        assert last_error == "x"

    def test_delay_capped_at_two_seconds(self):
        db, tx = _mock_db()
        before = datetime.now(UTC)
        _backoff(db, {"namespace": "dev", "order_id": "o1", "attempt": 30})
        next_at = _saga_job_update(tx)[0][1][1]
        assert next_at - before <= timedelta(seconds=BACKOFF_CAP_SECONDS + 0.5)

    def test_job_is_never_dropped(self):
        db, tx = _mock_db()
        _backoff(db, {"namespace": "dev", "order_id": "o1", "attempt": 1000})
        next_at = _saga_job_update(tx)[0][1][1]
        assert next_at is not None
        assert not any("next_attempt_at = NULL" in c[0][0] for c in tx.execute.call_args_list)

    def test_manual_review_only_after_sixty_seconds_without_progress(self):
        db, tx = _mock_db()
        before = datetime.now(UTC)
        _backoff(db, {"namespace": "dev", "order_id": "o1", "attempt": 0})
        review = next(c for c in tx.execute.call_args_list if "MANUAL_REVIEW" in c[0][0])
        cutoff = review[0][1][3]
        assert "updated_at <= %s" in review[0][0]
        assert abs((before - timedelta(seconds=60)) - cutoff) < timedelta(seconds=1)


class TestExecuteStepReserve:
    @patch("services.orders.saga._HTTP")
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
            "order_id": "o1",
            "total_amount_minor": 5000,
            "reservation_id": None,
            "payment_id": None,
            "failure_code": None,
        }
        tx.execute.return_value.fetchall.return_value = [{"sku": "SKU-001", "quantity": 2}]

        with patch("services.orders.saga._advance") as mock_advance:
            _execute_step(
                db,
                events,
                job,
                ctx,
                inventory_url="http://inventory:8004",
                payments_url="http://payments:8005",
                internal_token="tok",
            )
        mock_advance.assert_called_once()
        args = mock_advance.call_args
        assert args[0][4] == "RESERVING"
        assert args[0][5] == "AUTHORIZE_PAYMENT"

    @patch("services.orders.saga._HTTP")
    def test_reserve_conflict_cancels(self, mock_httpx):
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        job = {"namespace": "dev", "order_id": "o1", "planned_step": "RESERVE", "attempt": 0}

        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_httpx.post.return_value = mock_response

        tx.execute.return_value.fetchone.return_value = {
            "order_id": "o1",
            "total_amount_minor": 5000,
        }
        tx.execute.return_value.fetchall.return_value = [{"sku": "SKU-001", "quantity": 1}]

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
        assert args[0][4] == "COMPENSATING"
        assert args[0][5] == "CANCEL"


class TestExecuteStepAuthorizePayment:
    @patch("services.orders.saga._HTTP")
    def test_payment_success_advances_to_commit(self, mock_httpx):
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        job = {
            "namespace": "dev",
            "order_id": "o1",
            "planned_step": "AUTHORIZE_PAYMENT",
            "attempt": 0,
        }

        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.json.return_value = {"attempts": []}

        post_resp = MagicMock()
        post_resp.status_code = 202
        post_resp.json.return_value = {"payment_id": "p1", "status": "SUCCESS"}

        hold = MagicMock(status_code=200)
        hold.json.return_value = {
            "state": "ACTIVE",
            "expires_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
        }
        mock_httpx.get.side_effect = [get_resp, hold]
        mock_httpx.post.return_value = post_resp

        tx.execute.return_value.fetchone.return_value = {
            "order_id": "o1",
            "total_amount_minor": 5000,
            "reservation_id": "r1",
            "payment_id": None,
            "failure_code": None,
        }

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
        assert args[0][4] == "PAYMENT_PENDING"
        assert args[0][5] == "COMMIT_STOCK"

    @patch("services.orders.saga._HTTP")
    def test_payment_fail_attempt1_retries(self, mock_httpx):
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        job = {
            "namespace": "dev",
            "order_id": "o1",
            "planned_step": "AUTHORIZE_PAYMENT",
            "attempt": 0,
        }

        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.json.return_value = {"attempts": []}

        post_resp = MagicMock()
        post_resp.status_code = 202
        post_resp.json.return_value = {
            "payment_id": "p1",
            "status": "FAILED",
            "failure_code": "RETRYABLE_PROVIDER_FAILURE",
        }

        hold = MagicMock(status_code=200)
        hold.json.return_value = {
            "state": "ACTIVE",
            "expires_at": (datetime.now(UTC) + timedelta(seconds=30)).isoformat(),
        }
        mock_httpx.get.side_effect = [get_resp, hold]
        mock_httpx.post.return_value = post_resp

        tx.execute.return_value.fetchone.return_value = {
            "order_id": "o1",
            "total_amount_minor": 5000,
        }

        with patch("services.orders.saga._retry_step") as mock_retry:
            _execute_step(
                db,
                events,
                job,
                ctx,
                inventory_url="http://inventory:8004",
                payments_url="http://payments:8005",
                internal_token="",
            )
        mock_retry.assert_called_once()

    @patch("services.orders.saga._HTTP")
    def test_max_attempts_exceeded_compensates(self, mock_httpx):
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        job = {
            "namespace": "dev",
            "order_id": "o1",
            "planned_step": "AUTHORIZE_PAYMENT",
            "attempt": 0,
        }

        get_resp = MagicMock()
        get_resp.status_code = 200
        get_resp.json.return_value = {"attempts": [{"id": 1}, {"id": 2}]}

        mock_httpx.get.return_value = get_resp

        tx.execute.return_value.fetchone.return_value = {
            "order_id": "o1",
            "total_amount_minor": 5000,
        }

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
        assert args[0][4] == "COMPENSATING"
        assert args[0][5] == "COMPENSATE_RELEASE"


class TestExecuteStepCommitStock:
    @patch("services.orders.saga._HTTP")
    def test_commit_success_advances_to_confirm(self, mock_httpx):
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        job = {"namespace": "dev", "order_id": "o1", "planned_step": "COMMIT_STOCK", "attempt": 0}

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_httpx.post.return_value = mock_response

        tx.execute.return_value.fetchone.return_value = {
            "order_id": "o1",
            "reservation_id": "r1",
        }

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

    @patch("services.orders.saga._HTTP")
    def test_commit_conflict_compensates(self, mock_httpx):
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        job = {"namespace": "dev", "order_id": "o1", "planned_step": "COMMIT_STOCK", "attempt": 0}

        mock_response = MagicMock()
        mock_response.status_code = 409
        mock_httpx.post.return_value = mock_response

        tx.execute.return_value.fetchone.return_value = {
            "order_id": "o1",
            "reservation_id": "r1",
        }

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
        assert args[0][4] == "COMPENSATING"


class TestExecuteStepConfirm:
    def test_confirm_calls_finalize_confirmed(self):
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        job = {"namespace": "dev", "order_id": "o1", "planned_step": "CONFIRM", "attempt": 0}

        with patch("services.orders.saga._finalize") as mock_finalize:
            _execute_step(
                db,
                events,
                job,
                ctx,
                inventory_url="http://inventory:8004",
                payments_url="http://payments:8005",
                internal_token="",
            )
        mock_finalize.assert_called_once()
        assert mock_finalize.call_args[0][4] == "CONFIRMED"


def _run_step(step, db, *, ctx=None, namespace="dev"):
    _execute_step(
        db,
        MagicMock(),
        {"namespace": namespace, "order_id": "o1", "planned_step": step, "attempt": 0},
        ctx or _context(),
        inventory_url="http://inventory:8004",
        payments_url="http://payments:8005",
        internal_token="",
    )


class TestCompensationSteps:
    """Common spec §9.3: release inventory first; reverse payment only after a proven release."""

    def _db(self):
        db, tx = _mock_db()
        tx.execute.return_value.fetchone.return_value = {
            "order_id": "o1",
            "failure_code": "PAYMENT_FAILED",
            "payment_id": None,
        }
        return db

    @patch("services.orders.saga._HTTP")
    def test_release_first_then_reverse_payment(self, http):
        http.post.return_value = MagicMock(status_code=200)
        with patch("services.orders.saga._update_saga_step") as update:
            _run_step("COMPENSATE_RELEASE", self._db())
        assert http.post.call_args[0][0].endswith("/reservations/by-order/o1/release")
        assert update.call_args[0][3] == "COMPENSATE_PAYMENT"

    @patch("services.orders.saga._HTTP")
    def test_reverse_payment_then_cancel(self, http):
        http.post.return_value = MagicMock(status_code=200)
        with patch("services.orders.saga._update_saga_step") as update:
            _run_step("COMPENSATE_PAYMENT", self._db())
        assert http.post.call_args[0][0].endswith("/payments/by-order/o1/reverse")
        assert update.call_args[0][3] == "CANCEL"

    @pytest.mark.parametrize("step", ["COMPENSATE_RELEASE", "COMPENSATE_PAYMENT"])
    @patch("services.orders.saga._HTTP")
    def test_unknown_participant_outcome_never_advances(self, http, step):
        http.post.return_value = MagicMock(status_code=503)
        with patch("services.orders.saga._update_saga_step") as update:
            with pytest.raises(RuntimeError):
                _run_step(step, self._db())
        update.assert_not_called()

    @patch("services.orders.saga._HTTP")
    def test_release_uses_default_reason_when_failure_code_null(self, http):
        db, tx = _mock_db()
        tx.execute.return_value.fetchone.return_value = {"failure_code": None, "payment_id": None}
        http.post.return_value = MagicMock(status_code=200)
        with patch("services.orders.saga._update_saga_step"):
            _run_step("COMPENSATE_RELEASE", db)
        assert http.post.call_args[1]["json"] == {"reason": "saga_compensation"}

    def test_cancel_calls_finalize_cancelled(self):
        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()
        job = {"namespace": "dev", "order_id": "o1", "planned_step": "CANCEL", "attempt": 0}

        with patch("services.orders.saga._finalize") as mock_finalize:
            _execute_step(
                db,
                events,
                job,
                ctx,
                inventory_url="http://inventory:8004",
                payments_url="http://payments:8005",
                internal_token="",
            )
        mock_finalize.assert_called_once()
        assert mock_finalize.call_args[0][4] == "CANCELLED"


class TestPaymentRecovery:
    """Common spec §9.2: a lost response never produces a second attempt or a double charge."""

    @patch("services.orders.saga._HTTP")
    def test_existing_success_is_reused_without_new_attempt(self, http):
        db, tx = _mock_db()
        tx.execute.return_value.fetchone.return_value = {"total_amount_minor": 5000}
        http.get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"attempts": [{"payment_id": "p1", "status": "SUCCESS"}]},
        )
        with patch("services.orders.saga._advance") as advance:
            _run_step("AUTHORIZE_PAYMENT", db)
        http.post.assert_not_called()
        assert advance.call_args[0][5] == "COMMIT_STOCK"
        assert advance.call_args[1]["payment_id"] == "p1"

    @patch("services.orders.saga._HTTP")
    def test_failed_lookup_backs_off_instead_of_guessing_attempt(self, http):
        db, tx = _mock_db()
        tx.execute.return_value.fetchone.return_value = {"total_amount_minor": 5000}
        http.get.return_value = MagicMock(status_code=503)
        with pytest.raises(RuntimeError):
            _run_step("AUTHORIZE_PAYMENT", db)
        http.post.assert_not_called()

    @patch("services.orders.saga._HTTP")
    def test_quiesced_payment_order_compensates(self, http):
        db, tx = _mock_db()
        tx.execute.return_value.fetchone.return_value = {"total_amount_minor": 5000}
        http.get.return_value = MagicMock(
            status_code=200, json=lambda: {"attempts": [], "quiesced": True}
        )
        with patch("services.orders.saga._advance") as advance:
            _run_step("AUTHORIZE_PAYMENT", db)
        http.post.assert_not_called()
        assert advance.call_args[0][5] == "COMPENSATE_RELEASE"

    @pytest.mark.parametrize(
        "status,code,expired",
        [
            ("PENDING", None, False),
            ("PENDING", None, True),
            ("FAILED", "DECLINED", False),
            ("FAILED", "INVALID_INPUT", False),
            ("FAILED", "RETRYABLE_PROVIDER_FAILURE", False),
            ("FAILED", "RETRYABLE_PROVIDER_FAILURE", True),
        ],
    )
    @patch("services.orders.saga._HTTP")
    def test_retry_policy_and_expiry_are_checked_before_a_new_attempt(
        self, http, status, code, expired
    ):
        db, tx = _mock_db()
        tx.execute.return_value.fetchone.return_value = {
            "total_amount_minor": 5000,
            "status": "PAYMENT_PENDING",
        }
        payment = {
            "attempts": [
                {"payment_id": "p1", "attempt_number": 1, "status": status, "failure_code": code}
            ]
        }
        hold = {
            "state": "ACTIVE",
            "expires_at": (
                datetime.now(UTC) + timedelta(seconds=-1 if expired else 30)
            ).isoformat(),
        }
        http.get.side_effect = lambda url, **kwargs: MagicMock(
            status_code=200, json=lambda: payment if "/payments/" in url else hold
        )
        http.post.return_value = MagicMock(
            status_code=202, json=lambda: {"payment_id": "p2", "status": "PENDING"}
        )
        with (
            patch("services.orders.saga._advance") as advance,
            patch("services.orders.saga._retry_step") as retry,
        ):
            _run_step("AUTHORIZE_PAYMENT", db)
        should_authorize = code == "RETRYABLE_PROVIDER_FAILURE" and not expired
        assert http.post.call_count == int(should_authorize)
        if should_authorize:
            assert http.post.call_args.kwargs["json"]["attempt_number"] == 2
            assert http.post.call_args.kwargs["headers"]["Idempotency-Key"] == "o1:authorize:2:v1"
        if status == "PENDING" and not expired or should_authorize:
            retry.assert_called_once()
        else:
            retry.assert_not_called()
            assert advance.call_args.args[5] == "COMPENSATE_RELEASE"
            assert advance.call_args.kwargs["failure_code"] == (
                "RESERVATION_EXPIRED" if expired else code
            )


class TestJobScoping:
    @patch("services.orders.saga._HTTP")
    def test_internal_calls_carry_the_jobs_namespace(self, http):
        from shared.contracts.common import RequestContext

        worker = RequestContext(
            namespace="dev",
            run_id="saga-worker",
            user_id="system",
            correlation_id=str(uuid4()),
            request_id=str(uuid4()),
            session_id=None,
        )
        db, tx = _mock_db()
        tx.execute.return_value.fetchone.return_value = {"order_id": "o1"}
        tx.execute.return_value.fetchall.return_value = [{"sku": "SKU-1", "quantity": 1}]
        http.post.return_value = MagicMock(status_code=201, json=lambda: {"reservation_id": "r1"})
        with patch("services.orders.saga._advance"):
            _run_step("RESERVE", db, ctx=worker, namespace="bench-run-7")
        assert http.post.call_args[1]["headers"]["X-Namespace"] == "bench-run-7"

    @patch("services.orders.saga._HTTP")
    def test_order_id_from_database_is_sent_as_string(self, http):
        from uuid import UUID

        db, tx = _mock_db()
        tx.execute.return_value.fetchone.return_value = {"order_id": "o1"}
        tx.execute.return_value.fetchall.return_value = [{"sku": "SKU-1", "quantity": 1}]
        http.post.return_value = MagicMock(status_code=201, json=lambda: {"reservation_id": "r1"})
        order_id = UUID("12345678-1234-5678-1234-567812345678")
        with patch("services.orders.saga._advance"):
            _execute_step(
                db,
                MagicMock(),
                {"namespace": "dev", "order_id": order_id, "planned_step": "RESERVE", "attempt": 0},
                _context(),
                inventory_url="http://inventory:8004",
                payments_url="http://payments:8005",
                internal_token="",
            )
        assert http.post.call_args[1]["json"]["order_id"] == str(order_id)

    def test_claim_leases_jobs_in_one_statement(self):
        db, tx = _mock_db()
        tx.execute.return_value.fetchall.return_value = []
        run_pending_sagas(
            db,
            MagicMock(),
            _context(),
            inventory_url="http://inventory:8004",
            payments_url="http://payments:8005",
            internal_token="",
        )
        sql, params = tx.execute.call_args[0]
        assert "UPDATE saga_jobs" in sql and "FOR UPDATE SKIP LOCKED" in sql
        lease_until, claimed_at = params[0], params[1]
        assert lease_until - claimed_at == timedelta(seconds=10)


class TestRetryStep:
    def test_retry_schedules_future_attempt(self):
        db, tx = _mock_db()
        now = datetime.now(UTC)

        _retry_step(db, "dev", "o1", "AUTHORIZE_PAYMENT", now)
        sql = tx.execute.call_args[0][0]
        assert "attempt = attempt + 1" in sql
