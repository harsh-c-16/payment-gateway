"""Routes installed into the existing exact-origin loopback controller."""

import threading
from copy import copy
from typing import Literal
from uuid import UUID

from fastapi import HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictBool

from .lab import Lab
from .observer import Observer
from .recordings import Recordings


class FixtureAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Literal[
        "race", "duplicate", "conflict", "out_of_order", "late_event", "malformed", "replay"
    ]
    confirmed: StrictBool = False


def install(app, controller, infrastructure):
    root = controller.evidence.parent / "data-journey"
    observer = Observer(controller.runtime, infrastructure)
    lab = Lab(controller.runtime, root / "lab")
    observers = {controller.runtime.namespace: observer}
    recording_namespace = None

    def scoped(namespace):
        namespace = namespace or controller.runtime.namespace
        allowed = {controller.runtime.namespace, *(r["namespace"] for r in lab.history())}
        if namespace not in allowed:
            raise HTTPException(404, "Namespace is not a known local demonstration")
        if namespace not in observers:
            from benchmarks.windows.infrastructure import Infrastructure

            runtime = copy(controller.runtime)
            runtime.namespace = namespace
            observers[namespace] = Observer(runtime, Infrastructure(namespace))
        return observers[namespace]

    def snapshot(namespace=None):
        result = scoped(namespace).snapshot()
        result["lab"] = lab.state()
        run = selected_run(result["namespace"])
        result["workload"] = run
        attach(result, run)
        result["recording"] = recordings.summary(recordings.current) if recordings.current else None
        return result

    def selected_run(namespace):
        for saved in lab.history():
            if saved["namespace"] == namespace:
                return lab.evidence(saved["id"])
        return None

    def attach(result, run):
        if not run or run.get("namespace") != result.get("namespace"):
            return
        from .model import latency_summary, timeline

        emissions = {
            tuple(e["source"][k] for k in ("topic", "partition", "offset")): e
            for e in run.get("emissions", [])
            if e.get("source")
        }
        requests = {r["order_id"]: r for r in run.get("requests", []) if r.get("order_id")}
        for event in result.get("events", []):
            source = event.get("source")
            emission = (
                emissions.get(tuple(source[k] for k in ("topic", "partition", "offset")))
                if source
                else None
            )
            if emission:
                event["scheduled_at"] = emission.get("scheduled_at")
                event["broker_acked_at"] = emission.get("broker_acked_at")
            submitted = requests.get(event.get("payload", {}).get("order_id"))
            if submitted:
                event["request_submitted_at"] = submitted.get("submitted_at")
        result["latency"] = latency_summary(result.get("events", []), result.get("clock", {}))
        if "timelines" in result:
            result["timelines"] = {
                e["key"]: timeline(e, result.get("clock", {})) for e in result["events"]
            }

    recordings = Recordings(root / "recordings", lambda: snapshot(recording_namespace))
    app.state.journey = observer
    app.state.journey_recordings = recordings
    app.state.journey_lab = lab

    @app.get("/journey/snapshot")
    def observations(namespace: str | None = Query(default=None, max_length=62)):
        return snapshot(namespace)

    @app.get("/journey/trace")
    def trace(
        kind: Literal["order", "search", "event"],
        id: UUID,
        namespace: str | None = Query(default=None, max_length=62),
    ):
        result = scoped(namespace).trace(kind, str(id))
        attach(result, selected_run(result["namespace"]))
        return result

    @app.get("/journey/recordings")
    def previous():
        return {"recordings": recordings.list(), "lab_runs": lab.history()}

    @app.post("/journey/recordings/start", status_code=201)
    def record(namespace: str | None = Query(default=None, max_length=62)):
        nonlocal recording_namespace
        try:
            selected = scoped(namespace)
            with recordings.lock:
                result = recordings.start()
                recording_namespace = selected.runtime.namespace
            threading.Thread(target=recordings.capture, daemon=True).start()
            return result
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/journey/recordings/stop")
    def stop_recording():
        return recordings.finish()

    @app.get("/journey/recordings/{identity}")
    def recording(identity: UUID):
        try:
            return recordings.read(str(identity))
        except FileNotFoundError as exc:
            raise HTTPException(404, "Recorded observations not found") from exc
        except ValueError as exc:
            raise HTTPException(409, "Recording integrity check failed") from exc

    @app.get("/journey/lab")
    def scenarios():
        return lab.state()

    @app.post("/journey/lab/start", status_code=202)
    def start(body: FixtureAction):
        try:
            return lab.start(body.scenario, body.confirmed)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/journey/lab/{identity}/recover")
    def recover(identity: UUID):
        try:
            return lab.recover(str(identity))
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/journey/lab/{identity}")
    def evidence(identity: UUID):
        try:
            return JSONResponse(lab.evidence(str(identity)))
        except FileNotFoundError as exc:
            raise HTTPException(404, "Fixture evidence not found") from exc

    return recordings, lab
