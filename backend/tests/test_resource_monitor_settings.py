"""Resource-monitor settings singleton tests (chat request): whether/how
often the backend samples its own CPU/memory (see `app/resource_monitor.py`)
into `logs/resource_usage.log`.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.db as db_module
from app import resource_monitor_settings
from app.main import app


def test_resource_monitor_settings_defaults_and_round_trip(engine):
    settings = resource_monitor_settings.get_settings(engine)
    assert settings["enabled"] == resource_monitor_settings.DEFAULT_ENABLED
    assert settings["interval_seconds"] == resource_monitor_settings.DEFAULT_INTERVAL_SECONDS

    updated = resource_monitor_settings.update_settings(engine, {"enabled": False, "interval_seconds": 120})
    assert updated["enabled"] is False
    assert updated["interval_seconds"] == 120
    assert resource_monitor_settings.get_settings(engine)["interval_seconds"] == 120


def test_resource_monitor_settings_clamps_out_of_range_values(engine):
    updated = resource_monitor_settings.update_settings(engine, {"enabled": True, "interval_seconds": 999999})
    assert updated["interval_seconds"] == resource_monitor_settings.MAX_INTERVAL_SECONDS

    updated = resource_monitor_settings.update_settings(engine, {"enabled": True, "interval_seconds": 0})
    assert updated["interval_seconds"] == resource_monitor_settings.MIN_INTERVAL_SECONDS


def test_resource_monitor_settings_over_http(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.get("/api/resource-monitor-settings")
        assert r.status_code == 200
        assert r.json()["interval_seconds"] == resource_monitor_settings.DEFAULT_INTERVAL_SECONDS

        r = client.put("/api/resource-monitor-settings", json={"enabled": False, "interval_seconds": 5})
        assert r.status_code == 200
        assert r.json() == {"enabled": False, "interval_seconds": 5, "updated_at": r.json()["updated_at"]}

        assert client.get("/api/resource-monitor-settings").json()["interval_seconds"] == 5
