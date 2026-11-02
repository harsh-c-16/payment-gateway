"""D-03 catalogue-import fault hooks for the harness FaultGate: arm, wait, stop, restart.

The child imports until the named boundary, acknowledges it, then waits to be killed. It runs only
with FAULT_INJECTION_ENABLED=true in an isolated bench namespace and takes no commands.
"""

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from pipelines.catalog.adapter import run_import

BARRIER = "after_staging_chunk_commit_before_promotion"
TARGET = "catalog-import"


class CatalogImportFaults:
    def __init__(self, source, out, *, url=None, load_mode="copy"):
        self.source, self.out, self.url, self.load_mode = Path(source), Path(out), url, load_mode
        self.child = None

    async def arm(self, context, barrier, target):
        if barrier != BARRIER or target != TARGET:
            raise ValueError("unknown catalogue fault boundary")
        self.child = await asyncio.to_thread(
            subprocess.Popen,
            [
                sys.executable,
                "-m",
                "pipelines.catalog.faults",
                str(self.source),
                str(self.out),
                context["namespace"],
                self.load_mode,
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
        report, _ = await asyncio.to_thread(
            run_import,
            self.source,
            load_mode=self.load_mode,
            namespace=context["namespace"],
            out=self.out,
            url=self.url,
        )
        return {
            "namespace": context["namespace"],
            "run_id": context["run_id"],
            "target": TARGET,
            "ready": report.status in {"promoted", "noop"},
            "retained_volume": True,
            "chunks_resumed": report.chunks_resumed,
        }


def child(source, out, namespace, load_mode):
    if os.environ.get("FAULT_INJECTION_ENABLED") != "true" or not namespace.startswith("bench-"):
        raise SystemExit("fault hooks are disabled outside isolated benchmark namespaces")

    def hook(stage):
        if stage == "after_chunk_commit":
            print("BARRIER " + BARRIER, flush=True)
            sys.stdin.read()

    run_import(Path(source), load_mode=load_mode, namespace=namespace, out=out, hook=hook)


if __name__ == "__main__":
    child(*sys.argv[1:5])
