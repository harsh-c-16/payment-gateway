"""Owner-run I0/I1 comparison on one host, each trial in a fresh schema.

This is not the P9 runner: it has no frozen resource limits. Results are labelled accordingly.

    python -m pipelines.catalog.experiments import --out DIR
"""

import argparse
import json
import os
import platform
import random
import subprocess
import sys
from pathlib import Path
from statistics import median
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from pipelines.catalog.adapter import database_url, run_import

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data/raw/flipkart_com-ecommerce_sample.csv"
REPETITIONS, SEED = 3, 42


def git_state():
    def git(*arguments):
        return subprocess.run(
            ["git", *arguments], capture_output=True, text=True, cwd=ROOT, check=False
        ).stdout.strip()

    return {"commit": git("rev-parse", "HEAD"), "dirty": bool(git("status", "--porcelain"))}


def host_facts():
    memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    return {
        "git": git_state(),
        "cpu_count": os.cpu_count(),
        "total_memory_bytes": memory,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "resource_limits": "none enforced; not the frozen local4c8g profile",
    }


def create_schema():
    schema = "exp_" + uuid4().hex
    with psycopg.connect(database_url(), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    return schema


def drop_schema(schema):
    assert schema.startswith("exp_")
    with psycopg.connect(database_url(), autocommit=True) as admin:
        admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def write_json(path, document):
    Path(path).write_text(json.dumps(document, indent=2, default=str) + "\n", encoding="utf-8")


def import_one(arguments):
    """Runs in its own process so CPU time and peak RSS belong to this repetition alone."""
    _, timings = run_import(
        Path(arguments.source),
        load_mode=arguments.mode,
        namespace=arguments.namespace,
        out=arguments.out,
        url=make_conninfo(database_url(), options=f"-c search_path={arguments.schema},public"),
    )
    print(json.dumps(timings))


def run_import_experiment(arguments):
    out = Path(arguments.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(SEED)
    runs = []
    for repetition in range(1, REPETITIONS + 1):
        order = ["row", "copy"]
        rng.shuffle(order)
        for mode in order:
            schema = create_schema()
            namespace = f"bench-import-{mode}-{repetition}"
            try:
                child = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pipelines.catalog.experiments",
                        "import-one",
                        "--source",
                        str(arguments.source),
                        "--mode",
                        mode,
                        "--namespace",
                        namespace,
                        "--schema",
                        schema,
                        "--out",
                        str(out / f"rep{repetition}-{mode}"),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                    cwd=ROOT,
                )
                timings = json.loads(child.stdout.strip().splitlines()[-1])
            finally:
                drop_schema(schema)
            timings["repetition"] = repetition
            runs.append(timings)
            print(
                f"rep {repetition} {mode}: total {timings['raw_to_ready_seconds']:.2f}s, "
                f"staging {timings['stages']['staging_seconds']:.3f}s",
                flush=True,
            )
    digests = {run["logical_digest"] for run in runs}
    summary = {
        "workload": "W-IMPORT",
        "profile": "owner-local; not the frozen profile or the P9 runner",
        "host": host_facts(),
        "repetitions": REPETITIONS,
        "digests_equal": len(digests) == 1,
        "logical_digest": sorted(digests),
        "variants": {},
        "runs": runs,
    }
    for mode, variant in (("row", "I0"), ("copy", "I1")):
        chosen = [run for run in runs if run["load_mode"] == mode]
        staging = [run["stages"]["staging_seconds"] for run in chosen]
        total = [run["raw_to_ready_seconds"] for run in chosen]
        summary["variants"][variant] = {
            "load_mode": mode,
            "staging_seconds": {
                "median": median(staging),
                "min": min(staging),
                "max": max(staging),
            },
            "total_seconds": {"median": median(total), "min": min(total), "max": max(total)},
            "canonical_rows_per_staging_second": 19998 / median(staging),
            "raw_rows_per_total_second": 20000 / median(total),
            "wal_bytes": median(run["wal_bytes"] for run in chosen),
            "client_peak_rss_kib": max(run["client_peak_rss_kib"] for run in chosen),
            "client_cpu_seconds": median(run["client_cpu_seconds"] for run in chosen),
        }
    write_json(out / "summary.json", summary)
    print(json.dumps(summary["variants"], indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("import")
    command.add_argument("--out", required=True)
    command.add_argument("--source", default=str(SOURCE))
    one = commands.add_parser("import-one")
    for flag in ("--source", "--mode", "--namespace", "--schema", "--out"):
        one.add_argument(flag, required=True)
    arguments = parser.parse_args()
    if arguments.command == "import":
        run_import_experiment(arguments)
    else:
        import_one(arguments)


if __name__ == "__main__":
    main()
