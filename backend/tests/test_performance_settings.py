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
    assert settings["eta_window_minutes"] == performance_settings.DEFAULT_ETA_WINDOW_MINUTES

    updated = performance_settings.update_settings(
        engine, {"parallel_workers": 8, "eta_window_minutes": 15}
    )
    assert updated["parallel_workers"] == 8
    assert updated["eta_window_minutes"] == 15
    assert performance_settings.get_settings(engine)["parallel_workers"] == 8
    assert performance_settings.get_settings(engine)["eta_window_minutes"] == 15


def test_performance_settings_clamps_out_of_range_values(engine):
    updated = performance_settings.update_settings(
        engine, {"parallel_workers": 999, "eta_window_minutes": 999}
    )
    assert updated["parallel_workers"] == performance_settings.MAX_PARALLEL_WORKERS
    assert updated["eta_window_minutes"] == performance_settings.MAX_ETA_WINDOW_MINUTES

    updated = performance_settings.update_settings(
        engine, {"parallel_workers": 0, "eta_window_minutes": 0}
    )
    assert updated["parallel_workers"] == performance_settings.MIN_PARALLEL_WORKERS
    assert updated["eta_window_minutes"] == performance_settings.MIN_ETA_WINDOW_MINUTES


def test_performance_settings_over_http(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.get("/api/performance-settings")
        assert r.status_code == 200
        assert r.json()["parallel_workers"] == performance_settings.DEFAULT_PARALLEL_WORKERS
        assert r.json()["eta_window_minutes"] == performance_settings.DEFAULT_ETA_WINDOW_MINUTES

        r = client.put(
            "/api/performance-settings",
            json={"parallel_workers": 2, "eta_window_minutes": 20},
        )
        assert r.status_code == 200
        assert r.json()["parallel_workers"] == 2
        assert r.json()["eta_window_minutes"] == 20

        after = client.get("/api/performance-settings").json()
        assert after["parallel_workers"] == 2
        assert after["eta_window_minutes"] == 20
