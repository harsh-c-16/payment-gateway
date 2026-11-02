"""The stress ladder's accounting, without a database: a rejected call must stay visible."""

import itertools
import json
from types import SimpleNamespace

from pipelines.catalog import experiments
from services.catalog.errors import storage_unavailable


def test_stress_level_counts_rejections_and_violations_apart_from_latency(monkeypatch):
    calls = itertools.count()
    hit = SimpleNamespace(model_dump=lambda mode: {})

    def fake_search(db, events, request, context):
        if next(calls) % 3 == 0:
            raise storage_unavailable()
        return SimpleNamespace(hits=[hit])

    monkeypatch.setattr(experiments.search, "search_catalog", fake_search)
    monkeypatch.setattr(experiments, "hit_violations", lambda intent, found: ["wrong category"])
    spec = json.loads(experiments.QUERIES.read_text(encoding="utf-8"))["queries"][0]

    level = experiments.stress_level(None, [(spec, "lexical")], None, clients=2, seconds=0.05)

    completed = level["latency_ms"]["count"]
    assert level["clients"] == 2
    assert level["rejected"] > 0
    assert completed > level["rejected"]
    assert level["hard_filter_violations"] == completed
    assert level["completed_per_second"] == completed / level["seconds"]
