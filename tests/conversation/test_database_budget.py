"""M1's configured API connection budget includes its reserved intent-audit slot."""

import pytest

from services.conversation.database import Database
from services.conversation.errors import ServiceError


@pytest.mark.parametrize("value", ["", "none", "0", "1", "11", "3.5"])
def test_invalid_budget_fails_before_connecting(monkeypatch, value):
    monkeypatch.setenv("CONVERSATION_MAX_CONNECTIONS", value)
    with pytest.raises(ValueError, match="CONVERSATION_MAX_CONNECTIONS"):
        Database("explicit-unused-url")


@pytest.mark.parametrize("value", [True, False, 1.5, 1, 11])
def test_explicit_budget_requires_bounded_integer(value):
    with pytest.raises(ValueError, match="CONVERSATION_MAX_CONNECTIONS"):
        Database("explicit-unused-url", max_connections=value)


def test_configured_budget_reserves_audit_capacity_and_recovers_after_saturation(
    database, monkeypatch
):
    monkeypatch.setenv("CONVERSATION_MAX_CONNECTIONS", "3")
    limited = Database(database.url)
    assert limited.max_connections == 3
    with limited.transaction(), limited.transaction():
        # Two ordinary turns can hold connections while their durable audit
        # still has its own slot. A third ordinary caller cannot consume it.
        with limited.transaction(intent_audit=True) as tx:
            assert tx.execute("SELECT 1 AS n").fetchone()["n"] == 1
        with pytest.raises(ServiceError) as error, limited.transaction():
            pytest.fail("ordinary callers exceeded the configured budget")
        assert error.value.body.code == "STORAGE_UNAVAILABLE"
    with limited.transaction() as tx:
        assert tx.execute("SELECT 1 AS n").fetchone()["n"] == 1
