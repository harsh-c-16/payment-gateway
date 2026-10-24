import csv
from pathlib import Path

import pytest

from benchmarks.dataset_checks import EXPECTED, SOURCE_SHA256, inspect_source, price_minor

ROOT = Path(__file__).resolve().parents[2]


def test_checksum_mismatch_precedes_all_exact_count_assertions(tmp_path, monkeypatch):
    wrong = tmp_path / "different.csv"
    wrong.write_text("not the exact CSV", encoding="utf-8")

    def forbidden(*args, **kwargs):
        raise AssertionError("CSV parser must not run before checksum acceptance")

    monkeypatch.setattr(csv, "reader", forbidden)
    report = inspect_source(wrong)
    assert report["status"] == "INCOMPLETE"
    assert report["assertions"] == [] and report["observed"] is None


def test_missing_source_is_not_run(tmp_path):
    report = inspect_source(tmp_path / "missing.csv")
    assert report["status"] == "NOT_RUN" and report["observed"] is None
    assert report["assertions"] == []


def test_exact_source_when_available_has_conserved_dispositions():
    path = ROOT / "data/raw/flipkart_com-ecommerce_sample.csv"
    report = inspect_source(path)
    if not path.is_file():
        # Hosted CI has no uploaded dataset. Keep this condition visible without a fake pass.
        assert report["status"] == "NOT_RUN" and report["assertions"] == []
        return
    assert report["source_sha256"] == SOURCE_SHA256
    assert report["status"] == "PASS"
    assert report["observed"] == EXPECTED
    assert all(assertion["passed"] for assertion in report["assertions"])
    assert report["provider_normalization_comparison"] == "NOT_RUN"
    assert report["facet_coverage_verification"] == "NOT_RUN"


@pytest.mark.parametrize(
    "raw,expected", [("379", 37900), ("999", 99900), ("1.25", 125), ("", None), ("0.01", 1)]
)
def test_independent_price_arithmetic(raw, expected):
    assert price_minor(raw) == expected


@pytest.mark.parametrize("raw", ["nan", "inf", "1.001", "0", "-1", "10000000.01", "bad"])
def test_invalid_price_is_never_zero_or_imputed(raw):
    with pytest.raises(ValueError):
        price_minor(raw)
