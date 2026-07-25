"""Log-rotation settings singleton tests (chat request): configurable size
threshold and backup count for the rotating file handler (see
`app/logging_config.py`).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.db as db_module
from app import log_rotation_settings
from app.main import app


def test_log_rotation_settings_defaults_and_round_trip(engine):
    settings = log_rotation_settings.get_settings(engine)
    assert settings["max_bytes"] == log_rotation_settings.DEFAULT_MAX_BYTES
    assert settings["backup_count"] == log_rotation_settings.DEFAULT_BACKUP_COUNT

    updated = log_rotation_settings.update_settings(engine, {"max_bytes": 10 * 1024 * 1024, "backup_count": 3})
    assert updated["max_bytes"] == 10 * 1024 * 1024
    assert updated["backup_count"] == 3
    assert log_rotation_settings.get_settings(engine)["backup_count"] == 3


def test_log_rotation_settings_clamps_out_of_range_values(engine):
    updated = log_rotation_settings.update_settings(engine, {"max_bytes": 999999999999, "backup_count": 999})
    assert updated["max_bytes"] == log_rotation_settings.MAX_MAX_BYTES
    assert updated["backup_count"] == log_rotation_settings.MAX_BACKUP_COUNT

    updated = log_rotation_settings.update_settings(engine, {"max_bytes": 0, "backup_count": 0})
    assert updated["max_bytes"] == log_rotation_settings.MIN_MAX_BYTES
    assert updated["backup_count"] == log_rotation_settings.MIN_BACKUP_COUNT


def test_log_rotation_settings_over_http(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.get("/api/log-rotation-settings")
        assert r.status_code == 200
        assert r.json()["max_bytes"] == log_rotation_settings.DEFAULT_MAX_BYTES

        r = client.put("/api/log-rotation-settings", json={"max_bytes": 2 * 1024 * 1024, "backup_count": 2})
        assert r.status_code == 200
        assert r.json()["max_bytes"] == 2 * 1024 * 1024
        assert r.json()["backup_count"] == 2

        assert client.get("/api/log-rotation-settings").json()["backup_count"] == 2


def test_apply_rotation_settings_mutates_live_handler(monkeypatch):
    from logging.handlers import RotatingFileHandler

    from app import logging_config

    handler = RotatingFileHandler.__new__(RotatingFileHandler)
    handler.maxBytes = log_rotation_settings.DEFAULT_MAX_BYTES
    handler.backupCount = log_rotation_settings.DEFAULT_BACKUP_COUNT
    monkeypatch.setattr(logging_config, "_file_handler", handler)

    logging_config.apply_rotation_settings(7 * 1024 * 1024, 4)
    assert handler.maxBytes == 7 * 1024 * 1024
    assert handler.backupCount == 4
