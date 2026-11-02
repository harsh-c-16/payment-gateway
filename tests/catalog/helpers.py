"""Synthetic CSV rows and stock events for catalogue tests; never the real catalogue."""

import csv
from datetime import UTC, datetime
from uuid import uuid4

from pipelines.catalog.adapter import run_import
from pipelines.catalog.normalize import load_dictionary
from shared.contracts.events import SourceRecord
from shared.event_transport.consumer import raw_fingerprint

HEADER = load_dictionary()["source_header"]


def spec(**pairs):
    entries = ", ".join(f'{{"key"=>"{k}", "value"=>"{v}"}}' for k, v in pairs.items())
    return '{"product_specification"=>[' + entries + "]}"


def row(pid, **overrides):
    base = {
        "uniq_id": "obs-" + pid,
        "crawl_timestamp": "2016-01-01T00:00:00Z",
        "product_url": "https://example.invalid/synthetic",
        "product_name": f"Synthetic listing {pid}",
        "product_category_tree": '["Clothing >> Shirts >> Formal"]',
        "pid": pid,
        "retail_price": "999",
        "discounted_price": "379",
        "image": "[]",
        "is_FK_Advantage_product": "false",
        "description": "Synthetic catalogue fixture",
        "product_rating": "No rating available",
        "overall_rating": "No rating available",
        "brand": "",
        "product_specifications": "",
    }
    return {**base, **overrides}


def write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=HEADER)
        writer.writeheader()
        writer.writerows(rows)
    return path


def import_rows(tmp_path, url, namespace, rows, load_mode="copy", **kwargs):
    source = write_csv(tmp_path / f"{namespace}.csv", rows)
    return run_import(
        source,
        load_mode=load_mode,
        namespace=namespace,
        out=tmp_path / namespace,
        url=url,
        **kwargs,
    )


def stock_record(codec, namespace, sku, version, on_hand, reserved, *, offset, source="inventory"):
    """Encoded through the real codec, so the record is what validate_event sees on the wire."""
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    event = codec.build_event(
        event_type="STOCK_UPDATED",
        payload={
            "sku": sku,
            "on_hand": on_hand,
            "reserved": reserved,
            "available": on_hand - reserved,
            "stock_version": version,
            "changed_at": now,
            "order_id": None,
            "reservation_id": None,
            "reason_code": None,
        },
        context={
            "namespace": namespace,
            "run_id": str(uuid4()),
            "correlation_id": str(uuid4()),
            "session_id": None,
            "user_id": None,
        },
        aggregate_type="sku",
        aggregate_id=sku,
        aggregate_version=version,
        event_time=now,
        metadata={
            "dataset_revision": "rev",
            "synthetic": True,
            "scenario_source": "benchmark" if source == "benchmark" else "simulation",
        },
        source_service=source,
    )
    return source_record(codec, event, namespace, offset)


def source_record(codec, event, namespace, offset, *, raw=None):
    encoded, headers, topic, key = codec.encode(event)
    encoded = raw if raw is not None else encoded
    return SourceRecord(
        source_namespace=namespace,
        topic=topic,
        partition=0,
        offset=offset,
        key_bytes=key,
        value_bytes=encoded,
        headers=headers,
        broker_timestamp=None,
        ingested_at=datetime.now(UTC),
        raw_sha256=raw_fingerprint(key, encoded, headers),
    )


def apply_record(db, codec, record, diagnostics):
    from services.catalog import projection

    checked = codec.validate_event(
        record.value_bytes, record.headers, record.topic, record.key_bytes, source_record=record
    )
    with db.transaction() as tx:
        return projection.apply_stock_event(tx, checked, record, diagnostics=diagnostics)


def seed_stock(db, codec, namespace, skus, on_hand=10, *, diagnostics=None, start_offset=1000):
    for index, sku in enumerate(skus):
        apply_record(
            db,
            codec,
            stock_record(codec, namespace, sku, 1, on_hand, 0, offset=start_offset + index),
            diagnostics,
        )
