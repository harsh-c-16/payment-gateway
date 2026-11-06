"""M3 Inventory HTTP adapter with expiry worker. Owner: Aditya Gaurav."""

import logging
import os
import threading
import time
from time import monotonic
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from services.inventory import reservation
from services.inventory.database import Database
from services.inventory.errors import ServiceError
from services.inventory.events import InventoryEvents
from shared.contracts.common import (
    ErrorCode,
    ErrorResponse,
    Identifier,
    RequestContext,
    Sku,
    UUIDText,
)
from shared.contracts.transactions import ReserveRequest
from shared.telemetry.context import bind_context, log_operation
from shared.telemetry.metrics import Telemetry

LOGGER = logging.getLogger("inventory")
ROUTES = (
    "/internal/v1/reservations",
    "/internal/v1/reservations/by-order/{order_id}",
    "/internal/v1/reservations/by-order/{order_id}/commit",
    "/internal/v1/reservations/by-order/{order_id}/release",
    "/internal/v1/inventory/{sku}",
    "/health/live",
    "/health/ready",
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


Context = Annotated[RequestContext, Depends(request_context)]


EXPIRY_INTERVAL_SECONDS = 0.25


def create_app(*, db=None, events=None):
    db = db or Database(
        os.environ.get("INVENTORY_DATABASE_URL", ""),
        max_connections=int(os.environ.get("INVENTORY_MAX_CONNECTIONS", "10")),
        reuse_connections=os.environ.get("INVENTORY_REUSE_CONNECTIONS", "false") == "true",
    )
    events = events or InventoryEvents()
    errors = {
        status: {"model": ErrorResponse, "description": "Common error object"}
        for status in (400, 401, 404, 409, 422, 503)
    }
    app = FastAPI(title="Inventory service", version="1.0.0", responses=errors)
    telemetry = Telemetry(
        label_values={
            "service": {"inventory"},
            "route": set(ROUTES),
            "status": {str(code) for code in range(100, 600)},
        }
    )

    expiry_stop = threading.Event()

    @app.middleware("http")
    async def observe(request, call_next):
        started = monotonic()
        response = await call_next(request)
        elapsed = monotonic() - started
        route = getattr(request.scope.get("route"), "path", "unmatched")
        route = route if route in ROUTES else "unmatched"
        telemetry.record(
            "requests_total", 1, service="inventory", route=route, status=str(response.status_code)
        )
        telemetry.record("request_duration_seconds", elapsed, service="inventory", route=route)
        context = getattr(request.state, "context", None)
        if context is not None:
            with bind_context(context, "inventory"):
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

    @app.post("/internal/v1/reservations", status_code=201)
    def create_reservation(body: ReserveRequest, context: Context):
        return reservation.reserve(db, events, context.namespace, body, context)

    @app.get("/internal/v1/reservations/by-order/{order_id}")
    def get_reservation(order_id: UUIDText, context: Context):
        return reservation.get_reservation_by_order(db, context.namespace, order_id)

    @app.post("/internal/v1/reservations/by-order/{order_id}/commit")
    def commit(order_id: UUIDText, body: dict, context: Context):
        rid = body.get("reservation_id")
        if not rid:
            raise ServiceError(400, ErrorCode.BAD_REQUEST, "reservation_id is required.")
        return reservation.commit_reservation(db, events, context.namespace, order_id, rid, context)

    @app.post("/internal/v1/reservations/by-order/{order_id}/release")
    def release(order_id: UUIDText, body: dict, context: Context):
        reason = body.get("reason")
        if not reason:
            raise ServiceError(400, ErrorCode.BAD_REQUEST, "reason is required.")
        return reservation.release_reservation(
            db, events, context.namespace, order_id, reason, context
        )

    @app.get("/internal/v1/inventory/{sku}")
    def get_stock(sku: Sku, context: Context):
        return reservation.get_stock(db, context.namespace, sku)

    # ── Expiry worker ──

    @app.on_event("startup")
    def start_expiry_worker():
        def _loop():
            while not expiry_stop.is_set():
                try:
                    context = RequestContext(
                        namespace=os.environ.get("DEFAULT_NAMESPACE", "dev"),
                        run_id="expiry-worker",
                        user_id="system",
                        correlation_id=str(uuid4()),
                        request_id=str(uuid4()),
                        session_id=None,
                    )
                    expired = reservation.expire_reservations(db, events, context)
                    if expired > 0:
                        LOGGER.info("expired %d reservations", expired)
                except Exception:
                    LOGGER.exception("expiry worker error")
                time.sleep(EXPIRY_INTERVAL_SECONDS)

        t = threading.Thread(target=_loop, name="expiry-worker", daemon=True)
        t.start()

    @app.on_event("shutdown")
    def stop_expiry_worker():
        expiry_stop.set()

    # ── Audit exports (read-only, used by oracle/benchmark) ──

    @app.get("/internal/v1/audit/stock")
    def audit_stock(context: Context, limit: int = Query(default=1000, ge=1, le=10000)):
        """Read-only stock snapshot for oracle reconciliation."""
        with db.transaction() as tx:
            rows = tx.execute(
                """
                SELECT sku, on_hand, reserved, (on_hand - reserved) AS available,
                       stock_version, changed_at
                FROM inventory WHERE namespace = %s
                ORDER BY sku LIMIT %s
                """,
                (context.namespace, limit),
            ).fetchall()
        return {"items": rows, "count": len(rows)}

    @app.get("/internal/v1/audit/reservations")
    def audit_reservations(context: Context, limit: int = Query(default=1000, ge=1, le=10000)):
        """Read-only reservation snapshot for oracle reconciliation."""
        with db.transaction() as tx:
            rows = tx.execute(
                """
                SELECT r.reservation_id, r.order_id, r.state, r.expires_at, r.updated_at,
                       json_agg(json_build_object('sku', ri.sku, 'quantity', ri.quantity)) AS items
                FROM reservations r
                LEFT JOIN reservation_items ri ON r.namespace = ri.namespace AND r.reservation_id = ri.reservation_id
                WHERE r.namespace = %s
                GROUP BY r.reservation_id, r.order_id, r.state, r.expires_at, r.updated_at
                ORDER BY r.updated_at DESC LIMIT %s
                """,
                (context.namespace, limit),
            ).fetchall()
        return {"items": rows, "count": len(rows)}

    @app.get("/health/live")
    def live() -> dict:
        return {"status": "live"}

    @app.get("/health/ready")
    def ready() -> dict:
        events.ready()
        return {"status": "ready"}

    return app
