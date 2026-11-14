"""Measured desktop demo activity. No sample defaults or benchmark claims."""

from datetime import UTC, datetime, timedelta
from math import ceil

from .clients import DependencyUnavailable, RemoteError
from .provider_contracts import ContractUnavailable, ContractViolation


def snapshot(state, workflow, session_id, context, *, include_pipeline=True):
    state.shopping_session(session_id, context)  # Authorize before any measurements or Gold reads.
    with state.database.transaction() as tx:
        rows = tx.execute(
            "SELECT response,intent_diagnostic FROM turns WHERE namespace=%s AND session_id=%s "
            "AND user_id=%s ORDER BY created_at DESC LIMIT 500",
            (context.namespace, session_id, context.user_id),
        ).fetchall()
        attempts = tx.execute(
            "SELECT count(*) AS n FROM intent_attempts WHERE namespace=%s AND session_id=%s "
            "AND user_id=%s",
            (context.namespace, session_id, context.user_id),
        ).fetchone()["n"]
        pending = tx.execute(
            "SELECT count(*) AS n FROM outbox WHERE namespace=%s AND aggregate_id=%s "
            "AND published_at IS NULL",
            (context.namespace, session_id),
        ).fetchone()["n"]
    responses = [r["response"] for r in rows]
    durations = sorted(r["timings_ms"]["total"] for r in responses)
    models = [r["timings_ms"]["llm"] for r in responses if r["timings_ms"]["llm"] is not None]
    now = datetime.now(UTC)
    day = now.date()
    result = {
        "session_id": session_id,
        "sampled_turns": len(rows),
        "sample_limit": 500,
        "searches": sum(r["search_id"] is not None for r in responses),
        "model_attempts": attempts,
        "query_embeddings": sum(
            (r["intent_diagnostic"] or {}).get("query_embedding_calls") or 0 for r in rows
        ),
        "dependency_errors": sum(r["outcome"] == "dependency_error" for r in responses),
        "turn_p50_ms": durations[ceil(len(durations) * 0.5) - 1] if durations else None,
        "turn_p95_ms": durations[ceil(len(durations) * 0.95) - 1] if durations else None,
        "model_mean_ms": sum(models) / len(models) if models else None,
        "session_outbox_pending": pending,
        "pipeline_status": "unavailable",
        "pipeline_events_today": None,
        "pipeline_events_by_type": None,
        "gold_generation": None,
        "pipeline_date_utc": day.isoformat(),
        "checked_at": now,
    }
    if workflow is None or not include_pipeline:
        return result
    try:
        gold = workflow.call(
            "gold",
            context,
            table="pipeline_minute",
            params={
                "namespace": context.namespace,
                "date_from": day.isoformat(),
                "date_to": (day + timedelta(days=1)).isoformat(),
            },
        )
        counts = {}
        for row in gold["rows"]:
            if (
                row.get("namespace") != context.namespace
                or type(row.get("unique_events")) is not int
                or row["unique_events"] < 0
                or not isinstance(row.get("event_type"), str)
            ):
                raise ContractViolation("Invalid pipeline aggregate")
            kind = row["event_type"]
            counts[kind] = counts.get(kind, 0) + row["unique_events"]
        result.update(
            pipeline_status="available",
            pipeline_events_today=sum(counts.values()),
            pipeline_events_by_type=counts,
            gold_generation=gold["generation"],
        )
    except (DependencyUnavailable, RemoteError, ContractUnavailable, ContractViolation):
        pass  # Unavailable data stays null, never a fabricated zero or success.
    return result
