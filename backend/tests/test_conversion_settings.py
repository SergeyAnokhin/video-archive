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
    assert settings["ffmpeg_timeout_seconds"] == conversion_settings.DEFAULT_FFMPEG_TIMEOUT_SECONDS

    updated = conversion_settings.update_settings(
        engine, {"min_size_reduction_percent": 15, "ffmpeg_timeout_seconds": 7200}
    )
    assert updated["min_size_reduction_percent"] == 15
    assert updated["ffmpeg_timeout_seconds"] == 7200
    assert conversion_settings.get_settings(engine)["min_size_reduction_percent"] == 15
    assert conversion_settings.get_settings(engine)["ffmpeg_timeout_seconds"] == 7200


def test_conversion_settings_clamps_out_of_range_values(engine):
    updated = conversion_settings.update_settings(
        engine, {"min_size_reduction_percent": 999, "ffmpeg_timeout_seconds": 999999}
    )
    assert updated["min_size_reduction_percent"] == conversion_settings.MAX_MIN_SIZE_REDUCTION_PERCENT
    assert updated["ffmpeg_timeout_seconds"] == conversion_settings.MAX_FFMPEG_TIMEOUT_SECONDS

    updated = conversion_settings.update_settings(
        engine, {"min_size_reduction_percent": -10, "ffmpeg_timeout_seconds": 1}
    )
    assert updated["min_size_reduction_percent"] == conversion_settings.MIN_MIN_SIZE_REDUCTION_PERCENT
    assert updated["ffmpeg_timeout_seconds"] == conversion_settings.MIN_FFMPEG_TIMEOUT_SECONDS


def test_conversion_settings_over_http(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.get("/api/conversion-settings")
        assert r.status_code == 200
        assert r.json()["min_size_reduction_percent"] == conversion_settings.DEFAULT_MIN_SIZE_REDUCTION_PERCENT
        assert r.json()["ffmpeg_timeout_seconds"] == conversion_settings.DEFAULT_FFMPEG_TIMEOUT_SECONDS

        r = client.put(
            "/api/conversion-settings",
            json={"min_size_reduction_percent": 10, "ffmpeg_timeout_seconds": 1800},
        )
        assert r.status_code == 200
        assert r.json()["min_size_reduction_percent"] == 10
        assert r.json()["ffmpeg_timeout_seconds"] == 1800

        assert client.get("/api/conversion-settings").json()["min_size_reduction_percent"] == 10
        assert client.get("/api/conversion-settings").json()["ffmpeg_timeout_seconds"] == 1800
