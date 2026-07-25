"""HTTP-layer tests for the jobs/logs routers (non-streaming endpoints only).

`GET /api/logs/stream` is deliberately not exercised through
`fastapi.testclient.TestClient` here: TestClient's synchronous ASGI bridge
does not reliably stream an endless SSE generator and will hang the test
process waiting for a chunk that never arrives in that harness (discovered
the hard way during Stage 3 development). If that endpoint needs a test,
drive `app.routers.logs.stream_logs()` directly with `asyncio`, the way
`app/jobs/worker.py`'s own manual verification did - not via TestClient.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

import app.db as db_module
from app.main import app


def _insert_source_and_folder(engine, root):
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
        conn.execute(
            text(
                "INSERT INTO directories (id, source_id, relative_path, name, parent_relative_path, "
                "has_folder_preview, last_scanned_at, created_at, updated_at) "
                "VALUES (:id, :sid, '', 'Test', NULL, 0, :now, :now, :now)"
            ),
            {"id": str(uuid.uuid4()), "sid": source_id, "now": now},
        )
    return source_id


def test_rescan_directory_job_lifecycle_over_http(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        engine = db_module.get_engine()
        _insert_source_and_folder(engine, tmp_path / "source")

        r = client.post("/api/jobs/rescan-directory", json={"path": ""})
        assert r.status_code == 200
        job = r.json()
        assert job["status"] == "queued"
        assert job["job_type"] == "rescan"

        r = client.post("/api/jobs/does-not-exist/cancel")
        assert r.status_code == 404

        deadline_statuses = {"completed", "failed", "cancelled"}
        import time

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            r = client.get(f"/api/jobs/{job['id']}")
            if r.json()["status"] in deadline_statuses:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("job did not finish via HTTP in time")

        final_job = r.json()
        assert final_job["status"] == "completed"

        r = client.get(f"/api/jobs/{job['id']}/items")
        assert len(r.json()["items"]) == 1

        r = client.get("/api/logs", params={"job_id": job["id"]})
        event_types = [e["event_type"] for e in r.json()["events"]]
        assert "job_completed" in event_types

        r = client.post(f"/api/jobs/{job['id']}/cancel")
        assert r.status_code == 409

        r = client.delete(f"/api/jobs/{job['id']}")
        assert r.status_code == 200

        r = client.get(f"/api/jobs/{job['id']}")
        assert r.status_code == 404


def test_pause_and_resume_endpoints_over_http(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        engine = db_module.get_engine()
        _insert_source_and_folder(engine, tmp_path / "source")

        r = client.post("/api/jobs/does-not-exist/pause")
        assert r.status_code == 404
        r = client.post("/api/jobs/does-not-exist/resume")
        assert r.status_code == 404

        r = client.post("/api/jobs/rescan-directory", json={"path": ""})
        job = r.json()

        deadline_statuses = {"completed", "failed", "cancelled"}
        import time

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            r = client.get(f"/api/jobs/{job['id']}")
            if r.json()["status"] in deadline_statuses:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("job did not finish via HTTP in time")
        assert r.json()["status"] == "completed"

        # Finished jobs can't be paused or resumed.
        r = client.post(f"/api/jobs/{job['id']}/pause")
        assert r.status_code == 409
        r = client.post(f"/api/jobs/{job['id']}/resume")
        assert r.status_code == 409

        # optimize_db has no per-item loop, so it's never pausable, even
        # while still queued -- checked before status, so no race with the
        # live worker thread here.
        r = client.post("/api/jobs/optimize-database")
        opt_job = r.json()
        r = client.post(f"/api/jobs/{opt_job['id']}/pause")
        assert r.status_code == 409
        assert r.json()["detail"]["error"]["code"] == "job_not_pausable"


def test_migrate_legacy_previews_job_lifecycle_over_http(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        engine = db_module.get_engine()
        source_id = _insert_source_and_folder(engine, tmp_path / "source")
        now = datetime.now(timezone.utc).isoformat()
        with engine.begin() as conn:
            clips_dir_id = str(uuid.uuid4())
            conn.execute(
                text(
                    "INSERT INTO directories (id, source_id, relative_path, name, parent_relative_path, "
                    "has_folder_preview, last_scanned_at, created_at, updated_at) "
                    "VALUES (:id, :sid, 'clips', 'clips', '', 0, :now, :now, :now)"
                ),
                {"id": clips_dir_id, "sid": source_id, "now": now},
            )
            conn.execute(
                text(
                    "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                    "size_bytes, discovered_at, last_scanned_at, is_video_supported, has_preview_asset, "
                    "created_at, updated_at) "
                    "VALUES (:id, :sid, :did, 'clips/clip_0.mp4', 'clip_0.mp4', 'mp4', 1, :now, :now, 1, 0, "
                    ":now, :now)"
                ),
                {"id": str(uuid.uuid4()), "sid": source_id, "did": clips_dir_id, "now": now},
            )

        legacy_gif = tmp_path / "source" / ".video-archive" / "previews" / "clips__clip_0.gif"
        legacy_gif.parent.mkdir(parents=True, exist_ok=True)
        legacy_gif.write_bytes(b"legacy gif bytes")
        new_gif = tmp_path / "source" / ".video-archive" / "previews" / "clips" / "clip_0.gif"

        r = client.post("/api/jobs/migrate-legacy-previews")
        assert r.status_code == 200
        job = r.json()
        assert job["job_type"] == "migrate_legacy_previews"

        deadline_statuses = {"completed", "failed", "cancelled"}
        import time

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            r = client.get(f"/api/jobs/{job['id']}")
            if r.json()["status"] in deadline_statuses:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("job did not finish via HTTP in time")
        assert r.json()["status"] == "completed"
        assert not legacy_gif.exists()
        assert new_gif.read_bytes() == b"legacy gif bytes"
