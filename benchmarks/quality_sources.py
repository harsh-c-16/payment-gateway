"""Read-only adoption of Vichitr's bounded receipts, files and sink audits."""

import base64
from contextlib import contextmanager
from datetime import date, datetime
from uuid import UUID

from pipelines.curation.sink_observations import read_sink_batches
from pipelines.ingestion import read_bronze
from pipelines.ingestion.receipts import load_capture
from pipelines.storage.parquet import iter_verified
from pipelines.storage.publication import iter_membership
from pipelines.storage.readers import active_manifest, quarantine, receipts
from projectctl.artifacts import content_hash


def json_value(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(item) for item in value]
    return value


class QualitySources:
    """connect must use a read-only role/default, never the worker's write handle.

    The explicit review pins this mapping and the source APIs. No cleaners,
    reducers, publish_snapshot, offset commits or corrective writes are called.
    """

    def __init__(self, connect, store, lag_reader):
        self.connection, self.store, self.lag = connect, store, lag_reader

    @contextmanager
    def connect(self):
        with self.connection() as tx:
            if tx.execute("SHOW default_transaction_read_only").fetchone()[0] != "on":
                raise ValueError("quality audit requires a read-only analytics connection")
            yield tx

    def receipt_rows(self, namespace):
        cursor, result, seen = None, [], set()
        while True:
            page = receipts(self.connect, namespace, cursor, 1000)
            result.extend(row.model_dump(mode="json") for row in page.receipts)
            if page.next_cursor is None:
                return result
            if page.next_cursor in seen:
                raise ValueError("receipt cursor did not advance")
            seen.add(page.next_cursor)
            cursor = page.next_cursor

    def active(self, namespace):
        gold = active_manifest(self.connect, namespace, "gold")
        rows = []
        for descriptor in gold.files:
            if descriptor.schema_name != "pipeline_minute":
                raise ValueError("quality namespace contains unexpected business Gold")
            rows.extend(json_value(row) for row in iter_verified(self.store, descriptor))
        with self.connect() as tx:
            members = list(iter_membership(tx, namespace, "gold", gold.generation))
        # Files and membership are read at this pinned generation, never by a
        # second latest-generation query that could race publication.
        digest = content_hash(gold.model_dump(mode="json"))
        return {
            "namespace": namespace,
            "generation": gold.generation,
            "query_generation": gold.generation,
            "manifest_sha256": digest,
            "query_manifest_sha256": digest,
            "membership_ids": members,
            "rows": rows,
            "manifest": gold.model_dump(mode="json"),
        }

    def export(self, context):
        namespace, run_id = context["namespace"], context["run_id"]
        batches, cursor = [], 0
        while True:
            page = read_sink_batches(self.connect, namespace, run_id, after=cursor, limit=1000)
            if not page:
                break
            next_cursor = page[-1]["batch_sequence"]
            if next_cursor <= cursor:
                raise ValueError("sink cursor did not advance")
            cursor = next_cursor
            batches.extend(page)
        bronze = []
        for capture_id in sorted({str(row["capture_id"]) for row in batches}):
            with self.connect() as tx, tx.transaction():
                capture = load_capture(tx, capture_id)
            if capture is None or any(r.namespace != namespace for r in capture.records):
                raise ValueError("capture namespace/membership missing")
            for record in read_bronze(self.store, capture):
                bronze.append(
                    {
                        "source": dict(
                            topic=record.topic, partition=record.partition, offset=record.offset
                        ),
                        "value_base64": base64.b64encode(record.value_bytes).decode(),
                        "key_base64": base64.b64encode(record.key_bytes).decode(),
                        "headers": [[name, value.decode()] for name, value in record.headers],
                    }
                )
        # Restart captures may contain the same physical coordinate. Preserve all
        # batches, but the physical Bronze ledger below must contain each once.
        unique_bronze = {}
        for row in bronze:
            key = tuple(row["source"].values())
            if key in unique_bronze and unique_bronze[key] != row:
                raise ValueError("conflicting Bronze bytes across restart captures")
            unique_bronze[key] = row
        invalid, cursor, seen = [], None, set()
        while True:
            page = quarantine(self.connect, namespace, cursor, 1000)
            invalid.extend(row.model_dump(mode="json") for row in page.records)
            if page.next_cursor is None:
                break
            if page.next_cursor in seen:
                raise ValueError("quarantine cursor did not advance")
            seen.add(page.next_cursor)
            cursor = page.next_cursor
        silver_manifest = active_manifest(self.connect, namespace, "silver")
        silver = []
        for descriptor in silver_manifest.files:
            silver.extend(json_value(row) for row in iter_verified(self.store, descriptor))
        lag = self.lag.read_sync()
        offsets = [reading.details for reading in lag.values()]
        return {
            "namespace": namespace,
            "run_id": run_id,
            "test_mode": "real",
            "collection_complete": len(lag) == len(self.lag.series),
            "receipts": self.receipt_rows(namespace),
            "quarantine": invalid,
            "bronze": list(unique_bronze.values()),
            "silver": silver,
            "silver_manifest": silver_manifest.model_dump(mode="json"),
            "gold": self.active(namespace),
            "offsets": offsets,
            "sink_batches": json_value(batches),
        }
