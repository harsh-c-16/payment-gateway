"""Freeze W-ANALYTICS layouts before execution: exact file lists, generations and query day.

python -m analytics.queries.layouts freeze --namespace NS --day YYYY-MM-DD --out FROZEN_JSON

Run once, after Vichitr's snapshot is drained, with his pipeline environment (CODE_COMMIT,
ANALYTICS_DATABASE_URL, LAKEHOUSE_ROOT). Compaction publishes through his publisher, so the
snapshot's active generations advance (the file records both); the small-file layout is
the generation active before, whose files are retained. Measured runs only read the frozen lists.

The expected digests are the small-file results, and freezing refuses any layout whose result
differs. They are independent of the layout under test, not of DuckDB.
"""

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from analytics.queries.suite import (
    LAYOUT_FOR_PARAMETERS,
    QUERIES,
    Layout,
    build_layouts,
    open_connection,
    result_digest,
    run_query,
)
from projectctl.artifacts import file_hash
from shared.contracts.analytics import FileDescriptor

DATASETS = ("silver", "gold")


def store_root():
    return Path(os.environ.get("LAKEHOUSE_ROOT", "artifacts/lakehouse"))


def freeze(pipeline, namespace, day, root):
    before = {d: pipeline.active_manifest(namespace, d).generation for d in DATASETS}
    layouts, built = build_layouts(pipeline, namespace)
    after = {d: pipeline.active_manifest(namespace, d).generation for d in DATASETS}
    connection = open_connection()
    digests = {}
    for query_id in QUERIES:
        results = {
            name: result_digest(run_query(connection, query_id, layout, root, day)[0])
            for name, layout in layouts.items()
        }
        if len(set(results.values())) != 1:
            raise ValueError(f"{query_id} differs across layouts: {results}")
        digests[query_id] = results["small_files"]
    connection.close()
    return {
        "schema_version": 1,
        "audit_kind": "W-ANALYTICS",
        "namespace": namespace,
        "query_day": day.date().isoformat(),
        "store_root": str(root),
        "generations_before": before,
        "generations_after": after,
        "candidate": built["candidate"],
        "layouts": {
            name: [f.model_dump(mode="json") for f in layout.files]
            for name, layout in layouts.items()
        },
        "expected_digests": digests,
    }


class Frozen:
    def __init__(self, document):
        if document.get("schema_version") != 1 or document.get("audit_kind") != "W-ANALYTICS":
            raise ValueError("not a frozen W-ANALYTICS layout file")
        self.document = document
        self.query_day = datetime.fromisoformat(document["query_day"]).replace(tzinfo=UTC)
        self.layouts = {
            name: Layout([FileDescriptor.model_validate(f) for f in files])
            for name, files in document["layouts"].items()
        }

    def layout_name(self, parameters):
        return LAYOUT_FOR_PARAMETERS[parameters["file_layout"], parameters["partitioning"]]

    def layout_for(self, context):
        return self.layouts[self.layout_name(context["parameters"])]

    def summary(self):
        keys = ("namespace", "query_day", "store_root", "generations_before", "generations_after")
        return {key: self.document[key] for key in keys} | {
            "files": {name: len(layout.files) for name, layout in self.layouts.items()}
        }


def load_frozen(path):
    return Frozen(json.loads(Path(path).read_text(encoding="utf-8")))


def verify_files(frozen, name):
    """Paths of the layout whose bytes differ from the frozen hashes; empty when intact."""
    root = Path(frozen.document["store_root"])
    if root.resolve() != store_root().resolve():
        return ["LAKEHOUSE_ROOT differs from the frozen store root"]
    return [
        f.path
        for f in frozen.layouts[name].files
        if not (root / f.path).is_file() or file_hash(root / f.path) != f.sha256
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("freeze")
    command.add_argument("--namespace", required=True)
    command.add_argument("--day", required=True, help="UTC query day, YYYY-MM-DD")
    command.add_argument("--out", required=True)
    arguments = parser.parse_args()
    from pipelines.ingestion.runtime import pipeline_from_env

    day = datetime.fromisoformat(arguments.day).replace(tzinfo=UTC)
    document = freeze(pipeline_from_env(), arguments.namespace, day, store_root())
    out = Path(arguments.out)
    if out.exists():
        raise SystemExit("refusing to overwrite a frozen layout file")
    out.write_text(json.dumps(document, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {"files": {k: len(v) for k, v in document["layouts"].items()}}
            | {
                k: document[k]
                for k in ("namespace", "query_day", "generations_before", "generations_after")
            }
        )
    )


if __name__ == "__main__":
    main()
