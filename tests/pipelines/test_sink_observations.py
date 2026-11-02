"""Audit reader bounds fail before connecting to any database."""

import pytest

from pipelines.curation.sink_observations import read_sink_batches


@pytest.mark.parametrize(
    "kwargs",
    [
        {"after": True},
        {"after": -1},
        {"after": 2**63},
        {"after": "0"},
        {"limit": True},
        {"limit": 0},
        {"limit": 1001},
        {"limit": "1"},
    ],
)
def test_sink_audit_rejects_unbounded_or_coerced_cursor(kwargs):
    def never_connect():
        raise AssertionError("invalid request reached SQL")

    with pytest.raises(ValueError):
        read_sink_batches(never_connect, "bench-m11", "explicit-fixture", **kwargs)


@pytest.mark.parametrize("namespace,run_id", [("bad namespace", "run"), ("bench-m11", "")])
def test_sink_audit_requires_canonical_scope(namespace, run_id):
    with pytest.raises(ValueError):
        read_sink_batches(None, namespace, run_id)
