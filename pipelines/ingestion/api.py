"""Analytics read API. No arbitrary SQL, fake replay jobs, or hidden DB connection on import."""

from datetime import date
from secrets import compare_digest
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import TypeAdapter, ValidationError

from pipelines.curation import UnsupportedEvent
from pipelines.curation.quarantine import outbox_binding
from pipelines.storage import sync_directory
from pipelines.storage.readers import quarantine, receipts
from shared.contracts.analytics import (
    DatasetManifest,
    GoldQueryResult,
    QuarantinePage,
    ReceiptPage,
    ReplayRequest,
)
from shared.contracts.common import ErrorBody, ErrorCode, ErrorResponse, Identifier
from shared.contracts.events import Namespace
from shared.local_diagnostics import OutboxUnavailable


def create_app(pipeline, *, internal_token, metrics_namespace=None):
    if not isinstance(internal_token, str) or not internal_token:
        raise ValueError("An explicit internal service token is required")
    if metrics_namespace is not None:
        TypeAdapter(Namespace).validate_python(metrics_namespace)
    app = FastAPI(title="Analytics", docs_url=None, redoc_url=None, openapi_url=None)

    def failure(request, status, code, message, retryable=False):
        try:
            correlation = TypeAdapter(Identifier).validate_python(
                request.headers.get("x-correlation-id", "analytics")
            )
        except ValueError:
            correlation = "analytics"
        body = ErrorResponse(
            error=ErrorBody(code=code, message=message, retryable=retryable, details={}),
            correlation_id=correlation,
        )
        return JSONResponse(status_code=status, content=body.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return failure(request, 422, ErrorCode.VALIDATION_ERROR, "Invalid analytics request")

    @app.exception_handler(Exception)
    async def unavailable(request, exc):
        if isinstance(exc, (ValueError, ValidationError)):
            return failure(
                request,
                400,
                ErrorCode.VALIDATION_ERROR,
                "Invalid analytics parameters or stored data",
            )
        if isinstance(exc, LookupError):
            return failure(request, 404, ErrorCode.NOT_FOUND, "No analytics result")
        return failure(
            request, 503, ErrorCode.DEPENDENCY_UNAVAILABLE, "Analytics dependency unavailable", True
        )

    async def internal(request: Request):
        supplied = request.headers.get("authorization", "")
        if not compare_digest(supplied.encode(), ("Bearer " + internal_token).encode()):
            from fastapi import HTTPException

            raise HTTPException(401)

    from fastapi import HTTPException

    @app.exception_handler(HTTPException)
    async def http_failure(request, exc):
        return failure(
            request, exc.status_code, ErrorCode.UNAUTHORIZED, "Internal service token required"
        )

    @app.get("/health/live")
    def live():
        return {"status": "live"}

    @app.get("/health/ready")
    def ready():
        try:
            sync_directory(pipeline.store.root)
            with pipeline.connect() as tx:
                applied = {
                    row[0]
                    for row in tx.execute(
                        "SELECT version FROM analytics_schema_migrations"
                    ).fetchall()
                }
            if not {1, 2, 3, 4, 5}.issubset(applied):
                raise RuntimeError("Migration missing")
            outbox_binding()
        except OutboxUnavailable:
            return JSONResponse(
                status_code=503, content={"status": "not_ready", "dependency": "shared_outbox"}
            )
        except Exception:
            return JSONResponse(status_code=503, content={"status": "not_ready"})
        return {"status": "ready"}

    @app.get("/metrics")
    def metrics():
        if metrics_namespace is not None:
            with pipeline.connect() as tx:
                pending = tx.execute(
                    "SELECT count(*) FROM export_pending WHERE namespace=%s", (metrics_namespace,)
                ).fetchone()[0]
                generation = tx.execute(
                    """SELECT generation FROM active_datasets
                    WHERE namespace=%s AND dataset='gold'""",
                    (metrics_namespace,),
                ).fetchone()
            pipeline.telemetry.record("gold_pending_events", pending)
            if generation:
                pipeline.telemetry.record("gold_generation", generation[0])
        return Response(pipeline.telemetry.exposition(), media_type="text/plain; version=0.0.4")

    @app.get("/v1/analytics/manifests/{dataset}/active", response_model=DatasetManifest)
    def manifest(dataset: Literal["silver", "gold"], namespace: Namespace):
        return pipeline.active_manifest(namespace, dataset)

    @app.get("/v1/analytics/gold/{table}", response_model=GoldQueryResult)
    def gold(
        table: str,
        namespace: Namespace,
        date_from: date,
        date_to: date,
        currency: Literal["INR"] | None = None,
    ):
        return pipeline.query_gold(namespace, table, date_from, date_to, currency)

    @app.get(
        "/internal/v1/analytics/receipts",
        response_model=ReceiptPage,
        dependencies=[Depends(internal)],
    )
    def source_receipts(
        namespace: Namespace,
        after_cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 1000,
    ):
        return receipts(pipeline.connect, namespace, after_cursor, limit)

    @app.get(
        "/internal/v1/analytics/quarantine",
        response_model=QuarantinePage,
        dependencies=[Depends(internal)],
    )
    def quarantines(
        namespace: Namespace,
        cursor: str | None = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 1000,
    ):
        return quarantine(pipeline.connect, namespace, cursor, limit)

    @app.post("/internal/v1/analytics/replays", dependencies=[Depends(internal)])
    def replay(body: ReplayRequest):
        raise UnsupportedEvent("Replay is pending M10")

    @app.get("/internal/v1/analytics/replays/{replay_id}", dependencies=[Depends(internal)])
    def replay_status(replay_id: str):
        raise UnsupportedEvent("Replay is pending M10")

    return app
