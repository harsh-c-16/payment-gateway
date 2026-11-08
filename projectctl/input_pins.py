"""Expose exact-byte versus provider text pins without changing runbook hash semantics."""

import hashlib

from projectctl.artifacts import file_hash
from projectctl.config import repo_path

PUBLISHED = {
    "dictionary": (
        "contracts/dictionaries/catalog/flipkart-v1.json",
        "a7d381e90986b23f801eca537a689f2d3e056fa0b58040ecb7c182e2be2f9943",
    ),
    "queries": (
        "contracts/fixtures/catalog/queries.json",
        "89d89ac030f10d23e85d6e5084caa125017b5f927a1ed94854aadc3be4762410",
    ),
}


def text_pin(path):
    """Both values are labelled; the exact raw file hash is never normalized."""
    raw = path.read_bytes()
    text = raw.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return {
        "raw_sha256": file_hash(path),
        "lf_text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "contains_crlf": b"\r\n" in raw,
    }


def review_input_pins():
    result = {}
    for name, (relative, published) in PUBLISHED.items():
        path = repo_path(relative)
        if not path.is_file():
            result[name] = {"path": relative, "status": "NOT_RUN"}
            continue
        facts = text_pin(path)
        result[name] = {
            "path": relative,
            **facts,
            "published_sha256": published,
            "published_matches_lf_text": published == facts["lf_text_sha256"],
            "published_matches_raw": published == facts["raw_sha256"],
            "status": "REVIEW_REQUIRED",
            "decision": {
                "evaluation_pin": "raw_sha256 (exact runtime bytes)",
                "provider_identity": "lf_text_sha256 (existing dataset revision unchanged)",
                "freeze_machine": "Regenerate/review the packet on the final execution machine",
            },
            "conflict": (
                "file09 section 1 requires exact raw-file bytes; the provider's dictionary "
                "identity uses universal-newline UTF-8 text. Do not replace dataset_revision."
            ),
            "required_review": ["Harsh", "Jaineel", "Aditya (SKU consumer)"],
        }
    return result
