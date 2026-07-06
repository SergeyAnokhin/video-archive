"""HTTP-layer tests for backup/restore/maintenance endpoints (Stage 8):
`/api/backups*`, `/api/backup-settings`, and the `cleanup-stale-records`/
`optimize-database` job triggers. Backup/restore run through the real
background `JobWorker` started by the app's lifespan, so these tests poll
for completion the same way `test_jobs_router.py`'s rescan test does.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

import app.db as db_module
from app.main import app

_FINISHED_STATUSES = {"completed", "failed", "cancelled"}


def _insert_source_and_file(engine, root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "clip_0.mp4").write_bytes(b"0")

    source_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sources (id, name, protocol, root_path, is_active, created_at, updated_at) "
                "VALUES (:id, 'Test', 'local', :root, 1, :now, :now)"
            ),
            {"id": source_id, "root": str(root), "now": now},
        )
        dir_id = str(uuid.uuid4())
        conn.execute(
            text(
                "INSERT INTO directories (id, source_id, relative_path, name, parent_relative_path, "
                "has_folder_preview, last_scanned_at, created_at, updated_at) "
                "VALUES (:id, :sid, '', 'Test', NULL, 0, :now, :now, :now)"
            ),
            {"id": dir_id, "sid": source_id, "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, created_at, updated_at) "
                "VALUES (:id, :sid, :did, 'clip_0.mp4', 'clip_0.mp4', 'mp4', 1, :now, :now, 1, :now, :now)"
            ),
            {"id": str(uuid.uuid4()), "sid": source_id, "did": dir_id, "now": now},
        )
    return source_id


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/api/jobs/{job_id}")
        if r.json()["status"] in _FINISHED_STATUSES:
            return r.json()
        time.sleep(0.05)
    raise AssertionError("job did not finish via HTTP in time")


def test_backups_require_a_configured_source(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        assert client.get("/api/backups").status_code == 404
        assert client.post("/api/backups", json={}).status_code == 404


def test_backup_create_list_restore_delete_over_http(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        engine = db_module.get_engine()
        _insert_source_and_file(engine, tmp_path / "source")

        r = client.post("/api/backups", json={})
        assert r.status_code == 200
        job = r.json()
        assert job["job_type"] == "backup"
        final = _wait_for_job(client, job["id"])
        assert final["status"] == "completed"

        r = client.get("/api/backups")
        assert r.status_code == 200
        backups = r.json()["backups"]
        assert len(backups) == 1
        backup_id = backups[0]["id"]
        assert backups[0]["includes_secrets"] is False

        # Wipe the library metadata (as a destructive source switch would)
        # and restore it from the backup just created.
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM file_tags"))
            conn.execute(text("DELETE FROM files"))
            conn.execute(text("DELETE FROM directories"))

        r = client.post("/api/backups/restore", json={"backup_id": backup_id})
        assert r.status_code == 200
        restore_job = r.json()
        assert restore_job["job_type"] == "restore"
        final = _wait_for_job(client, restore_job["id"])
        assert final["status"] == "completed"

        with engine.connect() as conn:
            count = conn.execute(text("SELECT COUNT(*) FROM files")).scalar()
        assert count == 1

        r = client.post("/api/backups/restore", json={"backup_id": "does-not-exist"})
        assert r.status_code == 404

        r = client.delete(f"/api/backups/{backup_id}")
        assert r.status_code == 200
        assert client.get("/api/backups").json()["backups"] == []

        r = client.delete(f"/api/backups/{backup_id}")
        assert r.status_code == 404


def test_backup_settings_get_put(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.get("/api/backup-settings")
        assert r.status_code == 200
        assert r.json()["retention_count"] == 5

        r = client.put("/api/backup-settings", json={"retention_count": 3})
        assert r.status_code == 200
        assert r.json()["retention_count"] == 3


def test_maintenance_job_triggers_over_http(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        engine = db_module.get_engine()
        _insert_source_and_file(engine, tmp_path / "source")

        r = client.post("/api/jobs/cleanup-stale-records")
        assert r.status_code == 200
        job = r.json()
        assert job["job_type"] == "cleanup"
        assert _wait_for_job(client, job["id"])["status"] == "completed"

        r = client.post("/api/jobs/optimize-database")
        assert r.status_code == 200
        job = r.json()
        assert job["job_type"] == "optimize_db"
        assert _wait_for_job(client, job["id"])["status"] == "completed"
