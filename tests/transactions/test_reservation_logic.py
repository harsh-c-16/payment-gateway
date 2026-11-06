"""Unit tests for inventory reservation logic — mocked DB."""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from services.inventory.errors import ServiceError


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


def _reserve_request(*pairs):
    request = MagicMock(order_id="o1", ttl_seconds=30)
    request.items = [MagicMock(sku=sku, quantity=quantity) for sku, quantity in pairs]
    return request


def _reserve_tx(existing):
    """Route SQL to canned rows so assertions see the real statement order."""

    def execute(query, params=()):
        cursor = MagicMock()
        if query.lstrip().startswith("SELECT reservation_id, state"):
            cursor.fetchone.return_value = existing(params)
        elif "UPDATE inventory" in query:
            cursor.fetchone.return_value = {"stock_version": 2}
        elif "SELECT on_hand, reserved" in query:
            cursor.fetchone.return_value = {"on_hand": 10, "reserved": 1}
        elif "FROM reservations WHERE" in query:
            cursor.fetchone.return_value = {
                "reservation_id": "r-live",
                "order_id": "o1",
                "state": "ACTIVE",
                "expires_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        elif "FROM reservation_items" in query:
            cursor.fetchall.return_value = [{"sku": "SKU-A", "quantity": 2}]
        return cursor

    return execute


class TestReserve:
    def test_locks_skus_in_sorted_order(self):
        from services.inventory import reservation

        db, tx = _mock_db()
        with patch.object(reservation, "uuid4", return_value="r-new"):
            tx.execute.side_effect = _reserve_tx(
                lambda _p: {"reservation_id": "r-new", "state": "ACTIVE"}
            )
            result = reservation.reserve(
                db, MagicMock(), "dev", _reserve_request(("SKU-B", 1), ("SKU-A", 2)), _context()
            )
        locked = [c[0][1][3] for c in tx.execute.call_args_list if "UPDATE inventory" in c[0][0]]
        assert locked == ["SKU-A", "SKU-B"]
        assert result["reservation_id"] == "r-new"

    @pytest.mark.parametrize("state", ["ACTIVE", "COMMITTED"])
    def test_retry_replays_live_reservation_without_reserving_again(self, state):
        from services.inventory import reservation

        db, tx = _mock_db()
        tx.execute.side_effect = _reserve_tx(
            lambda _p: {"reservation_id": "r-live", "state": state}
        )
        result = reservation.reserve(
            db, MagicMock(), "dev", _reserve_request(("SKU-A", 2)), _context()
        )
        assert result["reservation_id"] == "r-live"
        assert not any("UPDATE inventory" in c[0][0] for c in tx.execute.call_args_list)

    @pytest.mark.parametrize("state", ["RELEASED", "EXPIRED"])
    def test_released_or_expired_order_cannot_reserve_again(self, state):
        from services.inventory import reservation

        db, tx = _mock_db()
        tx.execute.side_effect = _reserve_tx(lambda _p: {"reservation_id": "r-old", "state": state})
        with pytest.raises(ServiceError) as failure:
            reservation.reserve(db, MagicMock(), "dev", _reserve_request(("SKU-A", 1)), _context())
        assert failure.value.status == 409


class TestGetStock:
    def test_returns_stock_snapshot(self):
        from services.inventory.reservation import get_stock

        db, tx = _mock_db()
        tx.execute.return_value.fetchone.return_value = {
            "sku": "SKU-001",
            "on_hand": 100,
            "reserved": 10,
            "available": 90,
            "stock_version": 1,
            "changed_at": datetime.now(UTC),
        }
        result = get_stock(db, "dev", "SKU-001")
        assert result["sku"] == "SKU-001"
        assert result["available"] == 90

    def test_raises_not_found(self):
        from services.inventory.reservation import get_stock

        db, tx = _mock_db()
        tx.execute.return_value.fetchone.return_value = None

        with pytest.raises(ServiceError) as exc_info:
            get_stock(db, "dev", "SKU-MISSING")
        assert exc_info.value.status == 404


class TestGetReservationByOrder:
    def test_returns_reservation(self):
        from services.inventory.reservation import get_reservation_by_order

        db, tx = _mock_db()
        row = {
            "reservation_id": "r1",
            "order_id": "o1",
            "state": "ACTIVE",
            "expires_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        items = [{"sku": "SKU-001", "quantity": 2}]

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            cursor = MagicMock()
            if call_count["n"] == 1:
                cursor.fetchone.return_value = row
            else:
                cursor.fetchall.return_value = items
            return cursor

        tx.execute.side_effect = side_effect

        result = get_reservation_by_order(db, "dev", "o1")
        assert result["reservation_id"] == "r1"
        assert result["state"] == "ACTIVE"
        assert len(result["items"]) == 1

    def test_raises_not_found(self):
        from services.inventory.reservation import get_reservation_by_order

        db, tx = _mock_db()
        tx.execute.return_value.fetchone.return_value = None

        with pytest.raises(ServiceError) as exc_info:
            get_reservation_by_order(db, "dev", "o1")
        assert exc_info.value.status == 404


class TestCommitReservation:
    def test_idempotent_if_already_committed(self):
        from services.inventory.reservation import commit_reservation

        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            cursor = MagicMock()
            if call_count["n"] == 1:
                cursor.fetchone.return_value = {
                    "reservation_id": "r1",
                    "state": "COMMITTED",
                    "expires_at": datetime.now(UTC),
                }
            elif call_count["n"] == 2:
                cursor.fetchone.return_value = {
                    "reservation_id": "r1",
                    "order_id": "o1",
                    "state": "COMMITTED",
                    "expires_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            elif call_count["n"] == 3:
                cursor.fetchall.return_value = [{"sku": "SKU-001", "quantity": 2}]
            return cursor

        tx.execute.side_effect = side_effect

        result = commit_reservation(db, events, "dev", "o1", "r1", ctx)
        assert result["state"] == "COMMITTED"

    def test_rejects_expired_reservation(self):
        from services.inventory.reservation import commit_reservation

        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()

        tx.execute.return_value.fetchone.return_value = {
            "reservation_id": "r1",
            "state": "EXPIRED",
            "expires_at": datetime.now(UTC) - timedelta(seconds=60),
        }

        with pytest.raises(ServiceError) as exc_info:
            commit_reservation(db, events, "dev", "o1", "r1", ctx)
        assert exc_info.value.status == 409

    def test_rejects_mismatched_id(self):
        from services.inventory.reservation import commit_reservation

        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()

        tx.execute.return_value.fetchone.return_value = {
            "reservation_id": "r-other",
            "state": "ACTIVE",
            "expires_at": datetime.now(UTC) + timedelta(seconds=30),
        }

        with pytest.raises(ServiceError) as exc_info:
            commit_reservation(db, events, "dev", "o1", "r1", ctx)
        assert exc_info.value.status == 409


class TestReleaseReservation:
    def test_idempotent_if_already_released(self):
        from services.inventory.reservation import release_reservation

        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()

        call_count = {"n": 0}

        def side_effect(*args, **kwargs):
            call_count["n"] += 1
            cursor = MagicMock()
            if call_count["n"] == 1:
                cursor.fetchone.return_value = {
                    "reservation_id": "r1",
                    "state": "RELEASED",
                }
            elif call_count["n"] == 2:
                cursor.fetchone.return_value = {
                    "reservation_id": "r1",
                    "order_id": "o1",
                    "state": "RELEASED",
                    "expires_at": datetime.now(UTC),
                    "updated_at": datetime.now(UTC),
                }
            elif call_count["n"] == 3:
                cursor.fetchall.return_value = []
            return cursor

        tx.execute.side_effect = side_effect
        result = release_reservation(db, events, "dev", "o1", "compensation", ctx)
        assert result["state"] == "RELEASED"

    def test_rejects_committed_reservation(self):
        from services.inventory.reservation import release_reservation

        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()

        tx.execute.return_value.fetchone.return_value = {
            "reservation_id": "r1",
            "state": "COMMITTED",
        }

        with pytest.raises(ServiceError) as exc_info:
            release_reservation(db, events, "dev", "o1", "compensation", ctx)
        assert exc_info.value.status == 409


class TestExpireReservations:
    def test_returns_count(self):
        from services.inventory.reservation import expire_reservations

        db, tx = _mock_db()
        events = MagicMock()
        ctx = _context()

        tx.execute.return_value.fetchall.return_value = []
        result = expire_reservations(db, events, ctx)
        assert result == 0
