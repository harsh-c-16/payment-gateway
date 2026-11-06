"""M3 Payments HTTP adapter. Owner: Aditya Gaurav."""

import logging
import os
from time import monotonic
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import TypeAdapter, ValidationError

from services.payments import authorize
from services.payments.database import Database
from services.payments.errors import ServiceError
from services.payments.events import PaymentEvents
from shared.contracts.common import (
    ErrorCode,
    ErrorResponse,
    Identifier,
    RequestContext,
    UUIDText,
)
from shared.contracts.transactions import AuthorizePaymentRequest
from shared.telemetry.context import bind_context, log_operation
from shared.telemetry.metrics import Telemetry

LOGGER = logging.getLogger("payments")
ROUTES = (
    "/internal/v1/payments/authorize",
    "/internal/v1/payments/by-order/{order_id}",
    "/internal/v1/payments/by-order/{order_id}/reverse",
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


def create_app(*, db=None, events=None):
    db = db or Database(
        os.environ.get("PAYMENTS_DATABASE_URL", ""),
        max_connections=int(os.environ.get("PAYMENTS_MAX_CONNECTIONS", "10")),
        reuse_connections=os.environ.get("PAYMENTS_REUSE_CONNECTIONS", "false") == "true",
    )
    events = events or PaymentEvents()
    errors = {
        status: {"model": ErrorResponse, "description": "Common error object"}
        for status in (400, 401, 404, 409, 422, 503)
    }
    app = FastAPI(title="Payments service", version="1.0.0", responses=errors)
    telemetry = Telemetry(
        label_values={
            "service": {"payments"},
            "route": set(ROUTES),
            "status": {str(code) for code in range(100, 600)},
        }
    )

    @app.middleware("http")
    async def observe(request, call_next):
        started = monotonic()
        response = await call_next(request)
        elapsed = monotonic() - started
        route = getattr(request.scope.get("route"), "path", "unmatched")
        route = route if route in ROUTES else "unmatched"
        telemetry.record(
            "requests_total", 1, service="payments", route=route, status=str(response.status_code)
        )
        telemetry.record("request_duration_seconds", elapsed, service="payments", route=route)
        context = getattr(request.state, "context", None)
        if context is not None:
            with bind_context(context, "payments"):
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

    @app.post("/internal/v1/payments/authorize", status_code=202)
    def authorize_payment(body: AuthorizePaymentRequest, context: Context):
        return authorize.authorize(db, events, context.namespace, body, context)

    @app.get("/internal/v1/payments/by-order/{order_id}")
    def get_payments(order_id: UUIDText, context: Context):
        return authorize.get_payment_order(db, context.namespace, order_id)

    @app.post("/internal/v1/payments/by-order/{order_id}/reverse")
    def reverse(order_id: UUIDText, body: dict, context: Context):
        reason = body.get("reason")
        if not reason:
            raise ServiceError(400, ErrorCode.BAD_REQUEST, "reason is required.")
        return authorize.reverse_payments(db, events, context.namespace, order_id, reason, context)

    # ── Audit exports (read-only, used by oracle/benchmark) ──

    @app.get("/internal/v1/audit/payments")
    def audit_payments(context: Context):
        """Read-only payment snapshot for oracle reconciliation."""
        with db.transaction() as tx:
            rows = tx.execute(
                """
                SELECT po.order_id, po.quiesced,
                       json_agg(json_build_object(
                           'payment_id', pa.payment_id, 'attempt_number', pa.attempt_number,
                           'status', pa.status, 'amount_minor', pa.amount_minor,
                           'currency', pa.currency, 'failure_code', pa.failure_code,
                           'debit_id', pa.debit_id, 'reversal_id', pa.reversal_id
                       ) ORDER BY pa.attempt_number) AS attempts
                FROM payment_orders po
                LEFT JOIN payment_attempts pa ON po.namespace = pa.namespace AND po.order_id = pa.order_id
                WHERE po.namespace = %s
                GROUP BY po.order_id, po.quiesced
                ORDER BY po.order_id
                """,
                (context.namespace,),
            ).fetchall()
        return {"items": rows, "count": len(rows)}

    @app.get("/internal/v1/audit/ledger")
    def audit_ledger(context: Context):
        """Read-only ledger entries for reconciliation."""
        with db.transaction() as tx:
            rows = tx.execute(
                """
                SELECT le.entry_id, le.payment_id, le.kind, le.amount_minor, le.currency, le.created_at,
                       pa.order_id
                FROM ledger_entries le
                JOIN payment_attempts pa ON le.namespace = pa.namespace AND le.payment_id = pa.payment_id
                WHERE le.namespace = %s
                ORDER BY le.created_at
                """,
                (context.namespace,),
            ).fetchall()
        net = sum(r["amount_minor"] if r["kind"] == "DEBIT" else -r["amount_minor"] for r in rows)
        return {"items": rows, "count": len(rows), "net_debit_minor": max(0, net)}

    @app.get("/health/live")
    def live() -> dict:
        return {"status": "live"}

    @app.get("/health/ready")
    def ready() -> dict:
        events.ready()
        return {"status": "ready"}

    return app
