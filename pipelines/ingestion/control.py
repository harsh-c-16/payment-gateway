"""Private container-local consumer control; no HTTP endpoint or process suspension."""

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import monotonic, sleep

from pydantic import Field

from pipelines.ingestion.lifecycle import isolated_namespace
from shared.contracts.common import Identifier, UTCTime, UUIDText, WireModel

REQUEST = Path("/tmp/analytics-consumer-control.json")
ACK = Path("/tmp/analytics-consumer-control.ack.json")


class PauseRequest(WireModel):
    namespace: str
    run_id: Identifier
    request_id: UUIDText
    pause_seconds: float = Field(strict=True, ge=0, le=30, allow_inf_nan=False)
    expires_at: UTCTime


def enabled():
    return all(
        os.environ.get(name, "false").lower() == "true"
        for name in ("BENCHMARK_MODE", "FAULT_INJECTION_ENABLED")
    )


def validate_scope(request, namespace, run_id):
    isolated_namespace(request.namespace)
    if (request.namespace, request.run_id) != (namespace, run_id):
        raise ValueError("Consumer control belongs to a different run")


def atomic_json(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value), encoding="utf-8")
    temporary.replace(path)


class ConsumerControl:
    def __init__(self, namespace, run_id):
        self.namespace, self.run_id = namespace, run_id
        self.active = enabled()
        self.request_id = self.deadline = None
        self.last_ack = None

    def tick(self, group):
        if not self.active:
            return False
        if not REQUEST.exists():
            group.set_fetch_paused(False)
            return False
        if REQUEST.stat().st_size > 4096:
            raise ValueError("Consumer control request exceeds its bound")
        request = PauseRequest.model_validate_json(REQUEST.read_bytes())
        validate_scope(request, self.namespace, self.run_id)
        if request.request_id != self.request_id:
            remaining = (request.expires_at - datetime.now(UTC)).total_seconds()
            if remaining > 35:
                raise ValueError("Consumer control expiry is outside the short lease")
            self.deadline = monotonic() + max(0, min(request.pause_seconds, remaining))
            self.request_id = request.request_id
        paused = monotonic() < self.deadline
        group.set_fetch_paused(paused)
        state = (self.request_id, paused)
        if state != self.last_ack:
            atomic_json(
                ACK,
                {
                    "namespace": self.namespace,
                    "run_id": self.run_id,
                    "request_id": self.request_id,
                    "paused": paused,
                    "observed_at": datetime.now(UTC).isoformat(),
                },
            )
            self.last_ack = state
        return paused


def request_and_wait(document):
    if not enabled():
        raise ValueError("Both benchmark fault flags must be enabled")
    request = PauseRequest.model_validate(document)
    validate_scope(request, os.environ["RUN_NAMESPACE"], os.environ["RUN_ID"])
    atomic_json(REQUEST, request.model_dump(mode="json"))
    deadline = monotonic() + 10
    while monotonic() < deadline:
        if ACK.exists():
            ack = json.loads(ACK.read_text(encoding="utf-8"))
            if (
                ack.get("request_id") == request.request_id
                and ack.get("namespace") == request.namespace
                and ack.get("run_id") == request.run_id
                and ack.get("paused") is (request.pause_seconds > 0)
            ):
                return ack
        sleep(0.05)
    raise TimeoutError("Consumer did not acknowledge the requested fetch state")


if __name__ == "__main__":
    print(json.dumps(request_and_wait(json.loads(sys.argv[1]))))
