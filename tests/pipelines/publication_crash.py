"""Test-only child process: acknowledge a real boundary, then exit without cleanup."""

import json
import os
import re
import sys
from pathlib import Path

import psycopg

import pipelines.storage as storage
import pipelines.storage.publication as publication
from pipelines.curation import AnalyticsPipeline
from shared.event_transport.codec import EventCodec
from shared.event_transport.schemas import SchemaCache

root, namespace, schema, operation, point, candidate_path = sys.argv[1:]
assert re.fullmatch(r"m05_[a-f0-9]{32}", schema)


def connect():
    return psycopg.connect(
        host=os.environ["STORAGE_TEST_POSTGRES_HOST"],
        dbname="analytics_db",
        user="analytics_user",
        autocommit=True,
        password=Path("/run/secrets/analytics_password").read_text().strip(),
        options=f"-csearch_path={schema} -ctimezone=UTC",
    )


def crash(reached):
    if reached == point:
        print("M08_BOUNDARY_ACK:" + operation + ":" + point, flush=True)
        os._exit(73)


original = storage.os.replace


def before_rename(source, destination):
    if str(destination).endswith(".parquet"):
        crash("before_rename")
    original(source, destination)


storage.os.replace = before_rename
publication.boundary = crash
pipeline = AnalyticsPipeline(
    connect,
    storage.FileStore(root),
    EventCodec(SchemaCache.load("/app/schema-cache.json")),
    code_commit=os.environ["M05_CODE_COMMIT"],
)
if operation == "snapshot":
    pipeline.publish_snapshot(namespace)
else:
    document = pipeline.store.read(candidate_path)
    pipeline.publish_candidate(json.loads(document))
raise AssertionError("Requested publication boundary was not reached")
