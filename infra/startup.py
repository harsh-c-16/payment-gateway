"""Bounded retries for idempotent setup probes, with credential-free attempt evidence."""

import json
from datetime import UTC, datetime
from time import monotonic, sleep

import httpx
import psycopg
from confluent_kafka import KafkaException

from infra.postgres import SetupError


class StartupFailure(SetupError):
    pass


def transient(error):
    if isinstance(error, httpx.TransportError):
        return True
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code in {429, 500, 502, 503, 504}
    if isinstance(error, psycopg.OperationalError):
        return (
            error.sqlstate is None or error.sqlstate.startswith("08") or error.sqlstate == "57P03"
        )
    if isinstance(error, KafkaException):
        return bool(error.args and error.args[0].retriable())
    return isinstance(error, TimeoutError)


class StartupChecks:
    def __init__(self, path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def __call__(self, stage, operation, *, retry=False):
        limit = 3 if retry else 1
        for attempt in range(1, limit + 1):
            started = monotonic()
            row = {
                "stage": stage,
                "attempt": attempt,
                "max_attempts": limit,
                "started_at": datetime.now(UTC).isoformat(),
            }
            self.record(row | {"status": "STARTED"}, started)
            try:
                result = operation()
            except Exception as error:
                again = retry and transient(error) and attempt < limit
                row.update(status="RETRY" if again else "FAILED", error_type=type(error).__name__)
                if isinstance(error, psycopg.Error):
                    row["sqlstate"] = error.sqlstate
                if isinstance(error, httpx.HTTPStatusError):
                    row["http_status"] = error.response.status_code
                self.record(row, started)
                if not again:
                    detail = str(error) if isinstance(error, SetupError) else type(error).__name__
                    raise StartupFailure(
                        f"Startup stage {stage} failed after {attempt} attempt(s): "
                        f"{detail}; diagnostics: {self.path.name}"
                    ) from None
                sleep(attempt)
            else:
                row["status"] = "PASSED"
                self.record(row, started)
                return result

    def record(self, row, started):
        row["elapsed_seconds"] = monotonic() - started
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
