"""Explicit analytics process bindings; importing this module opens nothing."""

import os
import re
from pathlib import Path

import psycopg

from pipelines.curation import AnalyticsPipeline
from pipelines.storage import FileStore
from shared.event_transport.codec import EventCodec
from shared.event_transport.schemas import SchemaCache


def pipeline_from_env():
    if os.environ.get("SINK_BATCH_MAX_ROWS", "1") != "1":
        raise ValueError("M05 supports B0 sink rows=1; batching is a later checkpoint")
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

    return AnalyticsPipeline(
        connect,
        FileStore(os.environ["LAKEHOUSE_ROOT"]),
        EventCodec(SchemaCache.load(os.environ["EVENT_SCHEMA_CACHE_PATH"])),
        code_commit=commit,
    )


def app_from_env():
    from .api import create_app

    return create_app(
        pipeline_from_env(),
        internal_token=os.environ["INTERNAL_API_TOKEN"],
        metrics_namespace=os.environ.get("RUN_NAMESPACE"),
    )
