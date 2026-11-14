"""Prepare/activate a fresh presentation namespace without resetting retained data.

Explicit operator command only. Reuses the archived CSV, Harsh's importer and
Aditya's seed adapter. Old namespaces and the source-corruption evidence remain.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from benchmarks.failure_demo.runtime import Runtime
from infra import postgres, prototype, streaming

from .observer import Observer
from .recordings import write_json


def seed(source_hash):
    from pipelines.catalog.adapter import run_import
    from projectctl.providers import Invocation
    from services.inventory.adapter import inventory_seed

    namespace = os.environ["RUN_NAMESPACE"]
    if not namespace.startswith("bench-presentation-"):
        raise ValueError("A fresh isolated presentation namespace is required")
    paths = list((Path("/lakehouse/raw/catalog") / source_hash).glob("*.csv"))
    source = next(
        (p for p in paths if hashlib.sha256(p.read_bytes()).hexdigest() == source_hash), None
    )
    if source is None:
        raise ValueError("The retained source archive with the exact original hash is unavailable")
    out = Path("/journey-output/catalogue")
    report, timings = run_import(source, load_mode="copy", namespace=namespace, out=out)
    result = inventory_seed(
        Invocation(
            "inventory seed",
            {"profile": "performance", "seed": 42, "sku_manifest": str(out / "sku_manifest.json")},
            None,
            os.environ["RUN_ID"],
            namespace,
        )
    )
    if result.code != 0:
        raise RuntimeError("Owner-provided inventory seed adapter failed")
    write_json(
        Path("/journey-output/prepared.json"),
        {
            "namespace": namespace,
            "source_sha256": source_hash,
            "source_archive": str(source),
            "catalogue": report.model_dump(mode="json"),
            "timings": timings,
            "inventory_seed": [json.loads(v) for v in result.reasons],
            "mode": "real_owner_setup_adapters",
            "old_data_deleted": False,
        },
    )


def prepare():
    runtime = Runtime()
    observer = Observer(runtime, None)
    with_identity = observer.audit(
        "catalog",
        lambda tx: tx.execute(
            "SELECT source_hash FROM catalog_imports WHERE namespace=%s AND status='complete' "
            "ORDER BY completed_at DESC LIMIT 1",
            (runtime.namespace,),
        ).fetchone(),
    )
    if not with_identity:
        raise ValueError("An existing completed catalogue import is required")
    identity = str(uuid4())
    namespace = "bench-presentation-" + identity[:8]
    folder = postgres.ROOT / "artifacts/data-journey/presentation" / identity
    folder.mkdir(parents=True)
    context_path = prototype.RUNTIME / "context.json"
    original = json.loads(context_path.read_text("utf-8"))
    write_json(folder / "previous-context.json", original)
    streaming.provision_topics(namespace)
    values = {
        k: v
        for k, v in prototype.environment(host=False).items()
        if k.endswith("_DATABASE_URL") or k in {"CODE_COMMIT", "CATALOG_DATASET_REVISION"}
    }
    values.update(
        RUN_NAMESPACE=namespace,
        RUN_ID=identity,
        LAKEHOUSE_ROOT="/lakehouse",
        EVENT_SCHEMA_CACHE_PATH="/app/schema-cache.json",
        KAFKA_BOOTSTRAP_SERVERS="kafka:9092",
    )
    args = [
        "docker",
        "run",
        "--rm",
        "--label",
        "com.docker.compose.project=" + postgres.PROJECT,
        "--label",
        "group3.owner=jaineel",
        "--network",
        postgres.PROJECT + "_default",
        "--memory",
        "768m",
        "--cpus",
        "1",
        "--volumes-from",
        runtime.container("analytics-worker")["Id"],
    ]
    for directory in ("benchmarks", "projectctl", "configs", "infra", "services", "migrations"):
        args.extend(
            [
                "--mount",
                f"type=bind,source={postgres.ROOT / directory},target=/app/{directory},readonly",
            ]
        )
    args.extend(["--mount", f"type=bind,source={folder},target=/journey-output"])
    for key in sorted(values):
        args.extend(["-e", key])
    args.extend(
        [
            "group3-m04-storage:local",
            "python",
            "-m",
            "benchmarks.journey.presentation",
            "--seed",
            with_identity["source_hash"],
        ]
    )
    with (folder / "setup.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(
            args,
            env={**os.environ, **values},
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=600,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    if result.returncode or not (folder / "prepared.json").is_file():
        raise RuntimeError(
            "Fresh presentation preparation failed; original runtime context retained"
        )
    # Explicit operator activation changes only untracked runtime bindings.
    updated = {**original, "RUN_NAMESPACE": namespace, "RUN_ID": identity}
    previous_namespace = os.environ.get("RUN_NAMESPACE")
    try:
        write_json(context_path, updated)
        os.environ["RUN_NAMESPACE"] = namespace
        prototype.prepare(identity)
    except Exception:
        write_json(context_path, original)
        os.environ["RUN_NAMESPACE"] = original["RUN_NAMESPACE"]
        prototype.prepare(original["RUN_ID"])
        raise
    finally:
        if previous_namespace is None:
            os.environ.pop("RUN_NAMESPACE", None)
        else:
            os.environ["RUN_NAMESPACE"] = previous_namespace
    write_json(
        folder / "activation.json",
        {
            "previous_namespace": original["RUN_NAMESPACE"],
            "active_namespace": namespace,
            "status": "READY_TO_START",
            "retained_old_data": True,
        },
    )
    print(f"Prepared {namespace}; evidence: {folder.relative_to(postgres.ROOT)}", flush=True)
    print(
        "Run start-prototype.ps1, then start-failure-demo.ps1. Use a fresh browser session.",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare-and-activate", action="store_true")
    parser.add_argument("--seed")
    args = parser.parse_args()
    if args.seed and sys.platform == "linux":
        seed(args.seed)
    elif args.prepare_and_activate and sys.platform == "win32":
        prepare()
    else:
        parser.error("Choose the explicit Windows preparation action")


if __name__ == "__main__":
    main()
