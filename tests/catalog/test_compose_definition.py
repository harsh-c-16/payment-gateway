"""Static checks only: this compose file has not run yet, since this host has no Docker."""

from pathlib import Path

import yaml

from services.catalog.app import create_app

COMPOSE = Path(__file__).resolve().parents[2] / "infra/compose.catalog.yaml"


def test_service_entry_points_and_declared_port_exist():
    document = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    catalog, worker = document["services"]["catalog"], document["services"]["catalog-worker"]
    assert "services.catalog.app:create_app" in catalog["command"]
    assert catalog["ports"] == ["127.0.0.1:8002:8002"]
    assert worker["command"][:3] == ["python", "-m", "services.catalog.worker"]
    assert callable(create_app)
    # Vichitr's FileStore is not mounted: only the importer archives, and it runs separately.
    assert all("lakehouse" not in volume for volume in catalog["volumes"])
