"""Validate immutable layout candidates against pinned published rows, never staging."""

import hashlib
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from psycopg.errors import UniqueViolation

from pipelines.curation.db import one
from pipelines.gold.business import TABLES
from shared.contracts.analytics import DatasetManifest, ManifestCandidate
from shared.contracts.common import INT64_MAX
from shared.event_transport.schemas import canonical_json

from . import publication
from .parquet import verified_parquet
from .readers import _wire

DIGEST_HEADER = b"m08-logical-rows-v1\n"
KEYS = {
    "pipeline_minute": ("minute", "event_type", "source_service"),
    "order_fact": ("order_id",),
    "daily_conversion": ("cohort_date", "currency"),
    "checkout_funnel": ("cohort_date", "currency"),
    "payment_failures": ("cohort_date", "currency", "failure_code"),
    "inventory_failures": ("cohort_date", "reason_code"),
    "search_performance": ("cohort_date", "mode"),
}


class CandidateRejected(ValueError):
    pass


def canonical_logical_row(schema_name, schema_version, row):
    return canonical_json([schema_name, schema_version, _wire(row)])


def digest_sorted_rows(documents):
    """Input is UTF-8 canonical row bytes in ascending byte order, with duplicates retained."""
    digest = hashlib.sha256(DIGEST_HEADER)
    for document in documents:
        digest.update(str(len(document)).encode() + b":" + document + b"\n")
    return digest.hexdigest()


def _money(value, totals):
    if isinstance(value, dict):
        currency = value.get("currency")
        for name, item in value.items():
            if currency is not None and name.endswith("_minor") and item is not None:
                if currency != "INR" or type(item) not in (int, Decimal) or item < 0:
                    raise CandidateRejected("Invalid monetary field in published rows")
                if item != int(item):
                    raise CandidateRejected("Fractional minor units in published rows")
                totals[currency] += int(item)
            elif isinstance(item, (dict, list)):
                _money(item, totals)
    elif isinstance(value, list):
        for item in value:
            _money(item, totals)


def _stage(pipeline, tx, manifest, side):
    totals, count = defaultdict(int), 0
    for descriptor in manifest.files:
        silver = descriptor.schema_name in {"silver-conversation-turn", "silver-events-v1"}
        if (manifest.dataset == "silver") != silver or (
            not silver and descriptor.schema_name not in ("pipeline_minute", *TABLES)
        ):
            raise CandidateRejected("File schema is outside the selected dataset")
        column = (
            "event_time"
            if silver
            else ("minute" if descriptor.schema_name == "pipeline_minute" else "cohort_date")
        )
        minimum = maximum = None
        with verified_parquet(pipeline.store, descriptor) as parquet:
            if any(
                parquet.metadata.row_group(g).column(c).compression != "ZSTD"
                for g in range(parquet.metadata.num_row_groups)
                for c in range(parquet.metadata.num_columns)
            ):
                raise CandidateRejected("Compaction must preserve Zstandard compression")
            with tx.cursor().copy("COPY m08_candidate_rows(side,key,document) FROM STDIN") as copy:
                for batch in parquet.iter_batches(batch_size=32):
                    for row in batch.to_pylist():
                        timestamp = row[column]
                        if row["namespace"] != manifest.namespace or timestamp is None:
                            raise CandidateRejected(
                                "Row namespace/time does not match its manifest"
                            )
                        partitions = (
                            {
                                "event_date": timestamp.date().isoformat(),
                                "event_type": row["event_type"],
                            }
                            if silver
                            else {
                                "event_date"
                                if column == "minute"
                                else "cohort_date": timestamp.date().isoformat(),
                                "table": descriptor.schema_name,
                            }
                        )
                        if descriptor.partition_values != partitions:
                            raise CandidateRejected("File partition metadata differs from its rows")
                        minimum = timestamp if minimum is None else min(minimum, timestamp)
                        maximum = timestamp if maximum is None else max(maximum, timestamp)
                        key = (
                            ["silver", row["event_id"]]
                            if silver
                            else [
                                descriptor.schema_name,
                                *(_wire(row[k]) for k in KEYS[descriptor.schema_name]),
                            ]
                        )
                        document = canonical_logical_row(
                            descriptor.schema_name, descriptor.schema_version, row
                        )
                        if len(document) > publication.ROW_MAX_BYTES:
                            raise CandidateRejected("Candidate row exceeds 8 MiB bound")
                        copy.write_row((side, canonical_json(key).decode(), document))
                        _money(row, totals)
                        count += 1
        if (minimum, maximum) != (descriptor.min_event_time, descriptor.max_event_time):
            raise CandidateRejected("File time bounds differ from its actual rows")
        pipeline.store.sync_existing(descriptor)
    digest = digest_sorted_rows(
        row["document"]
        for row in publication.stream_rows(
            tx, "SELECT document FROM m08_candidate_rows WHERE side=%s ORDER BY document", (side,)
        )
    )
    return digest, count, dict(totals)


def publish_candidate(pipeline, candidate):
    candidate = ManifestCandidate.model_validate(
        candidate.model_dump() if isinstance(candidate, ManifestCandidate) else candidate
    )
    supplied = candidate.candidate_manifest
    namespace = supplied.namespace
    with publication.publisher_session(pipeline, namespace) as tx:
        old = publication._active(tx, namespace)
        if not old or old["gold"].generation != candidate.base_generation:
            raise publication.PublicationConflict(
                "STALE_MANIFEST: candidate base is no longer active"
            )
        base = old[supplied.dataset]
        if (
            supplied.generation != base.generation + 1
            or supplied.parent_generation != base.generation
            or supplied.transform_version != base.transform_version
            or supplied.source_ranges != base.source_ranges
            or supplied.input_manifest_ids != base.input_manifest_ids
        ):
            raise CandidateRejected("Candidate changed base identity, transform or source lineage")
        paths = [f.path for f in supplied.files]
        reused = one(
            tx,
            """SELECT EXISTS(SELECT 1 FROM snapshot_manifests s,
            jsonb_array_elements(s.manifest->'files') f WHERE f->>'path'=ANY(%s)) AS bad""",
            (paths,),
        )["bad"]
        if reused:
            raise CandidateRejected("Candidate must use new immutable output paths")
        try:
            with tx.transaction():
                tx.execute("SET LOCAL work_mem='4MB'")
                tx.execute("""CREATE TEMP TABLE m08_candidate_rows(
                    side text NOT NULL,key text NOT NULL,document bytea NOT NULL,
                    PRIMARY KEY(side,key)) ON COMMIT PRESERVE ROWS""")
                expected = _stage(pipeline, tx, base, "base")
                actual = _stage(pipeline, tx, supplied, "candidate")
                if any(value > INT64_MAX for value in expected[2].values()):
                    raise CandidateRejected(
                        "Exact totals exceed ManifestCandidate int64 contract; "
                        "owner review required"
                    )
                declared = (
                    candidate.logical_row_digest,
                    candidate.row_count,
                    candidate.monetary_totals_by_currency,
                )
                if actual != expected or declared != expected:
                    raise CandidateRejected(
                        "Logical digest, row count or exact currency totals differ"
                    )
                different = one(
                    tx,
                    """SELECT EXISTS(SELECT 1 FROM m08_candidate_rows a
                    LEFT JOIN m08_candidate_rows b ON b.side='candidate' AND b.key=a.key
                    WHERE a.side='base' AND a.document IS DISTINCT FROM b.document) AS bad""",
                )["bad"]
                if different:
                    raise CandidateRejected("Candidate changed a logical row")
        except UniqueViolation as exc:
            raise CandidateRejected("Repeated Silver event ID or Gold logical key") from exc
        snapshot_id = str(uuid4())
        lineage = publication.write_lineage(
            pipeline,
            namespace,
            snapshot_id,
            {
                **publication.provenance(pipeline, namespace),
                "membership_files": [],
                "parent_input_manifest_ids": base.input_manifest_ids,
                "compaction": candidate.model_dump(mode="json"),
            },
        )
        generation = base.generation + 1
        now = datetime.now(UTC)
        manifests = {
            dataset: source.model_copy(
                update={
                    "generation": generation,
                    "parent_generation": source.generation,
                    "created_at": now,
                    "code_commit": pipeline.code_commit,
                }
            )
            for dataset, source in old.items()
        }
        manifests[supplied.dataset] = DatasetManifest(
            **{
                **supplied.model_dump(),
                "created_at": now,
                "code_commit": pipeline.code_commit,
                "input_manifest_ids": [lineage],
                "source_ranges": [
                    r.model_copy(update={"receipt_membership_ref": lineage})
                    for r in supplied.source_ranges
                ],
            }
        )
        publication.boundary("after_files_durable")
        with tx.transaction():
            publication.activate(tx, namespace, old, manifests)
            publication.boundary("before_manifest_swap")
        publication.boundary("after_manifest_swap")
        return manifests[supplied.dataset]
