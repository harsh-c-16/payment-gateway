"""Real worker.main with an explicit isolated test SQL/file binding; no business double."""

import os
import re
import sys
from pathlib import Path

import psycopg

from pipelines.curation import AnalyticsPipeline
from pipelines.ingestion import worker
from pipelines.storage import FileStore
from shared.event_transport.codec import EventCodec
from shared.event_transport.schemas import SchemaCache

root, namespace, schema = sys.argv[1:]
assert re.fullmatch(r"m05_[a-f0-9]{32}", schema)


def connect():
    return psycopg.connect(
        host=os.environ["STORAGE_TEST_POSTGRES_HOST"],
        dbname="analytics_db",
        user="analytics_user",
        password=Path("/run/secrets/analytics_password").read_text().strip(),
        autocommit=True,
        options=f"-csearch_path={schema} -ctimezone=UTC",
    )


pipeline = AnalyticsPipeline(
    connect,
    FileStore(root),
    EventCodec(SchemaCache.load("/app/schema-cache.json")),
    code_commit=os.environ["M05_CODE_COMMIT"],
)
worker.pipeline_from_env = lambda: pipeline  # Only the fixture's schema/root differ from runtime.
os.environ["RUN_NAMESPACE"] = namespace
os.environ["RUN_ID"] = "m11-worker-real-fixture"
worker.main()
