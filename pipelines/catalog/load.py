"""Idempotent staging and atomic promotion: row-INSERT (I0) or COPY (I1), same semantics."""

import hashlib
import json
from time import perf_counter
from uuid import uuid4

from psycopg.types.json import Jsonb

from pipelines.catalog.artifacts import build_sku_manifest, read_canonical_rows
from pipelines.catalog.normalize import business_digest
from shared.contracts.catalog import CatalogLoadReport
from shared.event_transport.schemas import canonical_json

CHUNK_ROWS = 1000
STAGE_COLUMNS = (
    "source_row",
    "sku",
    "product_id",
    "source_pid",
    "source_observation_id",
    "source_crawled_at",
    "source_url",
    "title",
    "description",
    "category",
    "category_path",
    "category_path_raw",
    "brand",
    "brand_normalized",
    "size",
    "size_kind",
    "colour",
    "material",
    "seller_id",
    "price_minor",
    "retail_price_minor",
    "rating",
    "is_fk_advantage",
    "image_urls",
    "attributes",
    "unkeyed_specifications",
    "specification_entries",
    "quality_flags",
    "active",
    "inactive_reason",
    "normalized_business_hash",
)
JSON_COLUMNS = {"image_urls", "attributes", "unkeyed_specifications", "specification_entries"}
INSERT_SQL = (
    f"INSERT INTO catalog_stage (import_id,{','.join(STAGE_COLUMNS)}) "
    f"VALUES (%s,{','.join(['%s'] * len(STAGE_COLUMNS))})"
)
COPY_SQL = f"COPY catalog_stage (import_id,{','.join(STAGE_COLUMNS)}) FROM STDIN"
_BUSINESS_COLUMNS = (
    "title,description,category,category_path,brand,brand_normalized,size,size_kind,colour,"
    "material,seller_id,price_minor,retail_price_minor,rating,is_fk_advantage,image_urls,"
    "attributes,unkeyed_specifications,specification_entries,quality_flags,active,"
    "inactive_reason,normalized_business_hash"
)
_PROVENANCE_COLUMNS = (
    "dataset_revision,import_id,source_row,source_pid,source_observation_id,source_crawled_at,"
    "source_url,category_path_raw"
)
# search_vector weights the title above the description; computed in one set-based statement.
PROMOTE_SQL = f"""
WITH upserted AS (
    INSERT INTO products AS p (namespace,sku,product_id,{_PROVENANCE_COLUMNS},{_BUSINESS_COLUMNS},
                               category_path_folded,search_vector)
    SELECT %(namespace)s,s.sku,s.product_id,%(revision)s,s.import_id,s.source_row,s.source_pid,
           s.source_observation_id,s.source_crawled_at,s.source_url,s.category_path_raw,
           s.title,s.description,s.category,s.category_path,s.brand,s.brand_normalized,s.size,
           s.size_kind,s.colour,s.material,s.seller_id,s.price_minor,s.retail_price_minor,
           s.rating,s.is_fk_advantage,s.image_urls,s.attributes,s.unkeyed_specifications,
           s.specification_entries,s.quality_flags,s.active,s.inactive_reason,
           s.normalized_business_hash,
           ARRAY(SELECT lower(segment) FROM unnest(s.category_path) AS segment),
           setweight(to_tsvector('english', s.title), 'A')
             || setweight(to_tsvector('english', coalesce(s.description, '')), 'B')
    FROM catalog_stage s WHERE s.import_id = %(import_id)s
    ON CONFLICT (namespace, sku) DO UPDATE SET
        dataset_revision=EXCLUDED.dataset_revision, import_id=EXCLUDED.import_id,
        source_row=EXCLUDED.source_row, source_pid=EXCLUDED.source_pid,
        source_observation_id=EXCLUDED.source_observation_id,
        source_crawled_at=EXCLUDED.source_crawled_at, source_url=EXCLUDED.source_url,
        category_path_raw=EXCLUDED.category_path_raw,
        title=EXCLUDED.title, description=EXCLUDED.description, category=EXCLUDED.category,
        category_path=EXCLUDED.category_path, category_path_folded=EXCLUDED.category_path_folded,
        brand=EXCLUDED.brand, brand_normalized=EXCLUDED.brand_normalized, size=EXCLUDED.size,
        size_kind=EXCLUDED.size_kind, colour=EXCLUDED.colour, material=EXCLUDED.material,
        seller_id=EXCLUDED.seller_id, price_minor=EXCLUDED.price_minor,
        retail_price_minor=EXCLUDED.retail_price_minor, rating=EXCLUDED.rating,
        is_fk_advantage=EXCLUDED.is_fk_advantage, image_urls=EXCLUDED.image_urls,
        attributes=EXCLUDED.attributes, unkeyed_specifications=EXCLUDED.unkeyed_specifications,
        specification_entries=EXCLUDED.specification_entries,
        quality_flags=EXCLUDED.quality_flags, active=EXCLUDED.active,
        inactive_reason=EXCLUDED.inactive_reason, search_vector=EXCLUDED.search_vector,
        normalized_business_hash=EXCLUDED.normalized_business_hash,
        catalog_version = p.catalog_version + CASE
            WHEN p.normalized_business_hash <> EXCLUDED.normalized_business_hash THEN 1 ELSE 0 END
    RETURNING old.sku IS NULL AS inserted, old.catalog_version <> new.catalog_version AS updated
)
SELECT count(*) FILTER (WHERE inserted) AS inserted,
       count(*) FILTER (WHERE updated) AS updated
FROM upserted
"""


class ImportReconciliationError(RuntimeError):
    """Staged rows do not reconcile with the manifest; the catalogue stays unpromoted."""


def _stage_values(import_id, row):
    return [import_id] + [
        Jsonb(json.loads(row[name])) if name in JSON_COLUMNS else row[name]
        for name in STAGE_COLUMNS
    ]


def _chunk_hash(rows):
    return hashlib.sha256(
        canonical_json([[row["source_row"], row["normalized_business_hash"]] for row in rows])
    ).hexdigest()


def _stage_chunk(connection, import_id, chunk_no, rows, load_mode):
    """Rows and their checkpoint commit together, so a crash never leaves a partial chunk."""
    with connection.transaction():
        if load_mode == "row":
            for row in rows:
                connection.execute(INSERT_SQL, _stage_values(import_id, row))
        else:
            with connection.cursor().copy(COPY_SQL) as copy:
                for row in rows:
                    copy.write_row(_stage_values(import_id, row))
        connection.execute(
            "INSERT INTO catalog_import_chunks (import_id,chunk_no,row_count,chunk_sha256,"
            "load_mode) VALUES (%s,%s,%s,%s,%s)",
            (import_id, chunk_no, len(rows), _chunk_hash(rows), load_mode),
        )


def _load_ledgers(connection, namespace, source_hash, observations, dispositions):
    """Source ledger is identical for both load modes, so it is timed apart from staging."""
    with connection.transaction():
        loaded = connection.execute(
            "SELECT count(*) FROM source_dispositions WHERE namespace=%s AND source_hash=%s",
            (namespace, source_hash),
        ).fetchone()[0]
        if loaded == len(dispositions):
            return
        with connection.cursor().copy(
            "COPY source_observations (namespace,source_hash,row_no,uniq_id,pid,raw_sha256,"
            "mandatory_valid) FROM STDIN"
        ) as copy:
            for row in observations:
                copy.write_row((namespace, source_hash, *row))
        with connection.cursor().copy(
            "COPY source_dispositions (namespace,source_hash,row_no,disposition,issue_codes) "
            "FROM STDIN"
        ) as copy:
            for row in dispositions:
                copy.write_row((namespace, source_hash, *row))


def load_catalog(
    connection,
    *,
    out,
    source_manifest,
    manifest,
    load_mode,
    namespace,
    observations,
    dispositions,
    facets,
    issue_counts,
    hook=lambda stage: None,
):
    """Stage in bounded chunks, reconcile, then promote everything in one transaction.

    connection is a dedicated autocommit session: it holds the import advisory lock, and each
    chunk commits separately. A completed import of the same source and rules is a no-op.
    """
    source_hash = source_manifest.source_sha256
    elapsed = {}
    connection.execute(
        "SELECT pg_advisory_lock(hashtextextended(%s, 0))", (f"catalog:{namespace}:{source_hash}",)
    )
    try:
        existing = connection.execute(
            "SELECT import_id,status,canonical_business_digest FROM catalog_imports "
            "WHERE namespace=%s AND source_hash=%s AND rules_version=%s",
            (namespace, source_hash, manifest.rules_version),
        ).fetchone()
        if existing and existing[2] != manifest.canonical_business_digest:
            raise ImportReconciliationError("same source and rules produced a different digest")
        if existing and existing[1] == "complete":
            return _report(
                connection,
                existing[0],
                manifest,
                source_hash,
                namespace,
                load_mode,
                0,
                0,
                elapsed,
                "noop",
                issue_counts,
                inserted=0,
                updated=0,
            )
        started = perf_counter()
        _load_ledgers(connection, namespace, source_hash, observations, dispositions)
        elapsed["ledger_ms"] = (perf_counter() - started) * 1000
        rows = read_canonical_rows(out, manifest)
        if existing:
            import_id = existing[0]
        else:
            import_id = str(uuid4())
            connection.execute(
                "INSERT INTO catalog_imports (import_id,namespace,source_hash,rules_version,"
                "dictionary_sha256,dataset_revision,canonical_business_digest,canonical_rows,"
                "chunk_rows,load_mode,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'staging')",
                (
                    import_id,
                    namespace,
                    source_hash,
                    manifest.rules_version,
                    manifest.dictionary_sha256,
                    manifest.dataset_revision,
                    manifest.canonical_business_digest,
                    manifest.canonical_rows,
                    CHUNK_ROWS,
                    load_mode,
                ),
            )
        committed = dict(
            connection.execute(
                "SELECT chunk_no,chunk_sha256 FROM catalog_import_chunks WHERE import_id=%s",
                (import_id,),
            ).fetchall()
        )
        started = perf_counter()
        chunks = [rows[start : start + CHUNK_ROWS] for start in range(0, len(rows), CHUNK_ROWS)]
        resumed = 0
        for number, chunk in enumerate(chunks):
            if number in committed:
                if committed[number] != _chunk_hash(chunk):
                    raise ImportReconciliationError(f"staged chunk {number} hash differs")
                resumed += 1
                continue
            _stage_chunk(connection, import_id, number, chunk, load_mode)
            hook("after_chunk_commit")
        elapsed["staging_ms"] = (perf_counter() - started) * 1000
        hook("before_promotion")
        started = perf_counter()
        with connection.transaction():
            staged = connection.execute(
                "SELECT sku,normalized_business_hash FROM catalog_stage WHERE import_id=%s",
                (import_id,),
            ).fetchall()
            if (
                len(staged) != manifest.canonical_rows
                or business_digest([list(row) for row in staged])
                != manifest.canonical_business_digest
            ):
                raise ImportReconciliationError("staged rows do not reconcile with the manifest")
            result = connection.execute(
                PROMOTE_SQL,
                {
                    "namespace": namespace,
                    "revision": manifest.dataset_revision,
                    "import_id": import_id,
                },
            ).fetchone()
            connection.execute(
                "UPDATE products SET active=false,inactive_reason='REMOVED_FROM_SOURCE',"
                "catalog_version=catalog_version+1 "
                "WHERE namespace=%s AND import_id<>%s AND active",
                (namespace, import_id),
            )
            connection.execute(
                "INSERT INTO facet_dictionaries (namespace,dataset_revision,document) "
                "VALUES (%s,%s,%s) ON CONFLICT (namespace,dataset_revision) DO NOTHING",
                (namespace, manifest.dataset_revision, Jsonb(facets)),
            )
            connection.execute(
                "UPDATE catalog_imports SET status='complete',completed_at=clock_timestamp() "
                "WHERE import_id=%s",
                (import_id,),
            )
        elapsed["promotion_ms"] = (perf_counter() - started) * 1000
        return _report(
            connection,
            import_id,
            manifest,
            source_hash,
            namespace,
            load_mode,
            len(chunks),
            resumed,
            elapsed,
            "promoted",
            issue_counts,
            inserted=result[0],
            updated=result[1],
        )
    finally:
        connection.execute(
            "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
            (f"catalog:{namespace}:{source_hash}",),
        )


def _report(
    connection,
    import_id,
    manifest,
    source_hash,
    namespace,
    load_mode,
    chunks,
    resumed,
    elapsed,
    status,
    issue_counts,
    *,
    inserted,
    updated,
):
    return CatalogLoadReport(
        import_id=str(import_id),
        source_hash=source_hash,
        dataset_revision=manifest.dataset_revision,
        raw_rows=manifest.raw_rows,
        canonical_rows=manifest.canonical_rows,
        active_rows=manifest.active_rows,
        inactive_rows=manifest.inactive_rows,
        superseded_rows=manifest.superseded_rows,
        rejected_rows=manifest.rejected_rows,
        issue_counts=issue_counts,
        inserted=inserted,
        updated=updated,
        unchanged=manifest.canonical_rows - inserted - updated,
        load_mode=load_mode,
        chunk_count=chunks,
        chunks_resumed=resumed,
        elapsed_by_stage_ms=elapsed,
        canonical_business_digest=manifest.canonical_business_digest,
        status=status,
        artifact_paths=[],
    )


def export_sku_manifest(connection, manifest, namespace, source_hash):
    """Read back from promoted rows: active listings only, no stock guesses."""
    rows = connection.execute(
        "SELECT sku,product_id,source_pid,source_observation_id FROM products "
        "WHERE namespace=%s AND dataset_revision=%s AND active ORDER BY sku",
        (namespace, manifest.dataset_revision),
    ).fetchall()
    return build_sku_manifest(rows, manifest, namespace, source_hash)
