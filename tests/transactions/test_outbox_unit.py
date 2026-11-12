"""Unit tests for outbox serialization and DDL loading — no database needed."""

from unittest.mock import MagicMock

import pytest

from shared.outbox import OutboxError, _canonical_json, _serialise, outbox_table_ddl, relay_once


def test_empty_relay_pass_releases_transaction_without_publishing():
    connection = MagicMock()
    connection.cursor.return_value.__enter__.return_value.fetchall.return_value = []
    publisher = MagicMock()
    assert relay_once(connection, publisher).scanned == 0
    connection.commit.assert_called_once_with()
    publisher.publish_event.assert_not_called()


class TestCanonicalJson:
    def test_deterministic(self):
        obj = {"b": 2, "a": 1}
        result = _canonical_json(obj)
        assert result == b'{"a":1,"b":2}'

    def test_no_spaces(self):
        obj = {"key": "value", "list": [1, 2]}
        result = _canonical_json(obj)
        assert b" " not in result


class TestOutboxDDL:
    def test_contains_create_table(self):
        ddl = outbox_table_ddl()
        assert "CREATE TABLE" in ddl
        assert "outbox" in ddl
        assert "event_id" in ddl
        assert "published_at" in ddl


class TestSerialise:
    def test_rejects_non_event(self):
        with pytest.raises(TypeError):
            _serialise("not an event")

    def test_rejects_dict(self):
        with pytest.raises(TypeError):
            _serialise({"event_id": "abc"})


class TestAppendOutboxValidation:
    def test_requires_active_transaction(self):
        from psycopg.pq import TransactionStatus

        from shared.outbox import append_outbox

        mock_tx = MagicMock()
        mock_tx.info.transaction_status = TransactionStatus.IDLE

        mock_event = MagicMock()
        mock_event.__class__.__name__ = "EventEnvelope"

        with pytest.raises((OutboxError, TypeError)):
            append_outbox(mock_tx, mock_event)
