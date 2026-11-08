"""Explicit analytics process bindings; importing this module opens nothing."""

import os
import re
from contextlib import contextmanager
from pathlib import Path
from threading import BoundedSemaphore

import psycopg

from pipelines.curation import AnalyticsPipeline, BatchConfig
from pipelines.storage import FileStore
from shared.event_transport.codec import EventCodec
from shared.event_transport.schemas import SchemaCache


def worker_allocation():
    workers = os.environ.get("ANALYTICS_WORKERS", "1")
    index = os.environ.get("ANALYTICS_WORKER_INDEX", "0")
    if workers not in {"1", "3"} or index not in {"0", "1", "2"} or int(index) >= int(workers):
        raise ValueError("Declare one or three workers and a distinct valid worker index")
    return int(workers), int(index)


def limited_connect(dial, limit):
    """Bound live SQL sessions without adding a dependency or retaining idle sessions."""
    slots = BoundedSemaphore(limit)

    @contextmanager
    def connect():
        if not slots.acquire(timeout=5):
            raise TimeoutError("Analytics connection allocation exhausted")
        try:
            with dial() as tx:
                yield tx
        finally:
            slots.release()

    return connect


def pipeline_from_env(*, role="worker"):
    if role not in {"worker", "api"}:
        raise ValueError("Unknown analytics process role")
    rows = os.environ.get("SINK_BATCH_MAX_ROWS", "1")
    if rows not in {"1", "100"}:
        raise ValueError("Use B0 (1 row) or O1 (100 rows)")
    batch = BatchConfig(run_id="configuration", sink_batch_max_rows=int(rows))
    if os.environ.get("SINK_BATCH_MAX_WAIT_MS", "50") != "50":
        raise ValueError("The frozen sink wait is 50 ms")
    commit = os.environ["CODE_COMMIT"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("CODE_COMMIT must be the actual 40-character Git revision")
    url = os.environ.get("ANALYTICS_DATABASE_URL")
    if url:

        def connect():
            return psycopg.connect(
                url, autocommit=True, connect_timeout=5, options="-ctimezone=UTC"
            )
    else:
        password = (
            Path(os.environ.get("ANALYTICS_PASSWORD_FILE", "/run/secrets/analytics_password"))
            .read_text()
            .strip()
        )
        host = os.environ.get("ANALYTICS_DB_HOST", "postgres")

        def connect():
            return psycopg.connect(
                host=host,
                dbname="analytics_db",
                user="analytics_user",
                password=password,
                autocommit=True,
                connect_timeout=5,
                options="-ctimezone=UTC",
            )

    workers, _ = worker_allocation()
    pipeline = AnalyticsPipeline(
        limited_connect(connect, 12 // workers if role == "worker" else 2),
        FileStore(os.environ["LAKEHOUSE_ROOT"]),
        EventCodec(SchemaCache.load(os.environ["EVENT_SCHEMA_CACHE_PATH"])),
        code_commit=commit,
        sink_batch_max_rows=batch.sink_batch_max_rows,
    )
    pipeline.publisher_connect = limited_connect(connect, 2)
    return pipeline


def app_from_env():
    from .api import create_app

    return create_app(
        pipeline_from_env(role="api"),
        internal_token=os.environ["INTERNAL_API_TOKEN"],
        metrics_namespace=os.environ.get("RUN_NAMESPACE"),
    )
