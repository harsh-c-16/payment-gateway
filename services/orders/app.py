"""M3 Orders HTTP adapter with SSE and NOTIFY-based wake-up. Owner: Aditya Gaurav."""

import asyncio
import hmac
import json
import logging
import os
import threading
import time
from time import monotonic
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError

from services.orders import commands, saga
from services.orders.database import Database
from services.orders.errors import ServiceError, not_found
from services.orders.events import OrderEvents
from shared.contracts.common import (
    ErrorCode,
    ErrorResponse,
    Identifier,
    RequestContext,
    UUIDText,
)
from shared.contracts.transactions import CreateOrderRequest
from shared.telemetry.context import bind_context, log_operation
from shared.telemetry.metrics import Telemetry

LOGGER = logging.getLogger("orders")
ROUTES = (
    "/v1/orders",
    "/v1/orders/{order_id}",
    "/v1/orders/{order_id}/events",
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


def internal_caller(request: Request):
    """Common spec §2: /internal/v1 needs the environment service token; fail closed."""
    token = os.environ.get("INTERNAL_API_TOKEN", "")
    supplied = request.headers.get("Authorization", "")
    if not token or not hmac.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
        raise ServiceError(401, ErrorCode.UNAUTHORIZED, "Valid service token is required.")


Internal = Depends(internal_caller)


class FaultBarrierRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    barrier_name: Annotated[str, Field(pattern=r"^[a-z0-9_.-]{1,64}$")]
    enabled: Annotated[bool, Field(strict=True)]
    action: Literal["CRASH", "DELAY", "SKIP"] = "CRASH"
    delay_ms: Annotated[int, Field(strict=True, ge=0, le=60_000)] = 0


TERMINAL_STATUSES = frozenset({"CONFIRMED", "CANCELLED", "MANUAL_REVIEW"})


def create_app(*, db=None, events=None):
    db = db or Database(
        os.environ.get("ORDERS_DATABASE_URL", ""),
        max_connections=int(os.environ.get("ORDERS_MAX_CONNECTIONS", "10")),
        reuse_connections=os.environ.get("ORDERS_REUSE_CONNECTIONS", "false") == "true",
    )
    events = events or OrderEvents()
    catalog_url = os.environ.get("CATALOG_URL", "http://catalog:8002")
    inventory_url = os.environ.get("INVENTORY_URL", "http://inventory:8004")
    payments_url = os.environ.get("PAYMENTS_URL", "http://payments:8005")
    internal_token = os.environ.get("INTERNAL_API_TOKEN", "")

    errors = {
        status: {"model": ErrorResponse, "description": "Common error object"}
        for status in (400, 401, 403, 404, 409, 422, 503)
    }
    app = FastAPI(title="Orders service", version="1.0.0", responses=errors)
    telemetry = Telemetry(
        label_values={
            "service": {"orders"},
            "route": set(ROUTES),
            "status": {str(code) for code in range(100, 600)},
        }
    )

    saga_stop = threading.Event()

    @app.on_event("startup")
    def start_saga_worker():
        def _loop():
            while not saga_stop.is_set():
                try:
                    context = RequestContext(
                        namespace=os.environ.get("DEFAULT_NAMESPACE", "dev"),
                        run_id="saga-worker",
                        user_id="system",
                        correlation_id=str(uuid4()),
                        request_id=str(uuid4()),
                        session_id=None,
                    )
                    processed = saga.run_pending_sagas(
                        db,
                        events,
                        context,
                        inventory_url=inventory_url,
                        payments_url=payments_url,
                        internal_token=internal_token,
                    )
                    if processed == 0:
                        time.sleep(0.1)
                except Exception:
                    LOGGER.exception("saga worker error")
                    time.sleep(1.0)

        t = threading.Thread(target=_loop, name="saga-worker", daemon=True)
        t.start()

    @app.on_event("shutdown")
    def stop_saga_worker():
        saga_stop.set()

    @app.middleware("http")
    async def observe(request, call_next):
        started = monotonic()
        response = await call_next(request)
        elapsed = monotonic() - started
        route = getattr(request.scope.get("route"), "path", "unmatched")
        route = route if route in ROUTES else "unmatched"
        telemetry.record(
            "requests_total", 1, service="orders", route=route, status=str(response.status_code)
        )
        telemetry.record("request_duration_seconds", elapsed, service="orders", route=route)
        context = getattr(request.state, "context", None)
        if context is not None:
            with bind_context(context, "orders"):
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

    @app.post("/v1/orders", status_code=202)
    def create_order(body: CreateOrderRequest, context: Context):
        return commands.create_order(
            db,
            events,
            context.namespace,
            body,
            context,
            catalog_url=catalog_url,
            internal_token=internal_token,
        )

    def owned_snapshot(order_id, context):
        # Another principal's order is reported as absent, never disclosed.
        snapshot = commands.get_order_snapshot(db, context.namespace, order_id)
        if snapshot["user_id"] != context.user_id:
            raise not_found("Order")
        return snapshot

    @app.get("/v1/orders/{order_id}")
    def order_status(order_id: UUIDText, context: Context):
        return owned_snapshot(order_id, context)

    @app.get("/v1/orders/{order_id}/events")
    async def order_events(
        order_id: UUIDText,
        context: Context,
        last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    ):
        owned_snapshot(order_id, context)

        async def generate():
            cursor = int(last_event_id) if last_event_id and last_event_id.isdigit() else 0
            deadline = monotonic() + 30.0
            while monotonic() < deadline:
                try:
                    snapshot = commands.get_order_snapshot(db, context.namespace, order_id)
                except ServiceError:
                    return
                version = snapshot["order_version"]
                if version > cursor or (cursor == 0 and version >= 1):
                    data = json.dumps(snapshot, default=str, ensure_ascii=False)
                    yield f"id:{version}\nevent:order\ndata:{data}\n\n"
                    cursor = version
                    if snapshot["status"] in TERMINAL_STATUSES:
                        return
                await asyncio.sleep(0.25)

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── Audit exports (read-only, used by oracle/benchmark) ──

    @app.get("/internal/v1/audit/orders", dependencies=[Internal])
    def audit_orders(context: Context, limit: int = Query(default=1000, ge=1, le=10000)):
        """Read-only order snapshot for oracle reconciliation."""
        with db.transaction() as tx:
            rows = tx.execute(
                """
                SELECT o.order_id, o.quote_id, o.user_id, o.session_id, o.status,
                       o.order_version, o.total_amount_minor, o.currency,
                       o.reservation_id, o.payment_id, o.failure_code,
                       o.created_at, o.updated_at
                FROM orders o WHERE o.namespace = %s
                ORDER BY o.created_at DESC LIMIT %s
                """,
                (context.namespace, limit),
            ).fetchall()
        return {"items": rows, "count": len(rows)}

    @app.get("/internal/v1/audit/saga-jobs", dependencies=[Internal])
    def audit_saga_jobs(context: Context, limit: int = Query(default=1000, ge=1, le=10000)):
        """Read-only saga job snapshot for recovery inspection."""
        with db.transaction() as tx:
            rows = tx.execute(
                """
                SELECT sj.order_id, sj.planned_step, sj.attempt, sj.operation_key,
                       sj.next_attempt_at, sj.last_error, sj.updated_at
                FROM saga_jobs sj WHERE sj.namespace = %s
                ORDER BY sj.updated_at DESC LIMIT %s
                """,
                (context.namespace, limit),
            ).fetchall()
        return {"items": rows, "count": len(rows)}

    # ── Fault barrier management (benchmark mode only) ──

    @app.post("/internal/v1/fault-barriers", dependencies=[Internal])
    def set_fault_barrier(body: FaultBarrierRequest, context: Context):
        """Set or clear a fault barrier in an explicitly enabled, isolated benchmark run."""
        if not saga.fault_injection_allowed(context.namespace):
            raise ServiceError(
                403,
                ErrorCode.FORBIDDEN,
                "Fault barriers need BENCHMARK_MODE=true, FAULT_INJECTION_ENABLED=true "
                "and a bench- namespace.",
            )
        name, enabled, action, delay_ms = (
            body.barrier_name,
            body.enabled,
            body.action,
            body.delay_ms,
        )
        with db.transaction() as tx:
            tx.execute(
                """
                INSERT INTO fault_barriers (namespace, barrier_name, enabled, action, delay_ms)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (namespace, barrier_name) DO UPDATE
                SET enabled = EXCLUDED.enabled, action = EXCLUDED.action, delay_ms = EXCLUDED.delay_ms
                """,
                (context.namespace, name, enabled, action, delay_ms),
            )
        return {"barrier_name": name, "enabled": enabled, "action": action}

    @app.get("/health/live")
    def live() -> dict:
        return {"status": "live"}

    @app.get("/health/ready")
    def ready() -> dict:
        events.ready()
        return {"status": "ready"}

    return app
