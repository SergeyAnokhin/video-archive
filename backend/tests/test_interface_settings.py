"""Interface settings singleton tests (Stage 9, Settings §9): language +
theme preset, service-level round trip plus the HTTP endpoint.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.db as db_module
from app import interface_settings
from app.main import app


def test_interface_settings_defaults_and_round_trip(engine):
    settings = interface_settings.get_settings(engine)
    assert settings["language"] == "en"
    assert settings["theme_preset"] == "strict"

    updated = interface_settings.update_settings(engine, {"language": "ru", "theme_preset": "playful"})
    assert updated["language"] == "ru"
    assert updated["theme_preset"] == "playful"
    assert interface_settings.get_settings(engine)["theme_preset"] == "playful"


def test_interface_settings_over_http(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.get("/api/interface-settings")
        assert r.status_code == 200
        assert r.json() == {"language": "en", "theme_preset": "strict", "updated_at": r.json()["updated_at"]}

        r = client.put("/api/interface-settings", json={"language": "ru", "theme_preset": "playful"})
        assert r.status_code == 200
        assert r.json()["language"] == "ru"
        assert r.json()["theme_preset"] == "playful"

        assert client.get("/api/interface-settings").json()["theme_preset"] == "playful"
