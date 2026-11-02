"""M2 HTTP adapter over search, products, quotes and internal price/quote commands."""

import hashlib
import hmac
import logging
import os
from time import monotonic
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import TypeAdapter, ValidationError

from pipelines.catalog.migrate import MIGRATIONS
from services.catalog import products, search
from services.catalog.database import Database
from services.catalog.errors import ServiceError
from services.catalog.events import SharedEvents
from shared.contracts.catalog import (
    FacetDictionary,
    PriceUpdateRequest,
    Product,
    ProductResponse,
    Quote,
    QuoteRequest,
    SearchRequest,
    SearchResponse,
)
from shared.contracts.common import (
    ErrorCode,
    ErrorResponse,
    IdempotencyKey,
    Identifier,
    RequestContext,
    Sku,
    UUIDText,
)
from shared.telemetry.context import bind_context, log_operation
from shared.telemetry.metrics import Telemetry

LOGGER = logging.getLogger("catalog")
ROUTES = (
    "/v1/search",
    "/v1/catalog/facets",
    "/v1/products/{sku}",
    "/v1/quotes",
    "/internal/v1/quotes/{quote_id}",
    "/internal/v1/catalog/{sku}/price",
    "/internal/v1/projection/receipts",
    "/health/live",
    "/health/ready",
    "/metrics",
    "unmatched",
)


def correlation(request):
    value = request.headers.get("X-Correlation-ID")
    try:
        return TypeAdapter(Identifier).validate_python(value)
    except ValidationError:
        return str(uuid4())


def request_context(request: Request):
    if not request.headers.get("X-User-ID"):
        raise ServiceError(401, ErrorCode.UNAUTHORIZED, "X-User-ID is required.")
    try:
        context = RequestContext(
            namespace=request.headers.get("X-Namespace"),
            run_id=request.headers.get("X-Run-ID"),
            user_id=request.headers["X-User-ID"],
            correlation_id=request.headers.get("X-Correlation-ID"),
            request_id=request.headers.get("X-Request-ID"),
            session_id=request.headers.get("X-Session-ID"),
            trace_id=request.headers.get("X-Trace-ID"),
        )
    except ValidationError as error:
        raise ServiceError(422, ErrorCode.VALIDATION_ERROR, "Invalid request context.") from error
    request.state.context = context
    return context


def mutation_key(request: Request):
    try:
        return TypeAdapter(IdempotencyKey).validate_python(request.headers.get("Idempotency-Key"))
    except ValidationError as error:
        raise ServiceError(
            400, ErrorCode.BAD_REQUEST, "Valid Idempotency-Key is required."
        ) from error


def internal_caller(request: Request):
    token = os.environ.get("INTERNAL_API_TOKEN", "")
    supplied = request.headers.get("Authorization", "")
    if not token or not hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
        raise ServiceError(401, ErrorCode.UNAUTHORIZED, "Valid service token is required.")


Context = Annotated[RequestContext, Depends(request_context)]
Key = Annotated[str, Depends(mutation_key)]
Internal = Depends(internal_caller)
ValidSku = Annotated[Sku, "catalogue SKU"]


def create_app(*, db=None, events=None):
    db = db or Database(os.environ.get("CATALOG_DATABASE_URL", ""))
    events = events or SharedEvents()
    ttl = int(os.environ.get("QUOTE_TTL_SECONDS", "60"))
    errors = {
        status: {"model": ErrorResponse, "description": "Common error object"}
        for status in (400, 401, 403, 404, 409, 422, 429, 503)
    }
    app = FastAPI(title="Catalog service", version="1.0.0", responses=errors)
    telemetry = Telemetry(
        label_values={
            "service": {"catalog"},
            "route": set(ROUTES),
            "status": {str(code) for code in range(100, 600)},
        }
    )
    app.state.telemetry = telemetry

    @app.middleware("http")
    async def observe(request, call_next):
        started = monotonic()
        response = await call_next(request)
        elapsed = monotonic() - started
        route = getattr(request.scope.get("route"), "path", "unmatched")
        route = route if route in ROUTES else "unmatched"
        telemetry.record(
            "requests_total", 1, service="catalog", route=route, status=str(response.status_code)
        )
        telemetry.record("request_duration_seconds", elapsed, service="catalog", route=route)
        context = getattr(request.state, "context", None)
        if context is not None:
            with bind_context(context, "catalog"):
                log_operation(
                    LOGGER, request.method + " " + route, str(response.status_code), elapsed
                )
        return response

    @app.exception_handler(ServiceError)
    async def service_error(request, error):
        return JSONResponse(error.response(correlation(request)), status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        fields = sorted({".".join(map(str, item["loc"])) for item in error.errors()})
        failure = ServiceError(
            422,
            ErrorCode.VALIDATION_ERROR,
            "Request failed validation.",
            details={"fields": fields},
        )
        return JSONResponse(failure.response(correlation(request)), status_code=422)

    @app.post("/v1/search", response_model=SearchResponse)
    def post_search(body: SearchRequest, context: Context):
        return search.search_catalog(db, events, body, context)

    @app.get("/v1/catalog/facets", response_model=FacetDictionary)
    def get_facets(context: Context, dataset_revision: Annotated[str | None, Query()] = None):
        return products.get_facets(db, context.namespace, dataset_revision)

    @app.get("/v1/products/{sku}", response_model=ProductResponse)
    def get_product(sku: ValidSku, context: Context):
        return products.get_product(db, context.namespace, sku)

    @app.post("/v1/quotes", response_model=Quote, status_code=201)
    def post_quote(body: QuoteRequest, context: Context, key: Key):
        return products.create_quote(db, body, context, key, ttl_seconds=ttl)

    @app.get("/internal/v1/quotes/{quote_id}", response_model=Quote, dependencies=[Internal])
    def get_quote(quote_id: UUIDText, context: Context):
        return products.get_quote(db, context.namespace, quote_id, context.user_id)

    @app.post("/internal/v1/catalog/{sku}/price", response_model=Product, dependencies=[Internal])
    def post_price(sku: ValidSku, body: PriceUpdateRequest, context: Context, key: Key):
        return products.update_price(db, events, sku, body, context, key)

    @app.get("/internal/v1/projection/receipts", dependencies=[Internal])
    def get_receipts(
        context: Context,
        after: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=1000)] = 1000,
    ) -> dict:
        """Version and timing receipts for the independent freshness oracle."""
        with db.transaction() as tx:
            rows = tx.execute(
                'SELECT sequence,topic,partition,"offset",event_id::text,sku,outcome,'
                "previous_version,current_version,version_gap,produced_at,observed_commit_at "
                "FROM projection_receipts WHERE namespace=%s AND sequence>%s "
                "ORDER BY sequence LIMIT %s",
                (context.namespace, after, limit),
            ).fetchall()
        return {"receipts": rows, "next_cursor": rows[-1]["sequence"] if rows else None}

    @app.get("/health/live")
    def live() -> dict:
        return {"status": "live"}

    @app.get("/health/ready")
    def ready() -> dict:
        events.ready()
        with db.transaction() as tx:
            applied = {
                row["version"]: row["sha256"]
                for row in tx.execute(
                    "SELECT version,sha256 FROM catalog_schema_migrations"
                ).fetchall()
            }
        for version, path in enumerate(MIGRATIONS, 1):
            digest = hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            if applied.get(version) != digest:
                raise ServiceError(503, ErrorCode.STORAGE_UNAVAILABLE, "Schema is not migrated.")
        return {"status": "ready"}

    @app.get("/metrics")
    def metrics():
        return Response(telemetry.exposition(), media_type="text/plain; version=0.0.4")

    return app
