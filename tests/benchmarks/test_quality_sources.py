"""Explicit read-only SQL/file/page doubles; no database or broker integration."""

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from benchmarks.quality_sources import QualitySources, json_value


@pytest.mark.parametrize("readonly", ["on", "off"])
def test_read_connection_enforces_readonly_before_owner_reader(readonly):
    calls = []

    @contextmanager
    def connect_double():
        class Tx:
            def execute(self, statement):
                calls.append(statement)
                assert statement == "SHOW default_transaction_read_only"
                return SimpleNamespace(fetchone=lambda: [readonly])

        yield Tx()

    source = QualitySources(connect_double, None, None)
    if readonly == "on":
        with source.connect():
            pass
    else:
        with pytest.raises(ValueError, match="read-only"):
            with source.connect():
                pytest.fail("write handle must never reach owner reader")
    assert calls == ["SHOW default_transaction_read_only"]


def test_receipt_pages_are_bounded_scoped_and_cursor_driven(monkeypatch):
    calls = []

    def reader_double(connect, namespace, cursor, limit):
        calls.append((namespace, cursor, limit))
        row = SimpleNamespace(model_dump=lambda **kwargs: {"source": "double"})
        return SimpleNamespace(
            receipts=[row] if cursor is None else [], next_cursor="1" if cursor is None else None
        )

    monkeypatch.setattr("benchmarks.quality_sources.receipts", reader_double)
    source = QualitySources(None, None, None)
    assert source.receipt_rows("bench-quality") == [{"source": "double"}]
    assert calls == [("bench-quality", None, 1000), ("bench-quality", "1", 1000)]


def test_receipt_cursor_cycle_cannot_hang(monkeypatch):
    monkeypatch.setattr(
        "benchmarks.quality_sources.receipts",
        lambda *args: SimpleNamespace(receipts=[], next_cursor="1"),
    )
    with pytest.raises(ValueError, match="cursor did not advance"):
        QualitySources(None, None, None).receipt_rows("bench-quality")


def test_active_files_and_membership_use_one_pinned_generation(monkeypatch):
    calls = []

    @contextmanager
    def connect_double():
        yield SimpleNamespace(execute=lambda statement: SimpleNamespace(fetchone=lambda: ["on"]))

    manifest = SimpleNamespace(
        generation=4,
        files=[SimpleNamespace(schema_name="pipeline_minute")],
        model_dump=lambda **kwargs: {"namespace": "bench-quality", "generation": 4},
    )

    def active_double(connect, namespace, dataset):
        calls.append((namespace, dataset))
        return manifest

    def membership_double(tx, namespace, dataset, generation):
        assert (namespace, dataset, generation) == ("bench-quality", "gold", 4)
        return iter(["event-double"])

    monkeypatch.setattr("benchmarks.quality_sources.active_manifest", active_double)
    monkeypatch.setattr("benchmarks.quality_sources.iter_membership", membership_double)
    monkeypatch.setattr("benchmarks.quality_sources.iter_verified", lambda *args: [{"value": 1}])
    result = QualitySources(connect_double, None, None).active("bench-quality")
    assert calls == [("bench-quality", "gold")]
    assert result["generation"] == result["query_generation"] == 4
    assert result["manifest_sha256"] == result["query_manifest_sha256"]
    assert result["membership_ids"] == ["event-double"]


def test_datetime_evidence_is_json_safe_and_preserves_null_timers():
    observed = {"committed_at": datetime(2026, 11, 7, tzinfo=UTC), "flush_duration_seconds": None}
    assert json_value(observed) == {
        "committed_at": "2026-11-07T00:00:00Z",
        "flush_duration_seconds": None,
    }
