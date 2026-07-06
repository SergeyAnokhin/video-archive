"""HTTP-layer validation tests for conversion profile and convert-job
endpoints. Deliberately avoids letting an actual conversion run through the
worker here (that's covered against real ffmpeg in test_conversion.py);
this file only checks request validation and job creation.
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
        file_id = str(uuid.uuid4())
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, created_at, updated_at) "
                "SELECT :fid, :sid, d.id, 'clip_0.mp4', 'clip_0.mp4', 'mp4', 1, :now, :now, 1, :now, :now "
                "FROM directories d WHERE d.source_id = :sid AND d.relative_path = ''"
            ),
            {"fid": file_id, "sid": source_id, "now": now},
        )
    return source_id, file_id


def test_conversion_profile_crud_over_http(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.post("/api/conversion-profiles", json={"name": "Archive", "crf": 28})
        assert r.status_code == 200
        profile = r.json()
        assert profile["video_codec"] == "h265"
        assert profile["crf"] == 28

        r = client.get("/api/conversion-profiles")
        assert len(r.json()["profiles"]) == 1

        r = client.put(
            f"/api/conversion-profiles/{profile['id']}",
            json={"name": "Archive", "crf": 24, "max_dimension": 1000},
        )
        assert r.status_code == 200
        assert r.json()["crf"] == 24
        assert r.json()["max_dimension"] == 1000

        r = client.delete(f"/api/conversion-profiles/{profile['id']}")
        assert r.status_code == 200

        r = client.delete(f"/api/conversion-profiles/{profile['id']}")
        assert r.status_code == 404

        assert client.get("/api/conversion-profiles").json()["profiles"] == []


def test_convert_directory_requires_valid_profile(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        engine = db_module.get_engine()
        _insert_source_and_folder(engine, tmp_path / "source")

        r = client.post("/api/jobs/convert-directory", json={"path": "", "profile_id": "missing"})
        assert r.status_code == 404
        assert r.json()["detail"]["error"]["code"] == "conversion_profile_not_found"

        r = client.post("/api/conversion-profiles", json={"name": "P"})
        profile_id = r.json()["id"]

        r = client.post(
            "/api/jobs/convert-directory", json={"path": "does-not-exist", "profile_id": profile_id}
        )
        assert r.status_code == 404
        assert r.json()["detail"]["error"]["code"] == "directory_not_found"

        r = client.post("/api/jobs/convert-directory", json={"path": "", "profile_id": profile_id})
        assert r.status_code == 200
        job = r.json()
        assert job["job_type"] == "convert"
        assert job["status"] == "queued"


def test_convert_file_variants_require_test_mode(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        engine = db_module.get_engine()
        _source_id, file_id = _insert_source_and_folder(engine, tmp_path / "source")

        r = client.post("/api/conversion-profiles", json={"name": "P"})
        profile_id = r.json()["id"]

        r = client.post(
            "/api/jobs/convert-file",
            json={
                "file_id": file_id,
                "profile_id": profile_id,
                "mode": "production",
                "variants": [{"crf": 24}],
            },
        )
        assert r.status_code == 400
        assert r.json()["detail"]["error"]["code"] == "variants_require_test_mode"

        r = client.post(
            "/api/jobs/convert-file",
            json={
                "file_id": file_id,
                "profile_id": profile_id,
                "mode": "test",
                "variants": [{"crf": 24}, {"max_dimension": 800, "crf": 28}],
            },
        )
        assert r.status_code == 200
        job = r.json()
        assert job["parameters"]["variants"] == [{"crf": 24}, {"max_dimension": 800, "crf": 28}]

        r = client.post(
            "/api/jobs/convert-file",
            json={"file_id": "missing", "profile_id": profile_id, "mode": "production"},
        )
        assert r.status_code == 404
        assert r.json()["detail"]["error"]["code"] == "file_not_found"
