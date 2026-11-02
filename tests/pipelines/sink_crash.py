"""Test-only native consumer: exit after SQL COMMIT, before timer and offset writes."""

import os
import re
import sys
from pathlib import Path
from time import monotonic

import psycopg

import pipelines.curation as curation
from pipelines.curation import AnalyticsPipeline
from pipelines.storage import FileStore
from shared.event_transport.codec import EventCodec
from shared.event_transport.consumer import ConsumerGroup
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


def crash(*args):
    print("M11_BOUNDARY_ACK:after_sink_commit_before_timer_and_offset", flush=True)
    os._exit(73)


curation.observe_sink_batch = crash
pipeline = AnalyticsPipeline(
    connect,
    FileStore(root),
    EventCodec(SchemaCache.load("/app/schema-cache.json")),
    code_commit=os.environ["M05_CODE_COMMIT"],
)
group = ConsumerGroup(
    namespace + ".analytics.v1",
    [namespace + ".conversation-events.v1"],
    os.environ["KAFKA_BOOTSTRAP_SERVERS"],
)
try:
    deadline = monotonic() + 40
    while monotonic() < deadline:
        pipeline.ingest_once(group, run_id="m05-real-kafka-fixture", max_records=1)
    raise AssertionError("Native source did not reach the sink boundary")
finally:
    group.close()
