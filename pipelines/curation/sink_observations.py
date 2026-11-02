"""Durable transaction membership and nullable, process-local COMMIT timers."""

from pydantic import TypeAdapter

from shared.contracts.common import Identifier
from shared.contracts.events import Namespace

from .db import rows


def observe_sink_batch(connect, namespace, sequence, committed_at, duration):
    # A restart cannot reconstruct this elapsed timer; leave a lost sample NULL.
    with connect() as tx:
        tx.execute(
            """UPDATE sink_batches SET committed_observed_at=%s,flush_duration_seconds=%s
            WHERE namespace=%s AND batch_sequence=%s AND committed_observed_at IS NULL""",
            (committed_at, duration, namespace, sequence),
        )


def read_sink_batches(connect, namespace, run_id, *, after=0, limit=1000):
    """Read a drained run in bounded pages; active runs can still acquire timers."""
    TypeAdapter(Namespace).validate_python(namespace)
    TypeAdapter(Identifier).validate_python(run_id)
    if type(after) is not int or not 0 <= after <= 2**63 - 1:
        raise ValueError("after must be a nonnegative bigint cursor")
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError("limit must be between 1 and 1000")
    with connect() as tx:
        return rows(
            tx,
            """SELECT *,CASE WHEN flush_duration_seconds IS NULL THEN 'missing'
            ELSE 'observed' END AS timing_validity FROM sink_batches
            WHERE namespace=%s AND run_id=%s AND batch_sequence>%s
            ORDER BY batch_sequence LIMIT %s""",
            (namespace, run_id, after, limit),
        )
