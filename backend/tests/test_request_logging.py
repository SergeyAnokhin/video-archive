"""`app.request_logging.RequestLoggingMiddleware`: stays silent for the
polling routes in `_QUIET_ROUTES` while they succeed, but still logs them on
failure, and always logs every other route.
"""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient

import app.db as db_module
from app.main import app


def _isolated_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)
    return TestClient(app)


def _request_log_records(caplog):
    return [r for r in caplog.records if r.name == "app.requests"]


def test_quiet_route_success_is_not_logged(tmp_path, monkeypatch, caplog):
    with _isolated_client(tmp_path, monkeypatch) as client, caplog.at_level(logging.INFO, logger="app.requests"):
        resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert _request_log_records(caplog) == []


def test_quiet_route_failure_is_still_logged(tmp_path, monkeypatch, caplog):
    with _isolated_client(tmp_path, monkeypatch) as client, caplog.at_level(logging.INFO, logger="app.requests"):
        resp = client.get("/api/jobs/does-not-exist/items")
    assert resp.status_code == 404
    records = _request_log_records(caplog)
    assert len(records) == 1
    message = records[0].message
    assert "❌" in message
    assert "/api/jobs/{job_id}/items" in message
    assert "404" in message


def test_non_quiet_route_is_logged_with_path_and_purpose(tmp_path, monkeypatch, caplog):
    with _isolated_client(tmp_path, monkeypatch) as client, caplog.at_level(logging.INFO, logger="app.requests"):
        resp = client.get("/api/performance-settings")
    assert resp.status_code == 200
    records = _request_log_records(caplog)
    assert len(records) == 1
    message = records[0].message
    assert "✅" in message
    assert "/api/performance-settings" in message
    assert "get performance settings" in message


def test_health_route_success_is_not_logged(tmp_path, monkeypatch, caplog):
    with _isolated_client(tmp_path, monkeypatch) as client, caplog.at_level(logging.INFO, logger="app.requests"):
        resp = client.get("/api/health")
    assert resp.status_code == 200
    assert _request_log_records(caplog) == []


def test_system_stats_route_success_is_not_logged(tmp_path, monkeypatch, caplog):
    with _isolated_client(tmp_path, monkeypatch) as client, caplog.at_level(logging.INFO, logger="app.requests"):
        resp = client.get("/api/system/stats")
    assert resp.status_code == 200
    assert _request_log_records(caplog) == []
