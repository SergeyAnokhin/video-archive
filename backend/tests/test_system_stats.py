"""`GET /api/system/stats` (backend resource indicator, chat request
2026-07-19): exposes CPU/memory via `psutil` and cumulative SMB bytes read
via `app.sources.smb_stats`, polled every 5s by the frontend widget."""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.db as db_module
from app.main import app


def _isolated_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)
    return TestClient(app)


def test_system_stats_shape(tmp_path, monkeypatch):
    with _isolated_client(tmp_path, monkeypatch) as client:
        resp = client.get("/api/system/stats")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["cpu_percent"], (int, float))
    assert body["cpu_percent"] >= 0
    assert isinstance(body["memory_rss_bytes"], int)
    assert body["memory_rss_bytes"] > 0
    assert isinstance(body["memory_percent"], (int, float))
    assert body["memory_percent"] >= 0
    assert isinstance(body["smb_bytes_read_total"], int)
    assert body["smb_bytes_read_total"] >= 0
    assert isinstance(body["timestamp"], (int, float))
