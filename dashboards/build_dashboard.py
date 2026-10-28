"""Deterministic Grafana definition generator. No measured/sample values embedded."""

import json
from pathlib import Path


def definition():
    panels = [
        {
            "id": 1,
            "type": "text",
            "title": "Evidence context (select the matching SUT jobs)",
            "gridPos": {"x": 0, "y": 0, "w": 24, "h": 4},
            "options": {
                "mode": "markdown",
                "content": "Run: **${run_id}** · Variant: **${variant}** · "
                "Workload: **${workload}** · "
                "Evidence: **${evidence_status}**\n\nContext is supplied by the operator; "
                "select only this run's SUT scrape jobs. Missing series mean missing evidence. "
                "Offline artifacts are authoritative for cohorts and exact quantiles.",
            },
        }
    ]
    scope = '{job=~"$jobs"}'
    specs = [
        (
            "Offered / admitted / active Gold (measurement only)",
            "ops",
            [
                'rate(benchmark_planned_total{job=~"$jobs",phase="measurement"}[$__rate_interval])',
                'rate(benchmark_admitted_total{job=~"$jobs",phase="measurement"}[$__rate_interval])',
                'rate(benchmark_gold_visible_total{job=~"$jobs",phase="measurement"}[$__rate_interval])',
            ],
        ),
        (
            "Request latency p50/p95/p99 (histogram estimates)",
            "s",
            [
                f"histogram_quantile({q}, sum by (le,service,route) "
                f"(rate(request_duration_seconds_bucket{scope}[$__rate_interval])))"
                for q in (0.5, 0.95, 0.99)
            ],
        ),
        ("Kafka lag by group/topic/partition", "short", ["kafka_consumer_lag" + scope]),
        (
            "Pending Gold publication (independent of Kafka commits)",
            "short",
            ["gold_pending_events" + scope],
        ),
        ("Outbox pending by service", "short", ["outbox_pending" + scope]),
        ("Oldest outbox row age", "s", ["outbox_oldest_age_seconds" + scope]),
        ("Quarantine by reason", "ops", [f"rate(quarantine_total{scope}[$__rate_interval])"]),
        ("Projection age and apply outcomes", "s", ["projection_age_seconds" + scope]),
        (
            "Saga states and reservation race rejections",
            "short",
            [
                "saga_orders" + scope,
                f"increase(reservation_race_rejections_total{scope}[$__rate_interval])",
            ],
        ),
        (
            "CPU cores used (allocation recorded in artifacts)",
            "short",
            [f"rate(process_cpu_seconds_total{scope}[$__rate_interval])"],
        ),
        (
            "Process RSS (sampled separately per job/instance)",
            "bytes",
            ["process_resident_memory_bytes" + scope],
        ),
        (
            "Scrape availability and collector health",
            "short",
            ["up" + scope, "benchmark_observation_up" + scope, "absent(up" + scope + ")"],
        ),
        ("Active Gold generation", "short", ["gold_generation" + scope]),
        (
            "Stock audit totals (approved read-only projection)",
            "short",
            ["benchmark_inventory_units" + scope],
        ),
        (
            "Generator pending queue (bounded active + queued)",
            "short",
            ["benchmark_pending_records" + scope, "benchmark_pending_bytes" + scope],
        ),
        (
            "Fixed workflow model attempts (required zero)",
            "ops",
            [f"increase(intent_llm_calls_total{scope}[$__rate_interval])"],
        ),
    ]
    for index, (title, unit, expressions) in enumerate(specs):
        panels.append(
            {
                "id": index + 2,
                "type": "timeseries",
                "title": title,
                "datasource": {"type": "prometheus", "uid": "${datasource}"},
                "gridPos": {"x": index % 2 * 12, "y": 4 + index // 2 * 8, "w": 12, "h": 8},
                "fieldConfig": {
                    "defaults": {"unit": unit, "custom": {"spanNulls": False}},
                    "overrides": [],
                },
                "targets": [
                    {"refId": chr(65 + i), "expr": expr, "legendFormat": "__auto"}
                    for i, expr in enumerate(expressions)
                ],
            }
        )
    variables = [
        {"name": "datasource", "type": "datasource", "query": "prometheus"},
        {
            "name": "jobs",
            "type": "query",
            "datasource": "${datasource}",
            "query": "label_values(up, job)",
            "multi": True,
            "includeAll": False,
        },
    ]
    variables.extend(
        {"name": name, "type": "textbox", "query": "NOT_RUN"}
        for name in ("run_id", "variant", "workload", "evidence_status")
    )
    return {
        "uid": "group3-evidence",
        "title": "Group 3 benchmark evidence",
        "schemaVersion": 39,
        "version": 1,
        "editable": True,
        "timezone": "utc",
        "refresh": "1s",
        "tags": ["group3", "evidence"],
        "time": {"from": "now-15m", "to": "now"},
        "templating": {"list": variables},
        "panels": panels,
        "annotations": {"list": []},
    }


if __name__ == "__main__":
    (Path(__file__).parent / "benchmark.json").write_text(
        json.dumps(definition(), indent=2) + "\n", encoding="utf-8"
    )
