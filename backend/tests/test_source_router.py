"""HTTP-layer tests for `/api/source*` (API §2, Specification §5): the
pre-Stage-7 `local` flow (regression) plus the Stage 7 `smb` flow — test
connection, connect (with credential storage + scan), and reconnect — driven
against the in-memory `fake_smb` fixture (`conftest.py`) since no real SMB
server is available in this environment.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient
from sqlalchemy import text

import app.db as db_module
from app.main import app

_FINISHED_STATUSES = {"completed", "failed", "cancelled"}


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.get(f"/api/jobs/{job_id}").json()["status"] in _FINISHED_STATUSES:
            return
        time.sleep(0.05)
    raise AssertionError("job did not finish via HTTP in time")


def test_local_source_connect_and_test_connection(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    root = tmp_path / "library"
    root.mkdir()
    (root / "clip.mp4").write_bytes(b"0")

    with TestClient(app) as client:
        r = client.post("/api/source/test-connection", json={"name": "L", "protocol": "local", "root_path": str(root)})
        assert r.json()["ok"] is True

        r = client.put("/api/source", json={"name": "L", "protocol": "local", "root_path": str(root)})
        assert r.status_code == 200
        body = r.json()
        assert body["protocol"] == "local"
        assert body["detected_backups"] == []

        r = client.get("/api/source")
        assert r.json()["root_path"] == str(root.resolve())

        r = client.get("/api/files")
        assert len(r.json()["files"]) == 1

        r = client.post("/api/source/reconnect")
        assert r.json()["ok"] is True


def test_smb_source_test_connection_and_connect(tmp_path, monkeypatch, fake_smb):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    fake_smb.seed("clips/movie.mp4", b"0" * 42)

    with TestClient(app) as client:
        r = client.post(
            "/api/source/test-connection",
            json={
                "name": "NAS", "protocol": "smb", "host": fake_smb.host, "port": 445,
                "root_path": fake_smb.share, "username": "user", "password": "pass",
            },
        )
        assert r.json()["ok"] is True

        r = client.put(
            "/api/source",
            json={
                "name": "NAS", "protocol": "smb", "host": fake_smb.host, "port": 445,
                "root_path": fake_smb.share, "username": "user", "password": "pass",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["protocol"] == "smb"
        assert body["host"] == fake_smb.host

        r = client.get("/api/source")
        assert r.json()["host"] == fake_smb.host

        r = client.get("/api/files")
        assert len(r.json()["files"]) == 1
        assert r.json()["files"][0]["file_name"] == "movie.mp4"

        r = client.post("/api/source/reconnect")
        assert r.json()["ok"] is True


def test_smb_source_requires_host(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.put("/api/source", json={"name": "NAS", "protocol": "smb", "root_path": "share"})
        assert r.status_code == 400
        assert r.json()["detail"]["error"]["code"] == "host_required"


def test_replacing_source_wipes_full_metadata_and_offers_detected_backups(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    root = tmp_path / "library"
    root.mkdir()
    (root / "clip.mp4").write_bytes(b"0")

    with TestClient(app) as client:
        r = client.put("/api/source", json={"name": "L", "protocol": "local", "root_path": str(root)})
        assert r.status_code == 200

        # Build up job history and a backup while this source is active.
        r = client.post("/api/jobs/cleanup-stale-records")
        _wait_for_job(client, r.json()["id"])

        r = client.post("/api/backups", json={})
        _wait_for_job(client, r.json()["id"])
        assert client.get("/api/jobs").json()["jobs"]

        # Replacing the source (even with the same root path, as happens
        # when reconnecting after switching away and back) must wipe job
        # history/tags (Data Model §1) and surface the backup just made for
        # restore (Specification §5.2).
        r = client.put("/api/source", json={"name": "L", "protocol": "local", "root_path": str(root)})
        assert r.status_code == 200
        assert len(r.json()["detected_backups"]) == 1

        assert client.get("/api/jobs").json()["jobs"] == []
        engine = db_module.get_engine()
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM app_events")).scalar() == 0
            assert conn.execute(text("SELECT COUNT(*) FROM job_items")).scalar() == 0


def test_unsupported_protocol_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.put("/api/source", json={"name": "X", "protocol": "webdav", "root_path": "/x"})
        assert r.status_code == 400
        assert r.json()["detail"]["error"]["code"] == "unsupported_protocol"
