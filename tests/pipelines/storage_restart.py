"""Retained-volume/real-SQL checkpoint, run in separate Linux worker processes."""

import argparse
import json
import os
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import psycopg

from pipelines.ingestion import BronzeCapture, read_bronze
from pipelines.ingestion.receipts import load_capture, migrate_analytics, persist_capture
from pipelines.storage import FileStore
from shared.contracts.analytics import RawBatchReceipt

from .test_storage import source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    evidence = Path("artifacts/m04/restart.json")
    password = Path("/run/secrets/analytics_password").read_text().strip()
    with psycopg.connect(
        host=os.environ["STORAGE_TEST_POSTGRES_HOST"],
        dbname="analytics_db",
        user="analytics_user",
        password=password,
    ) as tx:
        with tx.transaction():
            migrate_analytics(tx)
            if args.resume:
                saved = json.loads(evidence.read_text())
                receipt = load_capture(tx, saved["receipt"]["capture_id"])
                assert receipt == RawBatchReceipt.model_validate(saved["receipt"])
                store = FileStore(saved["root"])
                records = read_bronze(store, receipt)
                assert records[0].value_bytes == b"\xff{invalid" and records[0].key_bytes is None
                assert persist_capture(tx, receipt, store).redelivery_noop == 1
                disposition = tx.execute(
                    "SELECT disposition FROM source_receipts WHERE capture_id=%s",
                    (receipt.capture_id,),
                ).fetchone()[0]
                assert disposition is None
                saved["restart_recovery"] = "PASS; real SQL and exact file bytes retained"
            else:
                namespace = "bench-m04-restart-" + uuid4().hex
                root = Path(os.environ["LAKEHOUSE_ROOT"]) / ("m04-restart-" + uuid4().hex)
                root.mkdir()
                store = FileStore(root)
                record = replace(
                    source(),
                    source_namespace=namespace,
                    topic=namespace + ".conversation-events.v1",
                )
                receipt = BronzeCapture(store).ingest_bronze([record])
                assert persist_capture(tx, receipt, store).new_sources == 1
                saved = {
                    "root": str(root),
                    "namespace": namespace,
                    "receipt": receipt.model_dump(mode="json"),
                    "restart_recovery": "PENDING",
                }
        evidence.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    print(
        json.dumps({"namespace": saved["namespace"], "restart_recovery": saved["restart_recovery"]})
    )


if __name__ == "__main__":
    main()
