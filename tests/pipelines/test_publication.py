"""Canonical compaction integrity format, independent of filesystem durability."""

import hashlib
from datetime import UTC, datetime
from decimal import Decimal

from pipelines.storage.candidates import canonical_logical_row, digest_sorted_rows


def test_canonical_row_and_framed_sorted_digest_preserve_exact_values():
    row = {
        "currency": "INR",
        "amount_minor": Decimal(2**64 - 2),
        "empty": None,
        "time": datetime(2026, 11, 1, tzinfo=UTC),
    }
    expected = (
        b'["fixture",1,{"amount_minor":18446744073709551614,"currency":"INR",'
        b'"empty":null,"time":"2026-11-01T00:00:00Z"}]'
    )
    assert canonical_logical_row("fixture", 1, row) == expected
    material = b"m08-logical-rows-v1\n" + str(len(expected)).encode() + b":" + expected + b"\n"
    assert digest_sorted_rows([expected]) == hashlib.sha256(material).hexdigest()
    assert digest_sorted_rows([b"a", b"bc"]) != digest_sorted_rows([b"ab", b"c"])
    assert digest_sorted_rows([]) == hashlib.sha256(b"m08-logical-rows-v1\n").hexdigest()
