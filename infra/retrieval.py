"""Provision the existing locked retriever for the retained local prototype.

Run `python -m infra.retrieval setup` with Docker Desktop running. This downloads
only checksum-locked model files, builds an optional image and backfills embeddings.
It never imports products, seeds inventory, resets volumes or submits purchases.
"""

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
from pathlib import Path
from uuid import uuid4

import httpx

from infra import postgres
from services.catalog.embedding import load_lock, verify_model_files

MODEL_DIR = postgres.ROOT / "artifacts/models/all-MiniLM-L6-v2"
SETTINGS = postgres.ROOT / "artifacts/infra/prototype-local/retrieval.json"


def enabled():
    return SETTINGS.is_file() and json.loads(SETTINGS.read_text())["enabled"] is True


def download_model(directory=MODEL_DIR):
    directory.mkdir(parents=True, exist_ok=True)
    lock = load_lock()
    for name, entry in lock["files"].items():
        target = directory / name
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == entry["sha256"]:
            continue
        url = f"https://huggingface.co/{lock['model_id']}/resolve/{lock['revision']}/{entry['source']}"
        # A partial/invalid download never replaces a verified model file.
        partial = target.with_suffix(target.suffix + ".download")
        try:
            digest = hashlib.sha256()
            with urllib.request.urlopen(url, timeout=60) as response, partial.open("wb") as stream:
                while chunk := response.read(1024 * 1024):
                    digest.update(chunk)
                    stream.write(chunk)
            if digest.hexdigest() != entry["sha256"]:
                raise ValueError(f"Downloaded {name} differs from the model lock")
            os.replace(partial, target)
        finally:
            partial.unlink(missing_ok=True)
    verify_model_files(directory, lock)


def build_image():
    with tempfile.TemporaryDirectory(prefix="retrieval-image-") as directory:
        directory = Path(directory)
        for source in (
            "infra/retrieval.Dockerfile",
            "contracts/data/catalog/embedding_requirements.txt",
        ):
            shutil.copyfile(postgres.ROOT / source, directory / Path(source).name)
        postgres.command(
            [
                "docker",
                "build",
                "--tag",
                "group3-catalog-retrieval:local",
                "--file",
                str(directory / "retrieval.Dockerfile"),
                str(directory),
            ],
            timeout=600,
        )


def setup():
    from infra import prototype

    postgres.check_engine()
    download_model()
    (postgres.ROOT / "artifacts/retrieval").mkdir(parents=True, exist_ok=True)
    # The base image is exactly the normal application image.
    postgres.command(
        ["docker", "image", "inspect", "group3-m04-storage:local", "--format", "{{.Id}}"]
    )
    build_image()
    namespace = prototype.environment()["RUN_NAMESPACE"]
    print(f"Backfilling locked embeddings in retained namespace {namespace}...", flush=True)
    output = prototype.compose(
        "run",
        "--rm",
        "--no-deps",
        "catalog",
        "python",
        "-m",
        "pipelines.catalog.embeddings",
        "--namespace",
        namespace,
        "--out",
        "/app/retrieval-artifacts",
        "--batch-size",
        "16",
        semantic=True,
    )
    print(output, flush=True)
    SETTINGS.write_text(json.dumps({"enabled": True, "revision": load_lock()["revision"]}) + "\n")
    print(
        "Hybrid retrieval provisioned. The prototype launcher now retains its model/image/limits."
    )
    print("Start the prototype normally, or recreate its running catalogue service to activate it.")


def verify(*, conversation_url="http://127.0.0.1:8001", catalog_url="http://127.0.0.1:8002"):
    """Real HTTP search checks. Creates one session, but never changes a cart or buys."""
    from infra import prototype

    namespace = prototype.environment()["RUN_NAMESPACE"]
    out = postgres.ROOT / "artifacts/retrieval" / ("verify-" + uuid4().hex)
    out.mkdir(parents=True)
    journal = []
    headers = {
        "X-Namespace": namespace,
        "X-User-ID": "retrieval-check-" + uuid4().hex,
        "X-Run-ID": str(uuid4()),
        "X-Correlation-ID": str(uuid4()),
    }
    with httpx.Client(timeout=10, trust_env=False) as client:

        def call(origin, method, path, body=None):
            identity = {**headers, "X-Request-ID": str(uuid4()), "Idempotency-Key": str(uuid4())}
            if body is not None and "text" in body:
                body = {**body, "request_id": identity["X-Request-ID"]}
            response = client.request(method, origin + path, json=body, headers=identity)
            try:
                data = response.json()
            except ValueError:
                data = {"non_json_body": response.text[:1000]}
            journal.append({"path": path, "status": response.status_code, "body": data})
            (out / "http.json").write_text(json.dumps(journal, indent=2), encoding="utf-8")
            response.raise_for_status()
            return data

        caps = call(conversation_url, "GET", "/v1/store/capabilities")
        assert "hybrid_exact" in caps["search_modes"], caps
        session = call(conversation_url, "POST", "/v1/sessions", {})["session_id"]
        headers["X-Session-ID"] = session
        shown = set()
        for text in (
            "shirt under 1000 rupees",
            "Show more options",
            "More like the second one",
        ):
            result = call(
                conversation_url,
                "POST",
                f"/v1/sessions/{session}/shopping-turns",
                {"text": text, "mode": "fixed"},
            )
            assert result["outcome"] == "success" and result["products"], result
            assert result["llm_call_count"] == 0
            assert result["intent"]["colour"] is None
            assert result["intent"]["max_price_minor"] == 99999
            products = result["products"]
            assert all(
                p["retrieval_mode"] == "hybrid_exact"
                and p["price_minor"] <= 99999
                and p["stock_available"] > 0
                and "bra" not in p["title"].casefold()
                and "trouser" not in p["title"].casefold()
                for p in products
            )
            assert not shown.intersection(p["sku"] for p in products)
            shown.update(p["sku"] for p in products)
        strict = call(
            conversation_url,
            "POST",
            f"/v1/sessions/{session}/shopping-turns",
            {"text": "Only white ones", "mode": "fixed"},
        )
        assert strict["intent"]["colour"] == "white"
        assert strict["intent"]["max_price_minor"] == 99999
        assert all(
            p["colour"] == "white"
            and p["price_minor"] <= 99999
            and "bra" not in p["title"].casefold()
            for p in strict["products"]
        )
        from services.conversation.intent import blank_intent

        semantic = call(
            catalog_url,
            "POST",
            "/v1/search",
            {
                "request_id": str(uuid4()),
                "session_id": session,
                "intent": {**blank_intent("wristwatch"), "category": "watches"},
                "mode": "hybrid_exact",
                "top_k": 5,
            },
        )
        assert semantic["embedding_calls"] == 1
        assert semantic["embedding_revision"] == load_lock()["revision"]
        assert semantic["hits"] and all(p["category"] == "watches" for p in semantic["hits"])
        saved = call(conversation_url, "GET", f"/v1/sessions/{session}")["conversation"]
        assert saved["retrieval_mode"] == "hybrid_exact"
    (out / "checks.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "session_id": session,
                "model_revision": semantic["embedding_revision"],
                "generative_calls": 0,
            },
            indent=2,
        )
    )
    print(f"Real M1/M2 hybrid retrieval: PASS. Evidence: {out.relative_to(postgres.ROOT)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["download", "setup", "verify"])
    arguments = parser.parse_args()
    if arguments.action == "download":
        download_model()
        print("Locked model files verified.")
    elif arguments.action == "setup":
        setup()
    else:
        verify()


if __name__ == "__main__":
    main()
