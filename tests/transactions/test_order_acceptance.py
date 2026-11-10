"""Order acceptance rules (common spec §8, §9.1) without a database or real catalogue.

The catalogue is an explicit httpx.MockTransport double; database access is a MagicMock.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import httpx
import pytest

from services.orders import commands
from services.orders.errors import ServiceError
from shared.contracts.common import RequestContext

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def utc(moment):
    return moment.isoformat().replace("+00:00", "Z")


def quote(quote_id, *, user="buyer", expires=NOW + timedelta(seconds=60), lines=None):
    lines = lines or [
        {
            "sku": "FK-1",
            "quantity": 2,
            "unit_price_minor": 100,
            "line_total_minor": 200,
            "catalog_version": 1,
        }
    ]
    return {
        "quote_id": quote_id,
        "user_id": user,
        "cart_id": str(uuid4()),
        "cart_version": 1,
        "lines": lines,
        "total_amount_minor": sum(line["line_total_minor"] for line in lines),
        "currency": "INR",
        "created_at": utc(NOW - timedelta(seconds=5)),
        "expires_at": utc(expires),
    }


def code_of(failure):
    return failure.value.status, failure.value.body.code


class TestVerifyQuote:
    def test_valid_quote_passes(self):
        quote_id = str(uuid4())
        commands._verify_quote(quote(quote_id), quote_id, "buyer", NOW)

    def test_expired_quote_is_quote_expired(self):
        quote_id = str(uuid4())
        with pytest.raises(ServiceError) as failure:
            commands._verify_quote(quote(quote_id, expires=NOW), quote_id, "buyer", NOW)
        assert code_of(failure) == (409, "QUOTE_EXPIRED")

    def test_another_users_quote_is_forbidden(self):
        quote_id = str(uuid4())
        with pytest.raises(ServiceError) as failure:
            commands._verify_quote(quote(quote_id, user="other"), quote_id, "buyer", NOW)
        assert code_of(failure) == (403, "FORBIDDEN")

    def test_different_quote_id_is_a_provider_fault(self):
        with pytest.raises(ServiceError) as failure:
            commands._verify_quote(quote(str(uuid4())), str(uuid4()), "buyer", NOW)
        assert code_of(failure) == (503, "DEPENDENCY_UNAVAILABLE")

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda q: q.update(currency="USD"),
            lambda q: q.pop("expires_at"),
            lambda q: q["lines"][0].update(quantity=0),
            lambda q: q.update(lines=[]),
        ],
    )
    def test_malformed_quote_is_a_provider_fault(self, mutate):
        quote_id = str(uuid4())
        document = quote(quote_id)
        mutate(document)
        with pytest.raises(ServiceError) as failure:
            commands._verify_quote(document, quote_id, "buyer", NOW)
        assert code_of(failure) == (503, "DEPENDENCY_UNAVAILABLE")

    def test_line_total_must_equal_price_times_quantity(self):
        quote_id = str(uuid4())
        document = quote(quote_id)
        document["lines"][0]["line_total_minor"] = 150
        document["total_amount_minor"] = 150
        with pytest.raises(ServiceError) as failure:
            commands._verify_quote(document, quote_id, "buyer", NOW)
        assert failure.value.status == 503

    @pytest.mark.parametrize("problem", ["duplicate_sku", "wrong_total"])
    def test_inconsistent_lines_are_rejected(self, problem):
        quote_id = str(uuid4())
        line = {
            "sku": "FK-1",
            "quantity": 1,
            "unit_price_minor": 100,
            "line_total_minor": 100,
            "catalog_version": 1,
        }
        document = quote(quote_id, lines=[line, dict(line)])
        if problem == "wrong_total":
            document["lines"][1]["sku"] = "FK-2"
            document["total_amount_minor"] = 999
        with pytest.raises(ServiceError) as failure:
            commands._verify_quote(document, quote_id, "buyer", NOW)
        assert code_of(failure) == (409, "ILLEGAL_STATE")


def context(user="buyer"):
    return RequestContext(
        namespace="bench-acceptance",
        run_id="unit",
        user_id=user,
        correlation_id=str(uuid4()),
        request_id=str(uuid4()),
        session_id=None,
    )


class TestFetchQuote:
    def fetch(self, status, payload=None):
        seen = {}

        def handler(request):
            seen["auth"] = request.headers.get("Authorization")
            seen["user"] = request.headers.get("X-User-ID")
            return httpx.Response(status, json=payload or {"error": {}})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        with patch.object(commands, "_HTTP", client):
            result = commands._fetch_quote("http://catalog.double", "q1", context(), "tok")
        return result, seen

    def test_sends_service_token_and_caller(self):
        _, seen = self.fetch(200, {"quote_id": "q1"})
        assert seen == {"auth": "Bearer tok", "user": "buyer"}

    @pytest.mark.parametrize(
        ("status", "expected"),
        [
            (404, (404, "NOT_FOUND")),
            (403, (403, "FORBIDDEN")),
            (401, (503, "DEPENDENCY_UNAVAILABLE")),
            (500, (503, "DEPENDENCY_UNAVAILABLE")),
        ],
    )
    def test_catalogue_status_mapping(self, status, expected):
        with pytest.raises(ServiceError) as failure:
            self.fetch(status)
        assert code_of(failure) == expected


class TestCreateOrderReplay:
    def test_accepted_quote_replays_before_quote_is_fetched(self):
        db = MagicMock()
        tx = db.transaction.return_value.__enter__.return_value
        tx.execute.return_value.fetchone.return_value = {"order_id": "o-1", "status": "CONFIRMED"}
        request = MagicMock(quote_id="q1", session_id=str(uuid4()))
        with patch.object(commands, "_fetch_quote") as fetch:
            result = commands.create_order(
                db,
                MagicMock(),
                "bench-acceptance",
                request,
                context(),
                catalog_url="",
                internal_token="",
            )
        fetch.assert_not_called()
        assert result == {"order_id": "o-1", "status": "CONFIRMED", "status_url": "/v1/orders/o-1"}

    def test_rejected_quote_writes_nothing(self):
        db = MagicMock()
        tx = db.transaction.return_value.__enter__.return_value
        tx.execute.return_value.fetchone.return_value = None
        request = MagicMock(quote_id=str(uuid4()), session_id=str(uuid4()))
        expired = quote(request.quote_id, expires=datetime.now(UTC) - timedelta(seconds=1))
        events = MagicMock()
        with patch.object(commands, "_fetch_quote", return_value=expired):
            with pytest.raises(ServiceError) as failure:
                commands.create_order(
                    db,
                    events,
                    "bench-acceptance",
                    request,
                    context(),
                    catalog_url="",
                    internal_token="",
                )
        assert code_of(failure) == (409, "QUOTE_EXPIRED")
        assert not any("INSERT" in str(call) for call in tx.execute.call_args_list)
        events.append.assert_not_called()
