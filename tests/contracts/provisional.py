"""Explicit provisional schemas/test examples. Never imported by production clients.

These are consumer interpretations of common §§3–5/Appendix A, pending owners'
canonical contracts. Analytics pagination shapes especially require review.
"""

import copy
import json
from pathlib import Path
from uuid import UUID

from services.conversation.provider_contracts import ENDPOINTS, OpenAPIContracts

ROOT = Path(__file__).resolve().parents[2]


def uid(number):
    return str(UUID(int=number))


def obj(**properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def array(items, **bounds):
    return {"type": "array", "items": items, **bounds}


def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


TEXT = {"type": "string"}
ID = {"type": "string", "format": "uuid"}
INT = {"type": "integer", "minimum": 0, "maximum": 2**63 - 1}
VERSION = {"type": "integer", "minimum": 1}
MONEY = INT
PRICE = {"type": "integer", "minimum": 1, "maximum": 1000000000}
QTY = {"type": "integer", "minimum": 1, "maximum": 10}
BOOL = {"type": "boolean"}
STAMP = {"type": "string", "format": "date-time", "pattern": "Z$"}
SKU = {"type": "string", "pattern": "^[!-~]{1,64}$"}
INR = {"const": "INR"}
ANY_OBJECT = {"type": "object"}
TEXTS = array(TEXT)
NOW = "2026-10-25T10:00:00Z"

INTENT = obj(
    query_text=TEXT,
    category=nullable(TEXT),
    size=nullable(TEXT),
    colour=nullable(TEXT),
    material=nullable(TEXT),
    max_price_minor=nullable(MONEY),
    occasion=nullable(TEXT),
    currency=INR,
)
INTENT["properties"].update(brand=nullable(TEXT), category_path_prefix=nullable(TEXTS))
HIT = obj(
    sku=SKU,
    product_id=SKU,
    title=TEXT,
    category=nullable(TEXT),
    brand=nullable(TEXT),
    size=nullable(TEXT),
    colour=nullable(TEXT),
    material=nullable(TEXT),
    price_minor=PRICE,
    currency=INR,
    catalog_version=VERSION,
    dataset_revision=TEXT,
    quality_flags=TEXTS,
    score={"type": "number"},
    stock_available=INT,
    stock_version=VERSION,
    stock_updated_at=STAMP,
    stock_applied_at=STAMP,
    retrieval_mode={"enum": ["lexical", "hybrid_exact", "hybrid_ann"]},
    rank=VERSION,
)
SEARCH_REQUEST = obj(
    request_id=ID,
    session_id=ID,
    intent=INTENT,
    top_k={"type": "integer", "minimum": 1, "maximum": 20},
    mode=TEXT,
)
SEARCH = obj(
    search_id=ID,
    hits=array(HIT, maxItems=20),
    mode=TEXT,
    candidate_count=INT,
    eligible_count=INT,
    returned_count=INT,
    exhausted=BOOL,
    embedding_revision=nullable(TEXT),
    timings_ms=obj(
        embedding={"type": "number", "minimum": 0},
        filter={"type": "number", "minimum": 0},
        rank={"type": "number", "minimum": 0},
        total={"type": "number", "minimum": 0},
    ),
    embedding_calls=INT,
    served_at=STAMP,
)
LINE = obj(sku=SKU, quantity=QTY, display_price_minor=nullable(MONEY))
QUOTE_REQUEST = obj(cart_id=ID, cart_version=INT, lines=array(LINE, minItems=1, maxItems=20))
QUOTE_LINE = obj(
    sku=SKU, quantity=QTY, unit_price_minor=PRICE, line_total_minor=MONEY, catalog_version=VERSION
)
QUOTE = obj(
    quote_id=ID,
    user_id=TEXT,
    cart_id=ID,
    cart_version=INT,
    lines=array(QUOTE_LINE, minItems=1, maxItems=20),
    total_amount_minor=MONEY,
    currency=INR,
    created_at=STAMP,
    expires_at=STAMP,
)
CREATE_ORDER = obj(quote_id=ID, session_id=ID, confirmation_id=ID)
ACCEPTED = obj(order_id=ID, status=TEXT, status_url=TEXT)
ORDER = obj(
    order_id=ID,
    quote_id=ID,
    user_id=TEXT,
    session_id=ID,
    status={
        "enum": [
            "PENDING",
            "RESERVING",
            "PAYMENT_PENDING",
            "COMMITTING_STOCK",
            "CONFIRMED",
            "COMPENSATING",
            "CANCELLED",
            "MANUAL_REVIEW",
        ]
    },
    order_version=VERSION,
    lines=array(QUOTE_LINE, minItems=1, maxItems=20),
    total_amount_minor=MONEY,
    currency=INR,
    reservation_id=nullable(ID),
    payment_id=nullable(ID),
    failure_code=nullable(TEXT),
    created_at=STAMP,
    updated_at=STAMP,
)
STOCK = obj(
    sku=SKU, on_hand=INT, reserved=INT, available=INT, stock_version=VERSION, changed_at=STAMP
)
PRODUCT = obj(
    product_id=SKU,
    sku=SKU,
    title=TEXT,
    category_path_normalized=TEXTS,
    attributes={"type": "object", "additionalProperties": TEXTS},
    quality_flags=TEXTS,
    dataset_revision=TEXT,
    source_pid=TEXT,
    source_observation_id=TEXT,
    source_crawled_at=STAMP,
    currency=INR,
    currency_source={"const": "project_assumption"},
    catalog_version=VERSION,
    active=BOOL,
    description=nullable(TEXT),
    category=nullable(TEXT),
    brand=nullable(TEXT),
    brand_normalized=nullable(TEXT),
    size=nullable(TEXT),
    size_kind=nullable(TEXT),
    colour=nullable(TEXT),
    material=nullable(TEXT),
    seller_id=nullable(TEXT),
    price_minor=nullable(PRICE),
    retail_price_minor=nullable(PRICE),
    rating=nullable(TEXT),
    inactive_reason=nullable(TEXT),
)
FACETS = obj(
    dataset_revision=TEXT,
    dictionary_version=TEXT,
    roots=array(obj(id=TEXT, label=TEXT)),
    path_prefixes=array(TEXTS),
    brands=array(obj(key=TEXT, label=TEXT)),
    colours=TEXTS,
    materials=TEXTS,
    allowed_apparel_sizes=TEXTS,
    observed_apparel_sizes=TEXTS,
    coverage_by_category=ANY_OBJECT,
)
FILE = obj(
    path=TEXT,
    sha256={"type": "string", "pattern": "^[0-9a-f]{64}$"},
    byte_size=INT,
    row_count=INT,
    schema_name=TEXT,
    schema_version=VERSION,
    partition_values=ANY_OBJECT,
    min_event_time=nullable(STAMP),
    max_event_time=nullable(STAMP),
)
MANIFEST = obj(
    namespace=TEXT,
    dataset={"enum": ["silver", "gold"]},
    generation=VERSION,
    parent_generation=nullable(VERSION),
    files=array(FILE),
    source_ranges=array(ANY_OBJECT),
    transform_version=TEXT,
    code_commit=TEXT,
    input_manifest_ids=TEXTS,
    created_at=STAMP,
)

RESPONSES = {
    "search": SEARCH,
    "product": obj(product=PRODUCT, stock=nullable(STOCK)),
    "facets": FACETS,
    "quote": QUOTE,
    "quote_lookup": QUOTE,
    "price": PRODUCT,
    "order_create": ACCEPTED,
    "order_status": ORDER,
    "order_events": ORDER,
    "active_manifest": MANIFEST,
    "gold": obj(generation=VERSION, rows=array(ANY_OBJECT), queried_at=STAMP),
    # Exact pagination wrappers are absent from the common spec. Explicit test-only assumptions.
    "receipts": obj(receipts=array(ANY_OBJECT), next_cursor=nullable(TEXT)),
    "quarantine": obj(records=array(ANY_OBJECT), next_cursor=nullable(TEXT)),
    "replay_create": obj(replay_id=ID, status_url=TEXT),
    "replay_status": obj(
        status=TEXT,
        counts=ANY_OBJECT,
        reconciliation=nullable(ANY_OBJECT),
        error=nullable(ANY_OBJECT),
    ),
}
REQUESTS = {
    "search": SEARCH_REQUEST,
    "quote": QUOTE_REQUEST,
    "order_create": CREATE_ORDER,
    "price": obj(price_minor=PRICE, expected_catalog_version=VERSION),
    "replay_create": obj(source_manifest_ids=TEXTS, target_namespace=TEXT, transform_version=TEXT),
}


class ProvisionalContracts:
    mode = "stub"

    def validate(self, endpoint, direction, value):
        name = next(name for name, item in ENDPOINTS.items() if item == endpoint)
        schema = (REQUESTS if direction == "request" else RESPONSES)[name]
        OpenAPIContracts(ROOT / "contracts/fixtures/p2").validate_schema(
            "urn:p2:test-only", schema, value
        )


def examples():
    intent = {
        "query_text": "synthetic test listing",
        "category": None,
        "size": None,
        "colour": None,
        "material": None,
        "max_price_minor": 50000,
        "occasion": None,
        "currency": "INR",
        "brand": None,
        "category_path_prefix": None,
    }
    hit = {
        "sku": "FK-P2-SYNTHETIC-001",
        "product_id": "FK-P2-SYNTHETIC-001",
        "title": "Synthetic P2 test listing",
        "category": "clothing",
        "brand": None,
        "size": None,
        "colour": None,
        "material": None,
        "price_minor": 37900,
        "currency": "INR",
        "catalog_version": 1,
        "dataset_revision": "p2-synthetic-not-dataset",
        "quality_flags": ["MISSING_BRAND"],
        "score": 1.0,
        "stock_available": 10,
        "stock_version": 1,
        "stock_updated_at": NOW,
        "stock_applied_at": NOW,
        "retrieval_mode": "lexical",
        "rank": 1,
    }
    search = {
        "search_id": uid(3),
        "hits": [hit],
        "mode": "lexical",
        "candidate_count": 1,
        "eligible_count": 1,
        "returned_count": 1,
        "exhausted": True,
        "embedding_revision": None,
        "timings_ms": {"embedding": 0, "filter": 1, "rank": 1, "total": 2},
        "embedding_calls": 0,
        "served_at": NOW,
    }
    request = {
        "request_id": uid(1),
        "session_id": uid(2),
        "intent": intent,
        "top_k": 5,
        "mode": "lexical",
    }
    quote = {
        "quote_id": uid(4),
        "user_id": "p2-user",
        "cart_id": uid(5),
        "cart_version": 1,
        "lines": [
            {
                "sku": hit["sku"],
                "quantity": 1,
                "unit_price_minor": 39900,
                "line_total_minor": 39900,
                "catalog_version": 2,
            }
        ],
        "total_amount_minor": 39900,
        "currency": "INR",
        "created_at": NOW,
        "expires_at": "2026-10-25T10:01:00Z",
    }
    order = {
        "order_id": uid(6),
        "quote_id": quote["quote_id"],
        "user_id": "p2-user",
        "session_id": uid(2),
        "status": "PENDING",
        "order_version": 1,
        "lines": quote["lines"],
        "total_amount_minor": 39900,
        "currency": "INR",
        "reservation_id": None,
        "payment_id": None,
        "failure_code": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    product = {
        "product_id": hit["product_id"],
        "sku": hit["sku"],
        "title": hit["title"],
        "category_path_normalized": ["Clothing"],
        "attributes": {},
        "quality_flags": hit["quality_flags"],
        "dataset_revision": hit["dataset_revision"],
        "source_pid": "P2-SYNTHETIC-001",
        "source_observation_id": "p2-synthetic-observation",
        "source_crawled_at": "2016-01-01T00:00:00Z",
        "currency": "INR",
        "currency_source": "project_assumption",
        "catalog_version": 1,
        "active": True,
        **{
            field: None
            for field in (
                "description",
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
        },
        "category": "clothing",
        "price_minor": 37900,
    }
    pairs = []

    def pair(name, endpoint, request, response):
        pairs.append(
            {
                "name": name,
                "endpoint": endpoint,
                "request": request,
                "response": copy.deepcopy(response),
            }
        )

    pair("fewer-than-five-null-facets", "search", request, search)
    search["hits"], search["eligible_count"], search["returned_count"] = [], 0, 0
    pair("no-results", "search", request, search)
    search["hits"] = [
        {
            **hit,
            "sku": f"FK-P2-SYNTHETIC-{n:03}",
            "product_id": f"FK-P2-SYNTHETIC-{n:03}",
            "rank": n,
        }
        for n in range(1, 6)
    ]
    search.update(candidate_count=5, eligible_count=5, returned_count=5)
    pair("five-hits", "search", request, search)
    pair("product-unknown-stock", "product", None, {"product": product, "stock": None})
    pair(
        "empty-facet-coverage",
        "facets",
        None,
        {
            "dataset_revision": hit["dataset_revision"],
            "dictionary_version": "p2-provisional",
            "roots": [{"id": "clothing", "label": "Clothing"}],
            "path_prefixes": [],
            "brands": [],
            "colours": [],
            "materials": [],
            "allowed_apparel_sizes": [
                "XXS",
                "XS",
                "S",
                "M",
                "L",
                "XL",
                "XXL",
                "XXXL",
                "FREE_SIZE",
                "ONE_SIZE",
            ],
            "observed_apparel_sizes": [],
            "coverage_by_category": {},
        },
    )
    pair(
        "changed-price-authoritative-quote",
        "quote",
        {
            "cart_id": uid(5),
            "cart_version": 1,
            "lines": [{"sku": hit["sku"], "quantity": 1, "display_price_minor": 37900}],
        },
        quote,
    )
    pair("internal-quote", "quote_lookup", None, quote)
    pair("internal-price", "price", {"price_minor": 37900, "expected_catalog_version": 1}, product)
    pair(
        "accepted-pending",
        "order_create",
        {"quote_id": uid(4), "session_id": uid(2), "confirmation_id": uid(7)},
        {"order_id": uid(6), "status": "PENDING", "status_url": "/v1/orders/" + uid(6)},
    )
    for status, version in [
        ("PENDING", 1),
        ("CONFIRMED", 4),
        ("CANCELLED", 5),
        ("MANUAL_REVIEW", 6),
    ]:
        order.update(status=status, order_version=version)
        pair("order-" + status.lower(), "order_status", None, order)
        pair("sse-" + status.lower(), "order_events", None, order)
    pair(
        "active-generation",
        "active_manifest",
        None,
        {
            "namespace": "bench-p2",
            "dataset": "gold",
            "generation": 1,
            "parent_generation": None,
            "files": [],
            "source_ranges": [],
            "transform_version": "p2-example",
            "code_commit": "example-not-measured",
            "input_manifest_ids": [],
            "created_at": NOW,
        },
    )
    pair("gold-empty", "gold", None, {"generation": 1, "rows": [], "queried_at": NOW})
    pair(
        "receipts-missing-timing",
        "receipts",
        None,
        {
            "receipts": [
                {
                    "namespace": "bench-p2",
                    "source": {
                        "topic": "bench-p2.conversation-events.v1",
                        "partition": 0,
                        "offset": 0,
                        "raw_locator": "bronze/p2-synthetic.jsonl#1",
                    },
                    "raw_sha256": "0" * 64,
                    "event_id": uid(8),
                    "disposition": "new_valid",
                    "reason_code": None,
                    "ingested_at": NOW,
                    "bronze_durable_at": NOW,
                    "silver_committed_observed_at": None,
                    "gold_visible_at": None,
                    "visibility_generation": None,
                    "timing_validity": "missing",
                }
            ],
            "next_cursor": None,
        },
    )
    pair("quarantine-empty", "quarantine", None, {"records": [], "next_cursor": None})
    pair(
        "replay-accepted",
        "replay_create",
        {
            "source_manifest_ids": ["p2-example"],
            "target_namespace": "replay-p2",
            "transform_version": "p2-example",
        },
        {"replay_id": uid(9), "status_url": "/internal/v1/analytics/replays/" + uid(9)},
    )
    pair(
        "replay-pending",
        "replay_status",
        None,
        {"status": "PENDING", "counts": {}, "reconciliation": None, "error": None},
    )
    return {"provisional": True, "synthetic": True, "test_mode": "stub", "pairs": pairs}


if __name__ == "__main__":
    path = ROOT / "contracts/fixtures/p2/pairs.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(examples(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
