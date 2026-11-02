"""Compaction fault hooks for the harness FaultGate: arm, wait, stop, restart.

The child writes a candidate from a pinned manifest, acknowledges the boundary, then waits to be
killed before anything is published. It runs only with FAULT_INJECTION_ENABLED=true in an isolated
bench namespace. Mapping this boundary to a case is still to be agreed with the harness owner.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from analytics.compaction.compact import compact_snapshot
from pipelines.storage import FileStore
from shared.contracts.analytics import DatasetManifest

BARRIER = "after_candidate_files_before_publish"
TARGET = "compaction"


def output_prefix(namespace, dataset):
    return f"candidate/{namespace}/{uuid4()}/{dataset}"


class CompactionFaults:
    def __init__(self, pipeline, store_root, dataset, work_dir):
        self.pipeline, self.store_root, self.dataset = pipeline, Path(store_root), dataset
        self.work_dir = Path(work_dir)
        self.child = self.pinned = None

    async def arm(self, context, barrier, target):
        if barrier != BARRIER or target != TARGET:
            raise ValueError("unknown compaction fault boundary")
        namespace = context["namespace"]
        self.pinned = self.pipeline.active_manifest(namespace, self.dataset)
        self.work_dir.mkdir(parents=True, exist_ok=True)
        path = self.work_dir / f"pinned-{uuid4()}.json"
        path.write_text(self.pinned.model_dump_json(), encoding="utf-8")
        self.child = await asyncio.to_thread(
            subprocess.Popen,
            [
                sys.executable,
                "-m",
                "analytics.compaction.faults",
                str(self.store_root),
                str(path),
                namespace,
                self.dataset,
            ],
            stdout=subprocess.PIPE,
            stdin=subprocess.PIPE,
            text=True,
            env={**os.environ, "FAULT_INJECTION_ENABLED": "true"},
        )
        return {"barrier": barrier, "target": target}

    async def wait(self, context, receipt):
        line = await asyncio.to_thread(self.child.stdout.readline)
        return {
            "namespace": context["namespace"],
            "run_id": context["run_id"],
            "case_id": context["case_id"],
            "target": receipt["target"],
            "barrier": receipt["barrier"],
            "receipt_id": str(uuid4()),
            "acknowledged": line.strip() == "BARRIER " + BARRIER,
        }

    async def stop(self, context, acknowledgement):
        await asyncio.to_thread(self.child.kill)
        await asyncio.to_thread(self.child.wait)
        return {"stopped": True}

    async def restart(self, context, acknowledgement):
        """The killed attempt's files are never referenced, so a fresh candidate is the recovery."""
        namespace = context["namespace"]
        unchanged = (
            self.pipeline.active_manifest(namespace, self.dataset).generation
            == self.pinned.generation
        )
        candidate = await asyncio.to_thread(
            compact_snapshot,
            self.pipeline.store,
            self.pinned,
            output_prefix=output_prefix(namespace, self.dataset),
        )
        published = await asyncio.to_thread(self.pipeline.publish_candidate, candidate)
        return {
            "namespace": namespace,
            "run_id": context["run_id"],
            "target": TARGET,
            "ready": unchanged and published.generation == self.pinned.generation + 1,
            "retained_volume": True,
            "active_unchanged_by_killed_attempt": unchanged,
            "published_generation": published.generation,
        }


def child(store_root, manifest_path, namespace, dataset):
    if os.environ.get("FAULT_INJECTION_ENABLED") != "true" or not namespace.startswith("bench-"):
        raise SystemExit("fault hooks are disabled outside isolated benchmark namespaces")
    manifest = DatasetManifest.model_validate_json(Path(manifest_path).read_text(encoding="utf-8"))
    compact_snapshot(
        FileStore(Path(store_root)), manifest, output_prefix=output_prefix(namespace, dataset)
    )
    print("BARRIER " + BARRIER, flush=True)
    sys.stdin.read()


if __name__ == "__main__":
    child(*sys.argv[1:5])
