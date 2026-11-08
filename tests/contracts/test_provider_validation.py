"""Review receipts here are explicit test fixtures, never team approvals."""

import json

import pytest

from projectctl.config import ROOT
from projectctl.contract_checks import inspect_contracts
from projectctl.provider_validation import SURFACES, inspect_surface, references


def receipt(tmp_path):
    path = tmp_path / "explicit-review-double.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "fixture": "explicit review double",
                "surfaces": {
                    name: {
                        "status": "APPROVED",
                        "reviewers": [owner, "Jaineel"],
                        "contracts": references(ROOT, name),
                    }
                    for name, (owner, _) in SURFACES.items()
                },
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize("surface", SURFACES)
def test_executable_validation_and_review_are_both_required(tmp_path, surface):
    result = inspect_surface(ROOT, surface)
    assert result["validation"] == "PASS" and result["status"] == "UNREVIEWED"
    reviewed = inspect_surface(ROOT, surface, review=receipt(tmp_path))
    assert reviewed["status"] == "PASS"


def test_review_receipt_reaches_existing_contract_inventory(tmp_path):
    checks = inspect_contracts(ROOT, provider_review=receipt(tmp_path))
    assert {r["name"] for r in checks if r["name"] in SURFACES and r["status"] == "PASS"} == set(
        SURFACES
    )


@pytest.mark.parametrize(
    "change",
    [
        "hash",
        "owner",
        "pending",
        "missing_ref",
        "malformed",
        "non_object",
        "surfaces_list",
        "entry_list",
        "reviewers_object",
        "non_integer_version",
    ],
)
def test_stale_or_incomplete_approvals_cannot_pass(tmp_path, change):
    path = receipt(tmp_path)
    doc = json.loads(path.read_text("utf-8"))
    entry = doc["surfaces"]["shared/outbox"]
    if change == "hash":
        entry["contracts"][0]["sha256"] = "0" * 64
    elif change == "owner":
        entry["reviewers"] = ["Jaineel"]
    elif change == "pending":
        entry["status"] = "REVIEW_REQUIRED"
    elif change == "missing_ref":
        entry["contracts"].pop()
    elif change == "non_object":
        doc = []
    elif change == "surfaces_list":
        doc["surfaces"] = []
    elif change == "entry_list":
        doc["surfaces"]["shared/outbox"] = []
    elif change == "reviewers_object":
        entry["reviewers"] = {"Aditya": True, "Jaineel": True}
    elif change == "non_integer_version":
        doc["schema_version"] = 1.0
    else:
        doc = {}
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert inspect_surface(ROOT, "shared/outbox", review=path)["status"] == (
        "UNREVIEWED" if change == "pending" else "FAIL"
    )


def test_an_approved_receipt_cannot_hide_a_broken_provider(tmp_path, monkeypatch):
    path = receipt(tmp_path)
    monkeypatch.setattr("shared.outbox.append_outbox", lambda wrong_signature: None)
    result = inspect_surface(ROOT, "shared/outbox", review=path)
    assert result["status"] == result["validation"] == "FAIL"
