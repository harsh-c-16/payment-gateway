"""Scoped dashboard reads with real isolated M1 storage and explicit owner HTTP doubles."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from services.conversation.app import create_app
from services.conversation.dashboard import RECEIPT_LIMIT, pipeline_summary, receipt_summary
from services.conversation.provider_contracts import ContractViolation
from services.conversation.workflow import FixedWorkflow
from tests.conversation.test_shopping_http import ShoppingProviderDouble, say
from tests.conversation.workflow_doubles import common_error


class DashboardProviderDouble(ShoppingProviderDouble):
    damaged_namespace = False

    def gateway(self):
        result = super().gateway()
        result.internal_token = "synthetic-dashboard-token"
        return result

    async def __call__(self, request):
        path, now = request.url.path, datetime.now(UTC).isoformat()
        namespace = request.headers.get("X-Namespace")
        if path == "/health/ready":
            self.requests.append(request)
            assert "Authorization" not in request.headers
            return httpx.Response(200, json={"status": "ready"})
        if path.startswith(("/v1/analytics/", "/internal/v1/analytics/")):
            self.requests.append(request)
            if self.analytics_down:
                return httpx.Response(503, json=common_error("DEPENDENCY_UNAVAILABLE", False))
            if "/manifests/" in path:
                dataset = path.split("/")[-2]
                return httpx.Response(
                    200,
                    json={
                        "namespace": namespace,
                        "dataset": dataset,
                        "generation": 3,
                        "parent_generation": 2,
                        "files": [],
                        "source_ranges": [],
                        "transform_version": "synthetic-v1",
                        "code_commit": "synthetic",
                        "input_manifest_ids": [],
                        "created_at": now,
                    },
                )
            if path.endswith("/receipts"):
                assert request.headers["Authorization"] == "Bearer synthetic-dashboard-token"
                return httpx.Response(
                    200, json={"receipts": [receipt(namespace, now)], "next_cursor": None}
                )
            rows = []
            if path.endswith("/pipeline_minute"):
                rows = [
                    {
                        "namespace": "bench-other" if self.damaged_namespace else namespace,
                        "minute": now,
                        "event_type": "SEARCH_PERFORMED",
                        "source_service": "conversation",
                        "unique_events": 3,
                    }
                ]
            return httpx.Response(200, json={"generation": 3, "rows": rows, "queried_at": now})
        return await super().__call__(request)


def receipt(namespace, now, **changes):
    return {
        "namespace": namespace,
        "source": {
            "topic": "shopping.events",
            "partition": 0,
            "offset": 7,
            "raw_locator": "synthetic-raw",
        },
        "raw_sha256": "a" * 64,
        "event_id": str(uuid4()),
        "disposition": "new_valid",
        "reason_code": None,
        "ingested_at": now,
        "bronze_durable_at": now,
        "silver_committed_observed_at": now,
        "gold_visible_at": now,
        "visibility_generation": 3,
        "timing_validity": "observed",
        **changes,
    }


@pytest.fixture
def dashboard(state, context):
    provider = DashboardProviderDouble()
    app = create_app(
        state=state,
        workflow=FixedWorkflow(state, provider.gateway()),
        mode="stub",
        purpose="contract_test",
    )
    headers = {**context.headers(), "Idempotency-Key": str(uuid4())}
    with TestClient(app) as client:
        created = client.post("/v1/sessions", headers=headers, json={})
        assert created.status_code == 201
        session = created.json()["session_id"]
        headers["X-Session-ID"] = session
        yield client, headers, session, provider


def test_dashboard_combines_scoped_storage_with_projected_owner_facts(dashboard):
    client, headers, session, provider = dashboard
    say(dashboard, "blue shirts")
    response = client.get(f"/v1/sessions/{session}/dashboard", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["session"]["sampled_turns"] == data["session"]["searches"] == 1
    assert data["session"]["model_attempts"] == 0
    assert data["pipeline"]["events"] == 3
    assert data["session"]["pipeline_events_today"] == 3
    assert len(data["datasets"]) == 2
    assert len(data["services"]) == 6 and all(s["status"] == "ready" for s in data["services"])
    assert data["receipt_sample"]["count"] == 1
    assert data["receipt_sample"]["visibility_p95_ms"] == 0
    assert data["unavailable"] == []
    # Session content and service credentials are not part of observability exports.
    assert "blue shirts" not in response.text and "synthetic-dashboard-token" not in response.text
    assert provider.count("/v1/orders") == 0


def test_dashboard_authorizes_before_probing_any_external_provider(dashboard):
    client, headers, session, provider = dashboard
    before = len(provider.requests)
    response = client.get(
        f"/v1/sessions/{session}/dashboard", headers={**headers, "X-User-ID": "other-user"}
    )
    assert response.status_code == 403
    assert len(provider.requests) == before


def test_missing_pipeline_remains_null_while_local_metrics_are_available(dashboard):
    client, headers, session, provider = dashboard
    provider.analytics_down = True
    response = client.get(f"/v1/sessions/{session}/dashboard", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["pipeline"] is data["orders"] is data["receipt_sample"] is None
    assert data["datasets"] == []
    assert data["session"]["turn_p95_ms"] is None
    assert data["catalogue"] is not None
    assert set(data["unavailable"]) == {"pipeline", "orders", "silver", "gold", "receipts"}


def test_dashboard_does_not_expose_other_namespace_gold(dashboard):
    client, headers, session, provider = dashboard
    provider.damaged_namespace = True
    response = client.get(f"/v1/sessions/{session}/dashboard", headers=headers)
    assert response.status_code == 200
    assert response.json()["pipeline"] is None
    assert "pipeline" in response.json()["unavailable"]
    assert "bench-other" not in response.text


def test_receipt_statistics_exclude_recovery_bounds_and_mark_incomplete_samples():
    now = datetime.now(UTC)
    records = [
        receipt("dev", now.isoformat(), gold_visible_at=(now + timedelta(seconds=2)).isoformat()),
        receipt(
            "dev",
            now.isoformat(),
            timing_validity="recovery_upper_bound",
            disposition="duplicate_delivery",
        ),
        receipt("dev", now.isoformat(), timing_validity="missing", gold_visible_at=None),
    ]
    for offset, record in enumerate(records):
        record["source"]["offset"] = offset
    records += [records[0]] * (RECEIPT_LIMIT - len(records))
    result = receipt_summary({"receipts": records, "next_cursor": "more"}, "dev")
    assert result["complete"] is False
    assert result["count"] == 3 and result["journal_observations"] == RECEIPT_LIMIT
    assert result["observed_timings"] == 1 and result["visibility_p95_ms"] == 2000
    assert result["dispositions"] == {"new_valid": 2, "duplicate_delivery": 1}


def test_receipt_summary_rejects_conflicting_bytes_for_one_source_position():
    now = datetime.now(UTC).isoformat()
    first = receipt("dev", now)
    second = {**first, "raw_sha256": "b" * 64}
    with pytest.raises(ContractViolation):
        receipt_summary({"receipts": [first, second], "next_cursor": "2"}, "dev")


def test_pipeline_buckets_do_not_cross_the_requested_day():
    now = datetime.now(UTC).replace(hour=0, minute=2, second=0, microsecond=0)
    result = pipeline_summary({"rows": [], "generation": 1}, "dev", now.date(), now)
    assert len(result["minutes"]) == 3 and result["events"] == 0
    wrong = {
        "rows": [
            {
                "namespace": "dev",
                "minute": (now - timedelta(days=1)).isoformat(),
                "event_type": "X",
                "source_service": "conversation",
                "unique_events": 1,
            }
        ],
        "generation": 1,
    }
    with pytest.raises(ContractViolation):
        pipeline_summary(wrong, "dev", now.date(), now)
