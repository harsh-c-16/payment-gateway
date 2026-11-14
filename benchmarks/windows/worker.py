"""Internal Docker Desktop provider process, launched only by the Windows controller."""

import argparse
import os
import resource
from pathlib import Path

from benchmarks.windows.evidence import write
from benchmarks.windows.measure import batching, compaction, imports, save_rows, searches


def main():
    parser = argparse.ArgumentParser()
    for name in ("repetitions", "executions", "events", "publications", "queries-per-stratum"):
        parser.add_argument("--" + name, type=int, required=True)
    args = parser.parse_args()
    if os.name != "posix" or not Path("/evidence").is_mount():
        raise RuntimeError("Internal provider requires the disposable Docker Desktop data volume")
    args.out, args.source = Path("/evidence"), Path("/input.csv")
    os.environ["LAKEHOUSE_ROOT"] = "/evidence/import-archive"
    status, rows = {"status": "RUNNING"}, []
    try:
        for operation in (imports, searches, batching, compaction):
            status["stage"] = operation.__name__
            operation(os.environ["WINDOWS_MEASURE_DATABASE"], args, rows)
        status["status"] = "COMPLETED"
    except Exception as error:
        status.update(status="FAILED", error_type=type(error).__name__, message=str(error))
        print("Provider stage failed: " + type(error).__name__, flush=True)
        return 1
    finally:
        save_rows(args.out, rows)
        status["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        status["cgroup"] = {
            name: (Path("/sys/fs/cgroup") / name).read_text()
            for name in ("memory.events", "memory.peak", "memory.max", "cpu.max", "cpu.stat")
        }
        write(args.out / "worker-status.json", status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
