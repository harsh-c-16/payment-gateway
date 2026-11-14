"""Enable only local hook support; fault plans remain empty until explicit Trigger."""

import argparse
import json
import os
import subprocess
import time

from infra import postgres, prototype, retrieval

from .runtime import Runtime, Unavailable


def configure(enabled):
    runtime = Runtime()
    for service in ("orders", "payments"):
        runtime.container(service)
    folder = postgres.ROOT / "artifacts/failure-demo"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "hooks.compose.yaml"
    value = "true" if enabled else "false"
    path.write_text(
        "services:\n"
        + "".join(
            f'  {role}:\n    environment:\n      LOCAL_FAILURE_DEMOS_ENABLED: "{value}"\n'
            for role in ("orders", "payments")
        ),
        encoding="utf-8",
    )
    files = prototype.FILES + (("compose.retrieval.yaml",) if retrieval.enabled() else ())
    args = [
        "docker",
        "compose",
        "--project-name",
        postgres.PROJECT,
        *[arg for name in files for arg in ("--file", str(postgres.ROOT / "infra" / name))],
        "--file",
        str(path),
        "up",
        "-d",
        "--no-deps",
        "orders",
        "payments",
    ]
    result = subprocess.run(
        args,
        cwd=postgres.ROOT,
        env={**os.environ, **prototype.environment()},
        capture_output=True,
        timeout=150,
    )
    if result.returncode:
        raise Unavailable("Local hook support configuration failed (service output withheld)")
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        if all(runtime.health(role) is True for role in ("orders", "payments")):
            break
        time.sleep(0.5)
    else:
        raise Unavailable("Orders/Payments readiness did not recover within 40 seconds")
    (folder / "hook-support.json").write_text(
        json.dumps(
            {
                "enabled": enabled,
                "faults_active": False,
                "scope": "Orders/Payments internal APIs; explicit run plans required",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        "Local failure hook support "
        + ("enabled" if enabled else "disabled")
        + ". No checkout submitted; no fault armed."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("enable", "disable"))
    configure(parser.parse_args().action == "enable")
