"""Performance settings singleton tests (post-V1, user request): how many
files/variants the `convert`/`preview` jobs process concurrently.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.db as db_module
from app import performance_settings
from app.main import app


def test_performance_settings_defaults_and_round_trip(engine):
    settings = performance_settings.get_settings(engine)
    assert settings["parallel_workers"] == performance_settings.DEFAULT_PARALLEL_WORKERS

    updated = performance_settings.update_settings(engine, {"parallel_workers": 8})
    assert updated["parallel_workers"] == 8
    assert performance_settings.get_settings(engine)["parallel_workers"] == 8


def test_performance_settings_clamps_out_of_range_values(engine):
    updated = performance_settings.update_settings(engine, {"parallel_workers": 999})
    assert updated["parallel_workers"] == performance_settings.MAX_PARALLEL_WORKERS

    updated = performance_settings.update_settings(engine, {"parallel_workers": 0})
    assert updated["parallel_workers"] == performance_settings.MIN_PARALLEL_WORKERS


def test_performance_settings_over_http(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.get("/api/performance-settings")
        assert r.status_code == 200
        assert r.json()["parallel_workers"] == performance_settings.DEFAULT_PARALLEL_WORKERS

        r = client.put("/api/performance-settings", json={"parallel_workers": 2})
        assert r.status_code == 200
        assert r.json()["parallel_workers"] == 2

        assert client.get("/api/performance-settings").json()["parallel_workers"] == 2
