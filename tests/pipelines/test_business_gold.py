"""Gold representation boundaries without claiming durable filesystem integration."""

from datetime import UTC, datetime
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq

from pipelines.gold.business import TABLES
from pipelines.storage.parquet import SCHEMAS
from pipelines.storage.readers import _wire


def test_exact_money_and_duration_references_survive_parquet_and_json():
    amount = 2 * (2**63 - 1)
    table = pa.Table.from_pylist(
        [
            {
                "created_amount_minor": Decimal(amount),
                "cohort_date": datetime(2026, 10, 31, tzinfo=UTC),
            }
        ],
        schema=SCHEMAS["daily_conversion"],
    )
    sink = pa.BufferOutputStream()
    pq.write_table(table, sink)
    row = _wire(pq.read_table(pa.BufferReader(sink.getvalue())).to_pylist()[0])
    assert row["created_amount_minor"] == amount and type(row["created_amount_minor"]) is int
    assert row["cohort_date"] == "2026-10-31T00:00:00Z"
    search = pa.Table.from_pylist(
        [
            {
                "duration_sum_ms": "0.3",
                "duration_references": [
                    {"event_id": "synthetic-a", "duration_ms": "0.1"},
                    {"event_id": "synthetic-b", "duration_ms": "0.2"},
                ],
            }
        ],
        schema=SCHEMAS["search_performance"],
    ).to_pylist()[0]
    assert sum(Decimal(r["duration_ms"]) for r in search["duration_references"]) == Decimal(
        search["duration_sum_ms"]
    )
    assert set(TABLES) <= SCHEMAS.keys()
    assert "intent_accuracy" not in SCHEMAS and "retrieval_quality" not in SCHEMAS
