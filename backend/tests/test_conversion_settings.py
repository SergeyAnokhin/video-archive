"""Conversion settings singleton tests (user report): the minimum
size-reduction percentage a converted output must achieve to replace the
source (see `app/jobs/convert.py`).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.db as db_module
from app import conversion_settings
from app.main import app


def test_conversion_settings_defaults_and_round_trip(engine):
    settings = conversion_settings.get_settings(engine)
    assert settings["min_size_reduction_percent"] == conversion_settings.DEFAULT_MIN_SIZE_REDUCTION_PERCENT

    updated = conversion_settings.update_settings(engine, {"min_size_reduction_percent": 15})
    assert updated["min_size_reduction_percent"] == 15
    assert conversion_settings.get_settings(engine)["min_size_reduction_percent"] == 15


def test_conversion_settings_clamps_out_of_range_values(engine):
    updated = conversion_settings.update_settings(engine, {"min_size_reduction_percent": 999})
    assert updated["min_size_reduction_percent"] == conversion_settings.MAX_MIN_SIZE_REDUCTION_PERCENT

    updated = conversion_settings.update_settings(engine, {"min_size_reduction_percent": -10})
    assert updated["min_size_reduction_percent"] == conversion_settings.MIN_MIN_SIZE_REDUCTION_PERCENT


def test_conversion_settings_over_http(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.get("/api/conversion-settings")
        assert r.status_code == 200
        assert r.json()["min_size_reduction_percent"] == conversion_settings.DEFAULT_MIN_SIZE_REDUCTION_PERCENT

        r = client.put("/api/conversion-settings", json={"min_size_reduction_percent": 10})
        assert r.status_code == 200
        assert r.json()["min_size_reduction_percent"] == 10

        assert client.get("/api/conversion-settings").json()["min_size_reduction_percent"] == 10
