"""Real PostgreSQL in an isolated per-test schema; a missing database is a visible skip."""

from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[2] / "data/raw/flipkart_com-ecommerce_sample.csv"


@pytest.fixture
def source_csv():
    if not SOURCE.is_file():
        pytest.skip("NOT_RUN: data/raw/flipkart_com-ecommerce_sample.csv not present")
    return SOURCE
