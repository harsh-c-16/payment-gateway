"""Scripted HTTP/producer/analytics double. Never a live-provider fixture or review."""

import copy
import json
from uuid import uuid4

import httpx

from benchmarks.g3 import G3Binding, G3Owners
from benchmarks.g3_http import G3HTTP
from projectctl.artifacts import content_hash, write_json

NOW = "2026-11-07T12:00:00Z"


class G3Double:
    def __init__(self, directory, status="CONFIRMED", *, lost=0, corrupt=None):
        self.status, self.lost, self.corrupt = status, lost, corrupt
        self.requests, self.callbacks = [], []
        self.ids = {
            k: str(uuid4()) for k in ("session", "cart", "quote", "order", "payment", "reservation")
        }
        self.sku, self.user = "FIXTURE-SKU", "fixture-user"
        self.line = {
            "sku": self.sku,
            "quantity": 1,
            "unit_price_minor": 100,
            "line_total_minor": 100,
            "catalog_version": 1,
        }
        self.case = "smoke/G3-" + ("success" if status == "CONFIRMED" else "decline")
        self.fixture_path = directory / (status + "-fixture.json")
        self.fixture = {
            "case_id": self.case,
            "input": {
                "user_id": self.user,
                "sku": self.sku,
                "text": "fixture shirt",
                "quantity": 1,
                "confirmed": True,
                "logical_event_counts": {"ORDER_CREATED": 1, "ORDER_" + status: 1},
            },
            "expected": {
                "events": None,
                "source_dispositions": None,
                "source_manifest_ids": None,
                "orders": {
                    "@id:order": {
                        "quote_id": "@id:quote",
                        "user_id": self.user,
                        "session_id": "@id:session",
                        "lines": [self.line],
                        "total_amount_minor": 100,
                        "currency": "INR",
                    }
                },
                "opening_stock": {self.sku: 10},
                "replenishment": {self.sku: 0},
                "gold_totals_by_currency": {"INR": 100 if status == "CONFIRMED" else 0},
                "gold_business_rows": {
                    "order_fact": {"@id:order": {"status": status, "total_amount_minor": 100}}
                },
            },
        }
        write_json(self.fixture_path, self.fixture)
        self.owners = G3Owners(self.prepare, self.drain, self.producer, self.analytics)

    def adapter(self):
        return G3Binding(
            self.case,
            self.fixture_path,
            self.owners,
            self.http,
            mode="stub",
            poll_seconds=0.001,
            finality_seconds=1,
        )

    def http(self):
        return G3HTTP(
            {
                name: "http://" + name + ".test"
                for name in ("conversation", "orders", "inventory", "payments", "catalog")
            },
            "explicit-test-token",
            mode="stub",
            transport=httpx.MockTransport(self),
        )

    def order(self):
        return {
            "order_id": self.ids["order"],
            "quote_id": self.ids["quote"],
            "user_id": self.user,
            "session_id": self.ids["session"],
            "status": self.status,
            "order_version": 3,
            "lines": [self.line],
            "total_amount_minor": 100,
            "currency": "INR",
            "reservation_id": self.ids["reservation"],
            "payment_id": self.ids["payment"],
            "failure_code": "DECLINED" if self.status == "CANCELLED" else None,
            "created_at": NOW,
            "updated_at": NOW,
        }

    def stock(self):
        count = 9 if self.status == "CONFIRMED" else 10
        return {
            "sku": self.sku,
            "on_hand": count,
            "available": count,
            "reserved": 0,
            "stock_version": 3,
            "changed_at": NOW,
        }

    def payment(self):
        return {
            "payment_id": self.ids["payment"],
            "order_id": self.ids["order"],
            "attempt_number": 1,
            "status": "SUCCESS" if self.status == "CONFIRMED" else "FAILED",
            "amount_minor": 100,
            "currency": "INR",
            "failure_code": "DECLINED" if self.status == "CANCELLED" else None,
            "created_at": NOW,
            "updated_at": NOW,
        }

    def product(self):
        value = {
            k: None
            for k in (
                "description",
                "category",
                "brand",
                "brand_normalized",
                "size",
                "size_kind",
                "colour",
                "material",
                "seller_id",
                "retail_price_minor",
                "rating",
                "inactive_reason",
            )
        }
        value.update(
            product_id=self.sku,
            sku=self.sku,
            title="fixture shirt",
            category_path_normalized=[],
            attributes={},
            quality_flags=[],
            dataset_revision="explicit-double",
            source_pid="fixture",
            source_observation_id="fixture",
            source_crawled_at=NOW,
            currency="INR",
            currency_source="project_assumption",
            catalog_version=1,
            active=True,
            price_minor=100,
        )
        return value

    async def __call__(self, request):
        body = json.loads(request.content) if request.content else None
        self.requests.append(
            {
                "path": request.url.path,
                "method": request.method,
                "headers": dict(request.headers),
                "body": body,
            }
        )
        path = request.url.path
        code = 200
        if path == "/v1/sessions":
            code, result = (
                201,
                {"session_id": self.ids["session"], "cart_id": self.ids["cart"], "cart_version": 0},
            )
        elif path.endswith("/turns"):
            result = {
                "turn_id": str(uuid4()),
                "response_text": "fixture",
                "intent": None,
                "search_id": str(uuid4()),
                "products": [{"sku": self.sku}],
                "proposed_action": None,
                "outcome": "success",
                "extractor_source": "rules",
                "llm_call_count": 0,
                "timings_ms": {
                    "parse": 0.1,
                    "llm": None,
                    "search": 0.1,
                    "compose": 0.1,
                    "total": 0.3,
                },
            }
        elif "/items/" in path:
            result = {
                "cart_id": self.ids["cart"],
                "session_id": self.ids["session"],
                "user_id": self.user,
                "version": 1,
                "lines": [{"sku": self.sku, "quantity": 1, "display_price_minor": None}],
                "updated_at": NOW,
            }
        elif path.endswith("/quote"):
            code, result = (
                201,
                {
                    "quote_id": self.ids["quote"],
                    "cart_id": self.ids["cart"],
                    "cart_version": 1,
                    "user_id": self.user,
                    "lines": [self.line],
                    "currency": "INR",
                    "total_amount_minor": 100,
                    "created_at": NOW,
                    "expires_at": "2026-11-07T12:01:00Z",
                },
            )
        elif path.endswith("/checkout"):
            if self.lost:
                self.lost -= 1
                raise httpx.ReadTimeout("explicit lost response", request=request)
            code, result = (
                202,
                {
                    "order_id": self.ids["order"],
                    "status": "PENDING",
                    "status_url": "/v1/orders/" + self.ids["order"],
                },
            )
        elif path.startswith("/v1/orders/"):
            result = self.order()
        elif path == "/internal/v1/audit/orders":
            result = {"items": [self.order()], "count": 1}
        elif path == "/internal/v1/audit/reservations":
            result = {
                "items": [
                    {
                        "order_id": self.ids["order"],
                        "state": "COMMITTED" if self.status == "CONFIRMED" else "RELEASED",
                        "items": [{"sku": self.sku, "quantity": 1}],
                    }
                ],
                "count": 1,
            }
        elif path == "/internal/v1/audit/payments":
            result = {"items": [{"order_id": self.ids["order"]}], "count": 1}
        elif "/payments/by-order/" in path:
            result = {
                "attempts": [self.payment()],
                "quiesced": self.status == "CANCELLED",
                "net_debit_minor": 100 if self.status == "CONFIRMED" else 0,
            }
        elif path == "/internal/v1/audit/ledger":
            entries = (
                []
                if self.status != "CONFIRMED"
                else [
                    {
                        "entry_id": "debit",
                        "order_id": self.ids["order"],
                        "payment_id": self.ids["payment"],
                        "kind": "DEBIT",
                        "amount_minor": 100,
                        "currency": "INR",
                    }
                ]
            )
            result = {"items": entries, "count": len(entries), "net_debit_minor": 100}
        elif path.startswith("/internal/v1/inventory/"):
            result = self.stock()
        elif path.startswith("/v1/products/"):
            result = {"product": self.product(), "stock": self.stock()}
        else:
            raise AssertionError("unplanned double endpoint: " + path)
        if self.corrupt:
            self.corrupt(path, result)
        return httpx.Response(code, json=result)

    async def prepare(self, context, frozen_input):
        self.callbacks.append("prepare")
        return {
            "namespace": context["namespace"],
            "run_id": context["run_id"],
            "created_new": True,
            "simulator_control_verified": True,
            "payment_outcome": "SUCCESS" if self.status == "CONFIRMED" else "DECLINED",
            "opening_stock": {self.sku: 10},
        }

    async def drain(self, context):
        self.callbacks.append("drain")
        return {
            **{k: context[k] for k in ("namespace", "run_id", "case_id")},
            "collection_complete": True,
            "pending_outbox": 0,
            "replenishment": {self.sku: 0},
        }

    async def producer(self, context):
        self.callbacks.append("producer")
        deliveries = []
        for index, (kind, status) in enumerate(
            (("ORDER_CREATED", "PENDING"), ("ORDER_" + self.status, self.status))
        ):
            event = {
                "event_id": str(uuid5_double(kind)),
                "event_type": kind,
                "schema_version": 1,
                "event_time": NOW,
                "produced_at": NOW,
                "namespace": context["namespace"],
                "run_id": context["run_id"],
                "source_service": "orders",
                "correlation_id": context["transaction"]["request_id"],
                "session_id": self.ids["session"],
                "user_id": self.user,
                "aggregate_type": "order",
                "aggregate_id": self.ids["order"],
                "aggregate_version": index + 1,
                "metadata": {
                    "dataset_revision": "explicit-double",
                    "synthetic": True,
                    "scenario_source": "simulation",
                },
                "payload": {
                    k: v
                    for k, v in self.order().items()
                    if k
                    in {
                        "order_id",
                        "quote_id",
                        "user_id",
                        "session_id",
                        "total_amount_minor",
                        "currency",
                        "created_at",
                        "failure_code",
                        "reservation_id",
                        "payment_id",
                    }
                },
            }
            event["payload"]["order_status"] = status
            deliveries.append(
                {
                    "record_id": str(index),
                    "event": event,
                    "topic": context["namespace"] + ".order-events.v1",
                    "partition": 0,
                    "offset": index,
                }
            )
        # An exact duplicate physical delivery is retained and independently classified.
        deliveries.append({**copy.deepcopy(deliveries[0]), "record_id": "duplicate", "offset": 2})
        self.proof = {
            **{k: context[k] for k in ("namespace", "run_id", "case_id")},
            "collection_complete": True,
            "origin": "producer_outbox_and_broker",
            "pending_outbox": 0,
            "deliveries": deliveries,
            "source_manifest_ids": ["producer-manifest"],
        }
        return self.proof

    async def analytics(self, context):
        self.callbacks.append("analytics")
        proof = self.proof
        events = {r["event"]["event_id"]: content_hash(r["event"]) for r in proof["deliveries"]}
        return {
            **{k: context[k] for k in ("namespace", "run_id", "case_id")},
            "test_mode": "stub",
            "collection_complete": True,
            "source_dispositions": [
                {
                    "record_id": r["record_id"],
                    "disposition": "duplicate_delivery"
                    if r["record_id"] == "duplicate"
                    else "new_valid",
                }
                for r in proof["deliveries"]
            ],
            "silver_events": [{"event_id": k, "content_sha256": v} for k, v in events.items()],
            "active_gold": {
                "namespace": context["namespace"],
                "generation": 1,
                "query_generation": 1,
                "manifest_sha256": "a" * 64,
                "query_manifest_sha256": "a" * 64,
                "source_manifest_ids": ["producer-manifest"],
                "membership_ids": list(events),
                "visibility_receipts": [
                    {"event_id": k, "generation": 1, "manifest_sha256": "a" * 64} for k in events
                ],
                "totals_by_currency": {"INR": 100 if self.status == "CONFIRMED" else 0},
                "business_rows": {
                    "order_fact": {
                        self.ids["order"]: {"status": self.status, "total_amount_minor": 100}
                    }
                },
            },
        }


def uuid5_double(value):
    from uuid import NAMESPACE_URL, uuid5

    return uuid5(NAMESPACE_URL, "explicit-double-" + value)
