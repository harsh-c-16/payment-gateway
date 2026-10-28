"""M1 HTTP adapter with fixed workflow and explicit provider-mode boundaries."""

import logging
import os
from time import monotonic
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import TypeAdapter, ValidationError

from shared.contracts.common import (
    ErrorCode,
    IdempotencyKey,
    Identifier,
    RequestContext,
    Sku,
    UUIDText,
)
from shared.contracts.conversation import (
    CartQuoteRequest,
    CartSnapshot,
    CartUpdateRequest,
    CheckoutRequest,
    SessionCreated,
    TurnRequest,
    TurnResponse,
)
from shared.telemetry.context import bind_context, log_operation
from shared.telemetry.metrics import Telemetry

from .database import Database
from .errors import ServiceError
from .gateway import Gateway
from .provider_contracts import ContractUnavailable
from .state import ConversationState
from .workflow import FixedWorkflow

LOGGER = logging.getLogger("conversation")
ROUTES = (
    "/v1/sessions",
    "/v1/sessions/{session_id}/turns",
    "/v1/carts/{cart_id}",
    "/v1/carts/{cart_id}/items/{sku}",
    "/v1/carts/{cart_id}/quote",
    "/v1/carts/{cart_id}/checkout",
    "/health/live",
    "/health/ready",
    "/metrics",
    "unmatched",
)


def correlation(request):
    existing = getattr(request.state, "safe_correlation_id", None)
    if existing is not None:
        return existing
    value = request.headers.get("X-Correlation-ID")
    try:
        result = TypeAdapter(Identifier).validate_python(value)
    except ValidationError:
        result = str(uuid4())
    request.state.safe_correlation_id = result
    return result


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
    except ValidationError as exc:
        raise ServiceError(422, ErrorCode.VALIDATION_ERROR, "Invalid request context.") from exc
    request.state.context = context
    return context


def mutation_key(request: Request):
    try:
        return TypeAdapter(IdempotencyKey).validate_python(request.headers.get("Idempotency-Key"))
    except ValidationError as exc:
        raise ServiceError(
            400, ErrorCode.BAD_REQUEST, "Valid Idempotency-Key is required."
        ) from exc


Context = Annotated[RequestContext, Depends(request_context)]
Key = Annotated[str, Depends(mutation_key)]


def workflow_unavailable():
    raise ServiceError(
        503,
        ErrorCode.DEPENDENCY_UNAVAILABLE,
        "Workflow providers are not configured.",
    )


def create_app(
    *,
    state=None,
    mode="real",
    purpose="service",
    turn_handler=None,
    workflow=None,
    intent_provider=None,
):
    if mode not in {"real", "stub"} or purpose not in {"service", "contract_test"}:
        raise ValueError("explicit real/service or stub/contract_test configuration required")
    if (mode == "stub") != (purpose == "contract_test"):
        raise ValueError("test doubles require explicit stub/contract_test mode")
    state = (
        state
        if state is not None
        else ConversationState(Database(os.environ.get("CONVERSATION_DATABASE_URL", "")))
    )
    if mode == "real" and state.events.mode != "real":
        raise ValueError("real service cannot use test event/outbox implementations")
    if mode == "real" and turn_handler is not None:
        raise ValueError("real turns require the fixed workflow with canonical provider validation")
    assistant_mode = os.environ.get("ASSISTANT_MODE", "fixed")
    allow = os.environ.get("ALLOW_INTENT_LLM", "false").lower()
    if assistant_mode not in {"fixed", "assist"} or allow not in {"true", "false"}:
        raise ValueError("explicit fixed/assist and true/false model policy required")
    allow = allow == "true"
    if assistant_mode == "fixed" and allow:
        raise ValueError("fixed mode requires ALLOW_INTENT_LLM=false")
    if workflow is None and mode == "real":
        from .intent_fallback import OpenAIIntentProvider

        if intent_provider is None and assistant_mode == "assist" and allow:
            intent_provider = OpenAIIntentProvider.from_env()
        workflow = FixedWorkflow(
            state,
            Gateway(
                os.environ.get("CATALOG_BASE_URL", "http://catalog:8002"),
                os.environ.get("ORDERS_BASE_URL", "http://orders:8003"),
            ),
            assistant_mode=assistant_mode,
            allow_intent_llm=allow,
            intent_provider=intent_provider,
        )
    if workflow is not None and (workflow.mode != mode or workflow.state is not state):
        raise ValueError("workflow mode/state must match the service")
    if workflow is not None and (
        workflow.assistant_mode != assistant_mode or workflow.allow_intent_llm != allow
    ):
        raise ValueError("workflow and configured assistant policy differ")
    app = FastAPI(title="Conversation", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.conversation = state
    app.state.execution_mode = mode
    telemetry = Telemetry(
        label_values={
            "service": {"conversation"},
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
            "requests_total",
            1,
            service="conversation",
            route=route,
            status=str(response.status_code),
        )
        telemetry.record("request_duration_seconds", elapsed, service="conversation", route=route)
        context = getattr(request.state, "context", None)
        if context is not None:
            with bind_context(context, "conversation"):
                log_operation(
                    LOGGER,
                    request.method + " " + route,
                    str(response.status_code),
                    elapsed,
                    resource_id=request.path_params.get("cart_id")
                    or request.path_params.get("session_id"),
                )
        response.headers["X-Correlation-ID"] = correlation(request)
        return response

    @app.exception_handler(ServiceError)
    async def service_error(request, exc):
        return JSONResponse(exc.response(correlation(request)), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        error = ServiceError(422, ErrorCode.VALIDATION_ERROR, "Invalid request fields.")
        return JSONResponse(error.response(correlation(request)), status_code=422)

    @app.exception_handler(ValidationError)
    async def local_validation_error(request, exc):
        error = ServiceError(422, ErrorCode.VALIDATION_ERROR, "Invalid request fields.")
        return JSONResponse(error.response(correlation(request)), status_code=422)

    @app.post("/v1/sessions", status_code=201, response_model=SessionCreated)
    async def create_session(request: Request, context: Context, key: Key):
        raw = await request.body()
        if raw.strip():
            try:
                # Only the contract's empty object is accepted; no identity override.
                import json

                body = json.loads(raw)
            except (ValueError, UnicodeError) as exc:
                raise ServiceError(400, ErrorCode.BAD_REQUEST, "Empty body is required.") from exc
            if body != {}:
                raise ServiceError(400, ErrorCode.BAD_REQUEST, "Empty body is required.")
        # This async route reads the body; execute blocking PostgreSQL off the event loop.
        from starlette.concurrency import run_in_threadpool

        return await run_in_threadpool(state.create_session, context, key)

    @app.get("/v1/carts/{cart_id}", response_model=CartSnapshot)
    def get_cart(cart_id: UUIDText, context: Context):
        return state.get_cart(cart_id, context)

    @app.put("/v1/carts/{cart_id}/items/{sku}", response_model=CartSnapshot)
    def update_cart(
        cart_id: UUIDText, sku: Sku, body: CartUpdateRequest, context: Context, key: Key
    ):
        return state.update_cart(cart_id, sku, body, context, key)

    @app.post("/v1/sessions/{session_id}/turns", response_model=TurnResponse)
    def submit_turn(session_id: UUIDText, body: TurnRequest, context: Context, key: Key):
        if workflow is not None:
            return workflow.dispatch_turn(session_id, body, context, key)
        if turn_handler is None:
            workflow_unavailable()
        return state.record_turn(session_id, body, context, key, turn_handler)

    @app.post("/v1/carts/{cart_id}/quote", status_code=201)
    def quote_cart(cart_id: UUIDText, body: CartQuoteRequest, context: Context, key: Key):
        if workflow is None:
            workflow_unavailable()
        return workflow.request_quote(cart_id, body, context, key)

    @app.post("/v1/carts/{cart_id}/checkout", status_code=202)
    def checkout_cart(cart_id: UUIDText, body: CheckoutRequest, context: Context, key: Key):
        if workflow is None:
            workflow_unavailable()
        return workflow.checkout_cart(cart_id, body, context, key)

    @app.get("/health/live")
    def live():
        return {"status": "live"}

    @app.get("/health/ready")
    def ready():
        state.ready()
        if workflow is not None:
            try:
                workflow.ready()
            except ContractUnavailable as exc:
                raise ServiceError(
                    503,
                    ErrorCode.DEPENDENCY_UNAVAILABLE,
                    "Canonical workflow provider contracts unavailable.",
                ) from exc
        return {"status": "ready", "mode": mode}

    @app.get("/metrics")
    def metrics():
        model_metrics = workflow.telemetry.exposition() if workflow is not None else b""
        return Response(
            telemetry.exposition() + model_metrics, media_type="text/plain; version=0.0.4"
        )

    return app
