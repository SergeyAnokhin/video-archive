"""Log file listing/download tests (chat request): the backend runs on a
Kubernetes PVC the user has no direct disk access to, so `backend.log` (and
any rotated backups) need to be downloadable through the UI instead. Uses
arbitrary sample filenames since listing/download is generic over whatever
is in `LOG_DIR`.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.db as db_module
from app.main import app
from app.routers import log_files


def test_list_log_files(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(log_files, "LOG_DIR", log_dir)
    (log_dir / "backend.log").write_text("hello", encoding="utf-8")
    (log_dir / "resource_usage.log").write_text("cpu_percent=1.0", encoding="utf-8")
    (log_dir / "subdir").mkdir()  # directories must not show up as files

    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.get("/api/log-files")
        assert r.status_code == 200
        names = {f["name"] for f in r.json()["files"]}
        assert names == {"backend.log", "resource_usage.log"}


def test_download_log_file(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(log_files, "LOG_DIR", log_dir)
    (log_dir / "resource_usage.log").write_text("cpu_percent=1.0", encoding="utf-8")

    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.get("/api/log-files/resource_usage.log")
        assert r.status_code == 200
        assert r.text == "cpu_percent=1.0"


def test_download_log_file_rejects_path_traversal(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    monkeypatch.setattr(log_files, "LOG_DIR", log_dir)
    secret = tmp_path / "secret.txt"
    secret.write_text("should not be downloadable", encoding="utf-8")

    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.get("/api/log-files/..%2Fsecret.txt")
        assert r.status_code in (400, 404)

        r = client.get("/api/log-files/missing.log")
        assert r.status_code == 404
