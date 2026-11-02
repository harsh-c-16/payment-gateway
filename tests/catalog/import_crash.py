"""Child process that dies without cleanup at a named import boundary (D-03)."""

import os
import sys
from pathlib import Path

from pipelines.catalog.adapter import run_import


def main():
    source, out, url, namespace, boundary, mode = sys.argv[1:7]
    seen = {"after_chunk_commit": 0}

    def hook(stage):
        if stage == boundary:
            seen[stage] = seen.get(stage, 0) + 1
            if stage == "before_promotion" or seen[stage] == 2:
                print("BARRIER " + stage, flush=True)
                os._exit(42)

    run_import(Path(source), load_mode=mode, namespace=namespace, out=out, url=url, hook=hook)
    sys.exit(0)


if __name__ == "__main__":
    main()
