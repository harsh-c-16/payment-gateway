"""CI-only bindings to Vichitr's provisioned streaming stack; no provider replacements."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from benchmarks.manual.verify_prompt6 import ROOT
from infra import postgres


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("export", "volume"))
    args = parser.parse_args()
    values = postgres.credentials()
    if args.action == "export":
        # URLs are neither printed nor uploaded as evidence.
        with Path(os.environ["GITHUB_ENV"]).open("a", encoding="utf-8") as output:
            output.write(
                "CATALOG_TEST_DATABASE_URL=" + postgres.database_url("catalog", values) + "\n"
            )
        return 0
    private = ROOT / "artifacts/ci-private"
    private.mkdir(parents=True, exist_ok=True)
    build = private / "build"
    build.mkdir(exist_ok=True)
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copyfile(ROOT / name, build / name)
    shutil.copyfile(ROOT / "infra/storage.Dockerfile", build / "Dockerfile")
    subprocess.run(["docker", "build", "-t", "group3-m04-storage:local", str(build)], check=True)
    # Reuse the owner's worker, network, named volume, secret and schema cache.
    overlay = private / "volume.json"
    overlay.write_text(
        json.dumps(
            {
                "services": {
                    "storage-check": {
                        "environment": {
                            "RUN_VERTICAL_LIVE_TESTS": "1",
                            "RUN_STORAGE_LIVE_TESTS": "1",
                            "M05_CODE_COMMIT": subprocess.check_output(
                                ["git", "rev-parse", "HEAD"], text=True
                            ).strip(),
                            "ANALYTICS_TEST_DATABASE_URL": postgres.database_url(
                                "analytics", values
                            ).replace("127.0.0.1", "postgres"),
                        },
                        "volumes": [
                            f"{ROOT.as_posix()}/benchmarks:/app/benchmarks:ro",
                            f"{ROOT.as_posix()}/analytics:/app/analytics:ro",
                            # Existing analytics tests import catalogue adapters
                            # that resolve their owning migration paths at import.
                            f"{ROOT.as_posix()}/migrations:/app/migrations:ro",
                            f"{ROOT.as_posix()}/artifacts:/app/artifacts",
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    command = ["docker", "compose", "--project-name", postgres.PROJECT]
    for file in (
        postgres.COMPOSE,
        ROOT / "infra/compose.streaming.yaml",
        ROOT / "infra/compose.storage.yaml",
        overlay,
    ):
        command.extend(["--file", str(file)])
    command.extend(
        [
            "run",
            "--rm",
            "--no-deps",
            "storage-check",
            "python",
            "-m",
            "benchmarks.manual.verify_prompt6",
            "--job",
            "volume",
            "--out",
            "artifacts/ci-volume",
        ]
    )
    env = {**os.environ, "POSTGRES_SECRETS_DIR": (postgres.RUNTIME / "secrets").as_posix()}
    return subprocess.run(command, env=env, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
