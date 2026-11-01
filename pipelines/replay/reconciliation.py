"""Compare pinned logical rows, excluding only analytical execution provenance."""

from collections import defaultdict

from pipelines.curation.db import rows
from pipelines.storage.candidates import KEYS, _money, digest_sorted_rows
from pipelines.storage.parquet import iter_verified
from pipelines.storage.publication import ROW_MAX_BYTES, stream_rows
from pipelines.storage.readers import _wire
from shared.contracts.analytics import DatasetManifest, ReconciliationResult
from shared.contracts.common import INT64_MAX
from shared.contracts.events import EVENTS
from shared.event_transport.schemas import canonical_json

EXECUTION_FIELDS = {"namespace", "revision", "transform_version", "publication_generation"}


def semantic_row(schema, row):
    if schema in {"silver-conversation-turn", "silver-events-v1"}:
        fields = EVENTS[row["event_type"]][4].model_fields
        payload = row["payload"] if schema == "silver-events-v1" else row
        value = {
            "event_id": row["event_id"],
            "content_hash": row["content_hash"],
            "payload": {name: payload.get(name) for name in fields},
        }
        return "silver", row["event_id"], value
    if schema not in KEYS:
        raise ValueError("Unsupported replay reference schema")
    value = {k: v for k, v in row.items() if k not in EXECUTION_FIELDS}
    key = canonical_json(_wire([row[k] for k in KEYS[schema]])).decode()
    return schema, key, value


def _stage(pipeline, tx, manifest, side):
    totals, count = defaultdict(int), 0
    with tx.cursor().copy(
        "COPY replay_compare(side,dataset,schema_name,logical_key,document) FROM STDIN"
    ) as copy:
        for descriptor in manifest.files:
            for row in iter_verified(pipeline.store, descriptor):
                if row["namespace"] != manifest.namespace:
                    raise ValueError("Replay reference row has a different namespace")
                schema, key, value = semantic_row(descriptor.schema_name, row)
                if (schema == "silver") != (manifest.dataset == "silver"):
                    raise ValueError("Replay reference dataset/schema mismatch")
                document = canonical_json(["m10-semantic-v1", schema, _wire(value)])
                if len(document) > ROW_MAX_BYTES:
                    raise ValueError("Replay comparison row exceeds the existing 8 MiB bound")
                copy.write_row((side, manifest.dataset, schema, key, document))
                _money(value, totals)
                count += 1
    return {"rows": count, "money": dict(totals)}


def reconcile(pipeline, tx, job, counts):
    references = rows(
        tx,
        """SELECT m.manifest FROM replay_references r
        JOIN snapshot_manifests m USING(namespace,dataset,generation)
        WHERE r.replay_id=%s ORDER BY r.dataset""",
        (job["replay_id"],),
    )
    if not references:
        return None  # Capture-only jobs have no independent published Gold reference.
    report = {
        "source_manifest_ids": job["request"]["source_manifest_ids"],
        "reference_transform": {},
        "target_transform": job["transform_version"],
        "datasets": {},
    }
    with tx.transaction():
        tx.execute("SET LOCAL work_mem='4MB'")
        tx.execute("""CREATE TEMP TABLE replay_compare(
            side text,dataset text,schema_name text,logical_key text,document bytea,
            PRIMARY KEY(side,dataset,schema_name,logical_key)) ON COMMIT DROP""")
        for reference in references:
            manifest = DatasetManifest.model_validate(reference["manifest"])
            dataset = manifest.dataset
            report["reference_transform"][dataset] = manifest.transform_version
            target = pipeline.active_manifest(job["target_namespace"], dataset)
            report["datasets"][dataset] = {
                "reference": _stage(pipeline, tx, manifest, "reference"),
                "target": _stage(pipeline, tx, target, "target"),
            }
            for side in ("reference", "target"):
                documents = (
                    r["document"]
                    for r in stream_rows(
                        tx,
                        """SELECT document FROM replay_compare
                        WHERE side=%s AND dataset=%s ORDER BY document""",
                        (side, dataset),
                    )
                )
                report["datasets"][dataset][side]["sha256"] = digest_sorted_rows(documents)
        mismatch = rows(
            tx,
            """SELECT coalesce(a.dataset,b.dataset) AS dataset,
            coalesce(a.logical_key,b.logical_key) AS logical_key,
            CASE WHEN a.document IS NULL THEN 'unexpected' WHEN b.document IS NULL
                THEN 'missing' ELSE 'conflicting' END AS kind
            FROM (SELECT * FROM replay_compare WHERE side='reference') a
            FULL JOIN (SELECT * FROM replay_compare WHERE side='target') b
            USING(dataset,schema_name,logical_key) WHERE a.document IS DISTINCT FROM b.document
            ORDER BY dataset,logical_key LIMIT 1001""",
        )
        failures = []
        if any(r["dataset"] == "gold" for r in mismatch):
            failures.append("Pinned Gold counts/states/money/logical rows differ")
        if len(mismatch) > 1000:
            failures.append("Diagnostic examples capped at 1000; full dataset digests retained")
        totals = defaultdict(int)
        for item in report["datasets"].values():
            for currency, amount in item["target"]["money"].items():
                totals[currency] += amount
        if any(amount > INT64_MAX for amount in totals.values()):
            failures.append(
                "Exact monetary integrity sums exceed the frozen reconciliation DTO int64 bound"
            )
        result = ReconciliationResult(
            passed=not mismatch and not failures,
            counts_by_disposition=counts,
            **{
                kind + "_ids": [
                    r["logical_key"]
                    for r in mismatch[:1000]
                    if r["dataset"] == "silver" and r["kind"] == kind
                ]
                for kind in ("missing", "unexpected", "conflicting")
            },
            totals_by_currency={c: v for c, v in totals.items() if v <= INT64_MAX},
            invariant_failures=failures,
            source_manifest_ids=job["request"]["source_manifest_ids"],
        )
    report["reconciliation"] = result.model_dump(mode="json")
    path = f"replays/{job['replay_id']}/semantic.json"
    data = canonical_json(report)
    import hashlib

    pipeline.store.write_immutable(path, data, hashlib.sha256(data).hexdigest())
    return result
