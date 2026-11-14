"""Semantic deployment isolation and tamper checks; network/Docker calls are explicit doubles."""

import hashlib
import io
import json

import pytest

from infra import prototype, retrieval


def test_download_uses_pinned_revision_and_never_replaces_good_files(monkeypatch, tmp_path):
    lock = {
        "model_id": "test/encoder",
        "revision": "frozen",
        "files": {
            "model.onnx": {
                "source": "onnx/model.onnx",
                "sha256": hashlib.sha256(b"good").hexdigest(),
            },
        },
    }
    monkeypatch.setattr(retrieval, "load_lock", lambda: lock)
    requested = []

    def download(url, timeout):
        requested.append(url)
        return io.BytesIO(b"wrong")

    monkeypatch.setattr(retrieval.urllib.request, "urlopen", download)
    with pytest.raises(ValueError, match="differs from the model lock"):
        retrieval.download_model(tmp_path)
    assert not (tmp_path / "model.onnx").exists()
    assert not list(tmp_path.glob("*.download"))
    assert requested == ["https://huggingface.co/test/encoder/resolve/frozen/onnx/model.onnx"]
    (tmp_path / "model.onnx").write_bytes(b"good")
    retrieval.download_model(tmp_path)
    assert len(requested) == 1


def test_provisioned_retrieval_is_retained_by_launcher_with_correct_memory(monkeypatch, tmp_path):
    settings = tmp_path / "retrieval.json"
    monkeypatch.setattr(retrieval, "SETTINGS", settings)
    assert not retrieval.enabled()
    lexical = prototype.allocations()
    assert lexical["catalog"]["memory_mib"] == 128
    settings.write_text(json.dumps({"enabled": True}))
    assert prototype.allocations()["catalog"]["memory_mib"] == 768
    calls = []
    monkeypatch.setattr(prototype, "environment", lambda: {})
    monkeypatch.setattr(prototype.postgres, "command", lambda args, **kw: calls.append(args))
    prototype.compose("config", "--quiet")
    assert any(path.endswith("compose.retrieval.yaml") for path in calls[0])
    prototype.compose("config", "--quiet", semantic=False)
    assert not any(path.endswith("compose.retrieval.yaml") for path in calls[1])
