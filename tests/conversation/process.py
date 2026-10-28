"""Spawn/restart an actual loopback service process using explicit test bindings."""

import os
import socket
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from time import monotonic, sleep

import httpx

ROOT = Path(__file__).resolve().parents[2]


@contextmanager
def server(
    database, log_path, *, workflow=False, lose_order_response=False, catalog_unavailable=False
):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = os.environ.copy()
    environment["P6_TEST_DATABASE_URL"] = database.url
    command = [
        sys.executable,
        "-m",
        "tests.conversation.server",
        "--port",
        str(port),
        "--test-double-events",
    ]
    if workflow:
        command.append("--test-double-workflow")
    if lose_order_response:
        command.append("--lose-order-response")
    if catalog_unavailable:
        command.append("--catalog-unavailable")
    with Path(log_path).open("ab") as log:
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
        child = subprocess.Popen(
            command, cwd=ROOT, env=environment, stdout=log, stderr=subprocess.STDOUT, **options
        )
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=3
            ) as client:
                deadline = monotonic() + 30
                while True:
                    if child.poll() is not None:
                        raise RuntimeError("P6 test server exited; inspect captured log")
                    try:
                        if client.get("/health/ready").status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    if monotonic() >= deadline:
                        raise RuntimeError("P6 test server not ready; inspect captured log")
                    sleep(0.05)
                yield client, child.pid, command
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
