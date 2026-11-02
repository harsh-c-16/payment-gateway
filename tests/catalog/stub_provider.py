"""Explicit test double for catalogue consumers. Never a real provider and holds no catalogue.

    uvicorn --factory tests.catalog.stub_provider:create_stub --port 8002

Every response validates against contracts/http/catalog.yaml. Magic values select each path:
SKU FK-STUB-OK succeeds, FK-STUB-INACTIVE is not sellable, FK-STUB-SLOW exceeds the 2-second
timeout, FK-STUB-DOWN returns 503. Quote ID ending 0002 is expired, ending 0003 returns 503, and
one held by another user returns 403. A search for "empty" has no hits.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

STUB_USER = "stub-user"
DATASET = "stub-not-a-dataset"
OK_QUOTE = "00000000-0000-4000-8000-000000000001"
EXPIRED_QUOTE = "00000000-0000-4000-8000-000000000002"
FAILING_QUOTE = "00000000-0000-4000-8000-000000000003"
OTHER_USER_QUOTE = "00000000-0000-4000-8000-000000000004"
FACETS = {
    "dataset_revision": DATASET,
    "dictionary_version": "stub",
    "roots": [{"id": "clothing", "label": "Clothing"}],
    "path_prefixes": [["Clothing"]],
    "brands": [{"key": "acme", "label": "Acme"}],
    "colours": ["blue"],
    "materials": ["cotton"],
    "allowed_apparel_sizes": ["S", "M", "L"],
    "observed_apparel_sizes": ["M"],
    "coverage_by_category": {"clothing": {"canonical": 1, "active": 1}},
}


def stamp(moment=None):
    return (moment or datetime.now(UTC)).isoformat().replace("+00:00", "Z")


def error(status, code, message):
    return JSONResponse(
        {
            "error": {
                "code": code,
                "message": message,
                "retryable": status in {429, 503},
                "details": {},
            },
            "correlation_id": str(uuid4()),
        },
        status_code=status,
    )


def quote_document(quote_id, *, user=STUB_USER, expired=False):
    now = datetime.now(UTC)
    created = now - timedelta(hours=1) if expired else now
    return {
        "quote_id": quote_id,
        "user_id": user,
        "cart_id": "00000000-0000-4000-8000-0000000000aa",
        "cart_version": 1,
        "lines": [
            {
                "sku": "FK-STUB-OK",
                "quantity": 2,
                "unit_price_minor": 219900,
                "line_total_minor": 439800,
                "catalog_version": 1,
            }
        ],
        "total_amount_minor": 439800,
        "currency": "INR",
        "created_at": stamp(created),
        "expires_at": stamp(created + timedelta(seconds=60)),
    }


def hit():
    return {
        "sku": "FK-STUB-OK",
        "product_id": "FK-STUB-OK",
        "title": "Stub listing",
        "category": "clothing",
        "brand": "Acme",
        "size": "M",
        "colour": "blue",
        "material": "cotton",
        "price_minor": 219900,
        "currency": "INR",
        "catalog_version": 1,
        "dataset_revision": DATASET,
        "quality_flags": [],
        "score": 1.0,
        "stock_available": 3,
        "stock_version": 1,
        "stock_updated_at": stamp(),
        "stock_applied_at": stamp(),
        "retrieval_mode": "lexical",
        "rank": 1,
    }


def create_stub():
    app = FastAPI(title="Catalog test stub")

    @app.post("/v1/search")
    async def search(request: Request):
        body = await request.json()
        hits = [] if body["intent"]["query_text"] == "empty" else [hit()]
        return {
            "search_id": str(uuid4()),
            "hits": hits,
            "mode": "lexical",
            "candidate_count": len(hits),
            "eligible_count": len(hits),
            "returned_count": len(hits),
            "exhausted": True,
            "embedding_revision": None,
            "timings_ms": {"embedding": 0, "filter": 0, "rank": 0, "total": 0},
            "embedding_calls": 0,
            "served_at": stamp(),
        }

    @app.get("/v1/catalog/facets")
    async def facets():
        return FACETS

    @app.post("/v1/quotes", status_code=201)
    async def create_quote(request: Request):
        body = await request.json()
        skus = [line["sku"] for line in body["lines"]]
        if "FK-STUB-INACTIVE" in skus:
            return error(409, "PRODUCT_NOT_SELLABLE", "Listing cannot be quoted.")
        if "FK-STUB-DOWN" in skus:
            return error(503, "STORAGE_UNAVAILABLE", "Catalogue storage is unavailable.")
        if "FK-STUB-SLOW" in skus:
            await asyncio.sleep(3)
        return quote_document(OK_QUOTE)

    @app.get("/internal/v1/quotes/{quote_id}")
    async def lookup(quote_id: str, x_user_id: str = Header(default=STUB_USER)):
        if quote_id == FAILING_QUOTE:
            return error(503, "STORAGE_UNAVAILABLE", "Catalogue storage is unavailable.")
        if quote_id == OTHER_USER_QUOTE:
            return error(403, "FORBIDDEN", "Quote belongs to another user.")
        if quote_id not in {OK_QUOTE, EXPIRED_QUOTE}:
            return error(404, "NOT_FOUND", "Quote not found.")
        return quote_document(quote_id, user=x_user_id, expired=quote_id == EXPIRED_QUOTE)

    @app.get("/health/ready")
    async def ready():
        return {"status": "stub", "real_provider": False}

    return app
