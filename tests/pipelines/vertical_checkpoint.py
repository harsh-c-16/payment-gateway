"""Persistent M05 synthetic slice; fresh-process recovery uses public analytics tables."""

import argparse
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from pipelines.ingestion import BronzeCapture
from pipelines.ingestion.receipts import migrate_analytics
from pipelines.ingestion.runtime import pipeline_from_env
from shared.contracts.events import SourceRecord
from shared.event_transport.consumer import raw_fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    pipeline = pipeline_from_env()
    evidence = Path("artifacts/m05/checkpoint-slice.json")
    if args.resume:
        saved = json.loads(evidence.read_text())
        namespace = saved["namespace"]
        now = datetime.now(UTC).date()
        result = pipeline.query_gold(
            namespace, "pipeline_minute", now - timedelta(days=1), now + timedelta(days=1)
        )
        assert result.generation == 1 and sum(row["unique_events"] for row in result.rows) == 1
        assert pipeline.active_manifest(namespace, "silver").generation == 1
        saved["restart"] = (
            "PASS; active immutable files and SQL pointers recovered in fresh process"
        )
    else:
        namespace = "bench-m05-check-" + uuid4().hex
        with pipeline.connect() as tx, tx.transaction():
            migrate_analytics(tx)
        session = str(uuid4())
        event = pipeline.codec.build_event(
            "CONVERSATION_TURN",
            {
                "turn_id": str(uuid4()),
                "mode": "fixed",
                "outcome": "success",
                "duration_ms": 1.0,
                "llm_call_count": 0,
                "extractor_source": "rules",
            },
            {
                "namespace": namespace,
                "run_id": "m05-persistent-synthetic-fixture",
                "session_id": session,
                "user_id": "synthetic-user",
                "correlation_id": str(uuid4()),
            },
            "session",
            session,
            1,
            datetime.now(UTC),
            metadata={"synthetic": True, "scenario_source": "simulation"},
        )
        raw, headers, topic, key = pipeline.codec.encode(event)
        key = key.encode() if isinstance(key, str) else key
        source = SourceRecord(
            namespace,
            topic,
            0,
            0,
            key,
            raw,
            tuple(headers),
            None,
            datetime.now(UTC),
            raw_fingerprint(key, raw, tuple(headers)),
        )
        capture = BronzeCapture(pipeline.store).ingest_bronze([source])
        assert (
            pipeline.curate_silver(
                capture, {"run_id": "m05-persistent-synthetic-fixture"}
            ).new_valid
            == 1
        )
        manifest = pipeline.publish_snapshot(namespace)
        saved = {
            "namespace": namespace,
            "code_commit": pipeline.code_commit,
            "event_id": event.event_id,
            "manifest": manifest.model_dump(mode="json"),
            "root": str(pipeline.store.root),
            "restart": "PENDING",
            "real_shared_outbox": "NOT_RUN; absent",
            "full_G1": "NOT_RUN; missing outbox/harness adoption",
        }
    evidence.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    print(json.dumps({"namespace": namespace, "restart": saved["restart"]}))


if __name__ == "__main__":
    main()
