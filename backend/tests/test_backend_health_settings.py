"""Backend-health-indicator timeout settings singleton (chat request
2026-07-19 follow-up, user-configurable): how long the top-bar status dot
waits before turning amber ("slow"), and how much longer it then waits on
retry before turning red ("offline").
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.db as db_module
from app import backend_health_settings
from app.main import app


def test_backend_health_settings_defaults_and_round_trip(engine):
    settings = backend_health_settings.get_settings(engine)
    assert settings["slow_timeout_seconds"] == backend_health_settings.DEFAULT_SLOW_TIMEOUT_SECONDS
    assert settings["offline_timeout_seconds"] == backend_health_settings.DEFAULT_OFFLINE_TIMEOUT_SECONDS

    updated = backend_health_settings.update_settings(
        engine, {"slow_timeout_seconds": 3, "offline_timeout_seconds": 20}
    )
    assert updated["slow_timeout_seconds"] == 3
    assert updated["offline_timeout_seconds"] == 20
    assert backend_health_settings.get_settings(engine)["slow_timeout_seconds"] == 3


def test_backend_health_settings_clamps_out_of_range_values(engine):
    updated = backend_health_settings.update_settings(
        engine, {"slow_timeout_seconds": 999, "offline_timeout_seconds": 999}
    )
    assert updated["slow_timeout_seconds"] == backend_health_settings.MAX_SLOW_TIMEOUT_SECONDS
    assert updated["offline_timeout_seconds"] == backend_health_settings.MAX_OFFLINE_TIMEOUT_SECONDS

    updated = backend_health_settings.update_settings(
        engine, {"slow_timeout_seconds": 0, "offline_timeout_seconds": 0}
    )
    assert updated["slow_timeout_seconds"] == backend_health_settings.MIN_SLOW_TIMEOUT_SECONDS
    assert updated["offline_timeout_seconds"] == backend_health_settings.MIN_OFFLINE_TIMEOUT_SECONDS


def test_backend_health_settings_over_http(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.get("/api/backend-health-settings")
        assert r.status_code == 200
        assert r.json()["slow_timeout_seconds"] == backend_health_settings.DEFAULT_SLOW_TIMEOUT_SECONDS

        r = client.put(
            "/api/backend-health-settings",
            json={"slow_timeout_seconds": 8, "offline_timeout_seconds": 15},
        )
        assert r.status_code == 200
        assert r.json()["slow_timeout_seconds"] == 8
        assert r.json()["offline_timeout_seconds"] == 15

        assert client.get("/api/backend-health-settings").json()["offline_timeout_seconds"] == 15
