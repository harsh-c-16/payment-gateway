"""Immutable observation frames and integrity-checked presentation playback."""

import hashlib
import json
import threading
from pathlib import Path
from uuid import UUID, uuid4

from .model import now

SCHEMA = "journey-observations-v1"


def write_json(path, value):
    raw = (json.dumps(value, indent=2, allow_nan=False, default=str) + "\n").encode("utf-8")
    temporary = path.with_name(path.name + "." + uuid4().hex + ".pending")
    temporary.write_bytes(raw)
    temporary.replace(path)
    return hashlib.sha256(raw).hexdigest()


class Recordings:
    def __init__(self, root, observe):
        self.root, self.observe = Path(root), observe
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock, self.stop_event = threading.RLock(), threading.Event()
        self.current = None

    def start(self):
        with self.lock:
            if self.current:
                raise ValueError("An observation recording is already running")
            identity = str(uuid4())
            folder = self.root / identity
            folder.mkdir()
            self.current = {
                "schema": SCHEMA,
                "id": identity,
                "started_at": now(),
                "completed_at": None,
                "status": "recording",
                "frames": [],
                "scope": "Recorded observations only; playback never sends business operations",
                "max_frames": 60,
                "interval_seconds": 5,
            }
            write_json(folder / "manifest.json", self.current)
            return self.summary(self.current)

    @staticmethod
    def summary(manifest):
        return {
            k: manifest.get(k) for k in ("id", "started_at", "completed_at", "status", "scope")
        } | {"frame_count": len(manifest["frames"])}

    def capture(self):
        with self.lock:
            if not self.current:
                return
            identity = self.current["id"]
        frame = self.observe()
        with self.lock:
            if not self.current or self.current["id"] != identity:
                return
            index = len(self.current["frames"])
            folder = self.root / identity
            name = f"frame-{index:03}.json"
            digest = write_json(folder / name, frame)
            self.current["frames"].append(
                {"file": name, "sha256": digest, "observed_at": frame["observed_at"]}
            )
            write_json(folder / "manifest.json", self.current)
            if index + 1 >= self.current["max_frames"]:
                self.finish("frame_limit_reached")

    def finish(self, status="saved"):
        with self.lock:
            if not self.current:
                return None
            self.current.update(status=status, completed_at=now())
            write_json(self.root / self.current["id"] / "manifest.json", self.current)
            result = self.summary(self.current)
            self.current = None
            return result

    def list(self):
        output = []
        for path in sorted(
            self.root.glob("*/manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True
        )[:30]:
            try:
                manifest = json.loads(path.read_text("utf-8"))
                output.append(self.summary(manifest))
            except (OSError, ValueError, KeyError):
                continue
        return output

    def read(self, identity):
        folder = self.root / str(UUID(str(identity)))
        with self.lock:
            manifest = json.loads((folder / "manifest.json").read_text("utf-8"))
            frames = []
            for index, descriptor in enumerate(manifest["frames"]):
                if descriptor["file"] != f"frame-{index:03}.json":
                    raise ValueError("Invalid recording frame name")
                raw = (folder / descriptor["file"]).read_bytes()
                if hashlib.sha256(raw).hexdigest() != descriptor["sha256"]:
                    raise ValueError("Recorded evidence hash mismatch")
                frames.append(json.loads(raw))
        return {**manifest, "frames": frames, "integrity": "verified_sha256"}

    def monitor(self):
        while not self.stop_event.wait(5):
            try:
                self.capture()
            except Exception:
                self.finish("observation_failed")

    def shutdown(self):
        self.stop_event.set()
        self.finish("saved_on_shutdown")
