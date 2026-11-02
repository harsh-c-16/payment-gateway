"""M08 process kills with explicit barrier acknowledgements, real SQL and retained files."""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from pipelines.storage import publication
from shared.event_transport.schemas import canonical_json

from . import test_vertical_live as live
from .test_publication_live import candidate_double
from .test_vertical_live import count, curate, event, query, record

vertical = live.vertical
pytestmark = live.pytestmark


@pytest.mark.parametrize(
    "operation,point",
    [
        ("snapshot", "before_rename"),
        ("snapshot", "after_files_durable"),
        ("snapshot", "before_manifest_swap"),
        ("snapshot", "after_manifest_swap"),
        ("candidate", "after_files_durable"),
        ("candidate", "before_manifest_swap"),
        ("candidate", "after_manifest_swap"),
    ],
)
def test_kill_at_acknowledged_publication_boundary_is_recoverable(vertical, operation, point):
    initial = event(vertical)
    curate(vertical, [record(vertical, initial)])
    vertical.publish_snapshot(vertical.test_namespace)
    candidate_path = "unused"
    if operation == "candidate":
        candidate = candidate_double(vertical)
        data = canonical_json(candidate.model_dump(mode="json"))
        candidate_path = "probe/candidate.json"
        vertical.store.write_immutable(candidate_path, data, hashlib.sha256(data).hexdigest())
    curate(vertical, [record(vertical, event(vertical, 2), 1)])
    with vertical.connect() as tx:
        schema = tx.execute("SELECT current_schema()").fetchone()[0]
    before_files = set(vertical.store.list_orphans(set()))
    child = subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.pipelines.publication_crash",
            str(vertical.store.root),
            vertical.test_namespace,
            schema,
            operation,
            point,
            candidate_path,
        ],
        capture_output=True,
        text=True,
        timeout=60,
        env=os.environ.copy(),
    )
    assert child.returncode == 73, child.stderr
    assert f"M08_BOUNDARY_ACK:{operation}:{point}" in child.stdout
    # Process exit precedes server-side session cleanup; wait for this exact lock.
    with vertical.connect() as tx, tx.transaction():
        tx.execute("SET LOCAL lock_timeout='5s'")
        tx.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            (publication.lock_key(vertical.test_namespace, "publisher"),),
        )
    committed = point == "after_manifest_swap"
    visible = query(vertical)
    assert visible.generation == (2 if committed else 1)
    expected = 2 if operation == "snapshot" and committed else 1
    assert visible.rows[0]["unique_events"] == expected
    assert count(vertical, "export_pending") == (0 if expected == 2 else 1)
    assert before_files <= set(vertical.store.list_orphans(set()))
    with vertical.connect() as tx:
        generations = tx.execute(
            "SELECT min(generation),max(generation) FROM active_datasets"
        ).fetchone()
        assert generations == (visible.generation, visible.generation)
        if operation == "snapshot" and committed:
            assert (
                tx.execute(
                    "SELECT count(*) FROM event_visibility WHERE observed_at IS NULL"
                ).fetchone()[0]
                == 1
            )
    recovered = vertical.publish_snapshot(vertical.test_namespace)
    assert recovered.generation == (3 if operation == "candidate" and committed else 2)
    assert query(vertical).rows[0]["unique_events"] == 2 and count(vertical, "export_pending") == 0
    with vertical.connect() as tx:
        assert (
            tx.execute(
                "SELECT generation FROM event_visibility WHERE event_id=%s", (initial.event_id,)
            ).fetchone()[0]
            == 1
        )
        if operation == "snapshot" and committed:
            assert (
                tx.execute(
                    """SELECT count(*) FROM event_visibility
                    WHERE timing_validity='recovery_upper_bound'"""
                ).fetchone()[0]
                == 1
            )
    facts = dict(
        operation=operation,
        point=point,
        acknowledgement=child.stdout.strip(),
        returncode=child.returncode,
        active_at_crash=visible.generation,
        count_at_crash=expected,
        recovered_generation=recovered.generation,
        retained_prior_files=True,
        code_commit=vertical.code_commit,
    )
    Path(f"artifacts/m08/crash-{operation}-{point}.json").write_text(json.dumps(facts, indent=2))
