import json
from pathlib import Path

from dashboards.build_dashboard import definition


def test_dashboard_is_reproducible_and_separates_stalls_without_zero_filling():
    dashboard = json.loads(Path("dashboards/benchmark.json").read_text(encoding="utf-8"))
    assert dashboard == definition()
    expressions = [
        target["expr"] for panel in dashboard["panels"] for target in panel.get("targets", [])
    ]
    assert any(expr.startswith("kafka_consumer_lag{") for expr in expressions)
    assert any(expr.startswith("gold_pending_events{") for expr in expressions)
    assert any(expr.startswith("outbox_oldest_age_seconds{") for expr in expressions)
    assert all("vector(0)" not in expr and "run_id=" not in expr for expr in expressions)
    assert {"run_id", "workload", "variant", "evidence_status"} <= {
        variable["name"] for variable in dashboard["templating"]["list"]
    }
    assert all(
        p["fieldConfig"]["defaults"]["custom"]["spanNulls"] is False
        for p in dashboard["panels"]
        if p["type"] == "timeseries"
    )
