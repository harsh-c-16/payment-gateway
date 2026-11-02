"""Pure replay semantics/repair guards; no integration claim."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from pipelines.replay.jobs import create_replay
from pipelines.replay.reconciliation import semantic_row
from pipelines.replay.repairs import repair_failure


def test_semantics_ignore_processing_provenance_but_keep_state_and_money():
    row = {
        "namespace": "bench-source",
        "order_id": str(uuid4()),
        "order_version": 3,
        "order_status": "CONFIRMED",
        "total_amount_minor": 9223372036854775807,
        "currency": "INR",
        "revision": 8,
        "transform_version": "old",
        "publication_generation": 2,
    }
    changed = dict(
        row,
        namespace="replay-target",
        revision=99,
        transform_version="new",
        publication_generation=10,
    )
    assert semantic_row("order_fact", row) == semantic_row("order_fact", changed)
    assert semantic_row("order_fact", row) != semantic_row(
        "order_fact", dict(changed, order_status="CANCELLED")
    )
    assert semantic_row("order_fact", row) != semantic_row(
        "order_fact", dict(changed, total_amount_minor=0)
    )


@pytest.mark.parametrize("change", ["same_id", "missing_reason", "missing_locator", "bad_id"])
def test_repairs_require_new_identity_and_explicit_reference(change):
    original, new = str(uuid4()), str(uuid4())
    metadata = {
        "original_event_id": original,
        "source_locator": "bronze/source.jsonl#1",
        "repair_reason": "fixture-correction",
    }
    if change == "same_id":
        new = original
    elif change == "bad_id":
        metadata["original_event_id"] = "bad"
    else:
        metadata.pop("repair_reason" if change == "missing_reason" else "source_locator")
    checked = SimpleNamespace(
        document={"metadata": metadata},
        envelope=SimpleNamespace(event_id=new, namespace="bench-source"),
    )
    known_reference_double = SimpleNamespace(
        execute=lambda *a: SimpleNamespace(fetchone=lambda: (1,))
    )
    assert (
        repair_failure(checked, "a" * 64, known_reference_double).reason_code.value
        == "INVARIANT_VIOLATION"
    )
    checked.document["metadata"] = {
        "original_event_id": original,
        "source_locator": "bronze/source.jsonl#1",
        "repair_reason": "fixture-correction",
    }
    checked.envelope.event_id = str(uuid4())
    assert repair_failure(checked, "a" * 64, known_reference_double) is None


def test_uninstalled_transform_is_rejected_before_database_access():
    pipeline = SimpleNamespace(transform_version="installed")
    with pytest.raises(ValueError, match="not installed"):
        create_replay(
            pipeline,
            {
                "source_manifest_ids": [str(uuid4())],
                "target_namespace": "replay-isolated",
                "transform_version": "unknown",
            },
        )
