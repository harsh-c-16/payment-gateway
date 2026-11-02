"""Versioned import outputs: Parquet files, hashed manifests, SKU manifest and facets."""

import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from pipelines.catalog.normalize import RULES_VERSION, dataset_revision
from pipelines.storage import FileStore
from shared.contracts.analytics import FileDescriptor
from shared.contracts.catalog import (
    FacetDictionary,
    NormalizedCatalogManifest,
    SkuManifest,
    SourceManifest,
)
from shared.event_transport.schemas import canonical_json

CANONICAL_SCHEMA = pa.schema(
    [
        ("source_row", pa.int32()),
        ("sku", pa.string()),
        ("product_id", pa.string()),
        ("source_pid", pa.string()),
        ("source_observation_id", pa.string()),
        ("source_crawled_at", pa.timestamp("us", tz="UTC")),
        ("source_url", pa.string()),
        ("title", pa.string()),
        ("description", pa.string()),
        ("category", pa.string()),
        ("category_path", pa.list_(pa.string())),
        ("category_path_raw", pa.string()),
        ("brand", pa.string()),
        ("brand_normalized", pa.string()),
        ("size", pa.string()),
        ("size_kind", pa.string()),
        ("colour", pa.string()),
        ("material", pa.string()),
        ("seller_id", pa.string()),
        ("price_minor", pa.int64()),
        ("retail_price_minor", pa.int64()),
        ("rating", pa.string()),
        ("is_fk_advantage", pa.bool_()),
        ("image_urls", pa.string()),
        ("attributes", pa.string()),
        ("unkeyed_specifications", pa.string()),
        ("specification_entries", pa.string()),
        ("quality_flags", pa.list_(pa.string())),
        ("active", pa.bool_()),
        ("inactive_reason", pa.string()),
        ("normalized_business_hash", pa.string()),
    ]
)


def peak_rss_kib():
    """None on Windows, which has no resource module; a missing sample stays missing."""
    try:
        import resource
    except ImportError:
        return None
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def content_hash(document):
    return hashlib.sha256(
        canonical_json({k: v for k, v in document.items() if k != "content_sha256"})
    ).hexdigest()


def hash_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_atomic(path, data):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(data)
    os.replace(temporary, path)


def write_json(path, document):
    write_atomic(path, json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False).encode())


def _descriptor(path, table, schema_name):
    return FileDescriptor(
        path=path.name,
        sha256=hash_file(path),
        byte_size=path.stat().st_size,
        row_count=table.num_rows,
        schema_name=schema_name,
        schema_version=1,
        partition_values={},
        min_event_time=None,
        max_event_time=None,
    )


def _write_table(out, name, table):
    path = Path(out) / f"{name}.parquet"
    temporary = path.with_name(path.name + ".tmp")
    pq.write_table(table, temporary, compression="zstd")
    os.replace(temporary, path)
    return _descriptor(path, table, f"catalog-{name}")


def canonical_row(observation):
    fields = observation.fields
    row = {name: fields.get(name) for name in CANONICAL_SCHEMA.names}
    row.update(
        source_row=fields["source_row_number"],
        category_path=fields["category_path_normalized"],
        image_urls=canonical_json(fields["image_urls"]).decode(),
        attributes=canonical_json(fields["attributes"]).decode(),
        unkeyed_specifications=canonical_json(fields["unkeyed_specifications"]).decode(),
        specification_entries=canonical_json(fields["specification_entries"]).decode(),
        quality_flags=sorted(set(observation.issues)),
        normalized_business_hash=observation.business_hash,
    )
    return row


def archive_source(store_root, source_path, data, source_sha256):
    """Archive the exact bytes by hash through Vichitr's FileStore."""
    Path(store_root).mkdir(parents=True, exist_ok=True)
    return FileStore(store_root).write_immutable(
        f"raw/catalog/{source_sha256}/{Path(source_path).name}", data, source_sha256
    )


def write_source_manifest(out, source_path, descriptor, source_sha256, row_count, dictionary):
    revision = dataset_revision(source_sha256, RULES_VERSION, dictionary["sha256"])
    manifest = SourceManifest(
        source_path=Path(source_path).name,
        raw_archive_descriptor=descriptor,
        source_sha256=source_sha256,
        byte_size=descriptor.byte_size,
        row_count=row_count,
        columns=dictionary["source_header"],
        acquired_at=datetime.fromtimestamp(Path(source_path).stat().st_mtime, UTC),
        rules_version=RULES_VERSION,
        dictionary_sha256=dictionary["sha256"],
        dataset_revision=revision,
    )
    write_json(Path(out) / "source_manifest.json", manifest.model_dump(mode="json"))
    return manifest


def write_normalized(out, source_manifest, raw_rows, observations, selection):
    """Observations, dispositions, issues and canonical rows; rows are verified before loading."""
    out = Path(out)
    header = source_manifest.columns
    observation_rows = []
    issue_rows = []
    disposition_rows = []
    for observation, raw in zip(observations, raw_rows, strict=True):
        row_number = observation.row_number
        cells = {name: raw[name] for name in header}
        observation_rows.append(
            {
                "source_row": row_number,
                "raw_sha256": hashlib.sha256(canonical_json(cells)).hexdigest(),
                "mandatory_valid": observation.mandatory_valid,
                **cells,
            }
        )
        disposition_rows.append(
            {
                "source_row": row_number,
                "uniq_id": observation.uniq_id,
                "pid": observation.pid,
                "disposition": selection.dispositions[row_number],
            }
        )
        issue_rows += [
            {"source_row": row_number, "uniq_id": observation.uniq_id, "code": code}
            for code in observation.issues
        ]
    files = {
        "observations": _write_table(out, "observations", pa.Table.from_pylist(observation_rows)),
        "dispositions": _write_table(out, "dispositions", pa.Table.from_pylist(disposition_rows)),
        "issues": _write_table(
            out,
            "issues",
            pa.Table.from_pylist(
                issue_rows,
                schema=pa.schema(
                    [("source_row", pa.int64()), ("uniq_id", pa.string()), ("code", pa.string())]
                ),
            ),
        ),
        "catalog": _write_table(
            out,
            "catalog",
            pa.Table.from_pylist(
                [canonical_row(item) for item in selection.canonical], schema=CANONICAL_SCHEMA
            ),
        ),
    }
    counts = Counter(selection.dispositions.values())
    manifest = NormalizedCatalogManifest(
        source_manifest_ref=hashlib.sha256(
            canonical_json(source_manifest.model_dump(mode="json"))
        ).hexdigest(),
        dataset_revision=source_manifest.dataset_revision,
        rules_version=RULES_VERSION,
        dictionary_sha256=source_manifest.dictionary_sha256,
        files=files,
        raw_rows=len(observations),
        canonical_rows=len(selection.canonical),
        active_rows=counts["canonical_active"],
        inactive_rows=counts["canonical_inactive_missing_price"],
        superseded_rows=counts["superseded"],
        rejected_rows=counts["rejected_mandatory"],
        canonical_business_digest=selection.digest,
    )
    document = manifest.model_dump(mode="json")
    document["content_sha256"] = content_hash(document)
    write_json(out / "normalized_manifest.json", document)
    return NormalizedCatalogManifest.model_validate(document)


def read_canonical_rows(out, manifest):
    """Verified read: load_catalog never trusts a file the manifest did not hash."""
    path = Path(out) / manifest.files.catalog.path
    if hash_file(path) != manifest.files.catalog.sha256:
        raise ValueError("catalog.parquet differs from its manifest hash")
    rows = pq.read_table(path).to_pylist()
    rows.sort(key=lambda row: row["source_row"])
    return rows


def facet_dictionary(selection, manifest, dictionary):
    """Observed facet values. Path prefixes exclude each path's last segment: it can be a title."""
    roots, brands = dictionary["root_ids"], {}
    prefixes, colours, materials, sizes = set(), set(), set(), set()
    coverage = defaultdict(Counter)
    for item in selection.canonical:
        fields = item.fields
        path = fields["category_path_normalized"]
        for depth in range(1, max(len(path), 2)):
            prefixes.add(tuple(path[:depth]))
        if fields["brand_normalized"]:
            brands.setdefault(fields["brand_normalized"], fields["brand"])
        colours.update(filter(None, [fields["colour"]]))
        materials.update(filter(None, [fields["material"]]))
        sizes.update(filter(None, [fields["size"]]))
        bucket = coverage[fields["category"] or "unclassified"]
        bucket["canonical"] += 1
        bucket["active"] += fields["active"]
        for name in ("brand", "colour", "material", "size"):
            bucket[name] += fields[name] is not None
    return FacetDictionary(
        dataset_revision=manifest.dataset_revision,
        dictionary_version=dictionary["dictionary_version"],
        roots=[{"id": slug, "label": label} for label, slug in sorted(roots.items())],
        path_prefixes=[list(prefix) for prefix in sorted(prefixes) if prefix],
        brands=[{"key": key, "label": brands[key]} for key in sorted(brands)],
        colours=sorted(colours),
        materials=sorted(materials),
        allowed_apparel_sizes=dictionary["allowed_apparel_sizes"],
        observed_apparel_sizes=sorted(sizes),
        coverage_by_category={name: dict(counts) for name, counts in sorted(coverage.items())},
    )


def build_sku_manifest(rows, manifest, namespace, source_sha256):
    """rows: (sku, product_id, source_pid, source_observation_id) for active listings only."""
    document = SkuManifest(
        dataset_revision=manifest.dataset_revision,
        source_sha256=source_sha256,
        rules_version=manifest.rules_version,
        namespace=namespace,
        sku_count=len(rows),
        sorted_skus=[
            {
                "sku": row[0],
                "product_id": row[1],
                "source_pid": row[2],
                "source_observation_id": row[3],
            }
            for row in sorted(rows)
        ],
        canonical_business_digest=manifest.canonical_business_digest,
    ).model_dump(mode="json")
    document["content_sha256"] = content_hash(document)
    return document


def quality_by_category_rows(selection, observations):
    """Denominators stay explicit: missing optional facets are not rejected products."""
    rows = defaultdict(Counter)
    for item in selection.canonical:
        fields = item.fields
        bucket = rows[fields["category"] or "unclassified"]
        bucket["canonical"] += 1
        bucket["active"] += fields["active"]
        for name in ("brand", "description", "colour", "material", "size"):
            bucket["known_" + name] += fields[name] is not None
        bucket["issues"] += len(item.issues)
    return rows
