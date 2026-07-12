"""HTTP-layer tests for preview layout presets, preview settings, and the
`preview-directory`/`preview-file` job triggers, plus the image-serving
endpoints. Deliberately avoids letting an actual preview job run through the
worker here (that's covered against real ffmpeg in test_preview.py); this
file only checks request validation, job creation, and image serving.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

import app.db as db_module
from app import preview_cache
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


def test_preview_layout_preset_crud_over_http(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.get("/api/preview-layouts")
        assert r.status_code == 200
        presets = r.json()["presets"]
        assert len(presets) == 5
        builtin = next(p for p in presets if p["is_builtin"])

        r = client.put(
            f"/api/preview-layouts/{builtin['id']}",
            json={**builtin, "name": "Renamed"},
        )
        assert r.status_code == 409

        r = client.delete(f"/api/preview-layouts/{builtin['id']}")
        assert r.status_code == 409

        r = client.post(
            "/api/preview-layouts",
            json={
                "name": "Mine",
                "grid_rows": 3,
                "grid_cols": 3,
                "layout_definition": [{"row": 0, "col": 0, "span": 2}],
            },
        )
        assert r.status_code == 200
        preset = r.json()
        assert preset["is_builtin"] is False

        r = client.post(
            "/api/preview-layouts",
            json={
                "name": "Bad",
                "grid_rows": 3,
                "grid_cols": 3,
                "layout_definition": [{"row": 2, "col": 2, "span": 3}],
            },
        )
        assert r.status_code == 400
        assert r.json()["detail"]["error"]["code"] == "invalid_layout"

        r = client.delete(f"/api/preview-layouts/{preset['id']}")
        assert r.status_code == 200

        r = client.delete(f"/api/preview-layouts/{preset['id']}")
        assert r.status_code == 404


def test_preview_layout_live_preview_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.post(
            "/api/preview-layouts/preview",
            json={"grid_rows": 4, "grid_cols": 4, "layout_definition": [{"row": 0, "col": 0, "span": 2}]},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["frame_count"] == 13
        assert len(body["tiles"]) == 13


def test_preview_settings_get_and_put(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.get("/api/preview-settings")
        assert r.status_code == 200
        assert r.json()["aspect_ratio"] == "phone-landscape"
        assert r.json()["folder_preview_frame_count"] == 4
        assert r.json()["gif_max_width"] == 640
        assert r.json()["gif_colors"] == 64

        r = client.put(
            "/api/preview-settings",
            json={"aspect_ratio": "custom", "aspect_ratio_custom_width": 16, "aspect_ratio_custom_height": 10,
                  "folder_preview_frame_count": 6, "gif_max_width": 320, "gif_colors": 32},
        )
        assert r.status_code == 200
        assert r.json()["aspect_ratio"] == "custom"
        assert r.json()["folder_preview_frame_count"] == 6
        assert r.json()["gif_max_width"] == 320
        assert r.json()["gif_colors"] == 32

        r = client.put("/api/preview-settings", json={"aspect_ratio": "not-a-real-ratio"})
        assert r.status_code == 422


def test_preview_directory_requires_valid_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        engine = db_module.get_engine()
        _insert_source_and_folder(engine, tmp_path / "source")

        r = client.post("/api/jobs/preview-directory", json={"path": "does-not-exist"})
        assert r.status_code == 404
        assert r.json()["detail"]["error"]["code"] == "directory_not_found"

        r = client.post("/api/jobs/preview-directory", json={"path": "", "layout_preset_id": "missing"})
        assert r.status_code == 404
        assert r.json()["detail"]["error"]["code"] == "preview_layout_preset_not_found"

        r = client.post("/api/jobs/preview-directory", json={"path": ""})
        assert r.status_code == 200
        job = r.json()
        assert job["job_type"] == "preview"
        assert job["status"] == "queued"


def test_preview_file_requires_valid_file(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        engine = db_module.get_engine()
        _source_id, file_id = _insert_source_and_folder(engine, tmp_path / "source")

        r = client.post("/api/jobs/preview-file", json={"file_id": "missing"})
        assert r.status_code == 404
        assert r.json()["detail"]["error"]["code"] == "file_not_found"

        r = client.post("/api/jobs/preview-file", json={"file_id": file_id})
        assert r.status_code == 200
        job = r.json()
        assert job["job_type"] == "preview"
        assert job["scope_type"] == "file"


def test_file_preview_image_serving(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        engine = db_module.get_engine()
        source_root = tmp_path / "source"
        _source_id, file_id = _insert_source_and_folder(engine, source_root)

        r = client.get(f"/api/files/{file_id}/preview.jpg")
        assert r.status_code == 404

        collage_path = source_root / "clip_0.jpg"
        collage_path.write_bytes(b"\xff\xd8\xff\xd9")
        with engine.begin() as conn:
            conn.execute(text("UPDATE files SET has_preview_asset = 1 WHERE id = :id"), {"id": file_id})

        r = client.get(f"/api/files/{file_id}/preview.jpg")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/jpeg"

        r = client.get(f"/api/files/{file_id}/preview")
        assert r.status_code == 200
        assert r.json()["has_preview_asset"] is True


def test_file_preview_gif_serving(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        engine = db_module.get_engine()
        source_root = tmp_path / "source"
        _source_id, file_id = _insert_source_and_folder(engine, source_root)

        r = client.get(f"/api/files/{file_id}/preview.gif")
        assert r.status_code == 404

        gif_path = preview_cache.gif_path(_source_id, "clip_0.mp4")
        gif_path.parent.mkdir(parents=True, exist_ok=True)
        gif_path.write_bytes(b"GIF89a")

        r = client.get(f"/api/files/{file_id}/preview.gif")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/gif"


def test_directory_preview_image_serving(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        engine = db_module.get_engine()
        source_root = tmp_path / "source"
        source_id, _file_id = _insert_source_and_folder(engine, source_root)

        r = client.get("/api/directories/preview.gif", params={"path": ""})
        assert r.status_code == 404

        folder_gif = preview_cache.folder_gif_path(source_id, "")
        folder_gif.parent.mkdir(parents=True, exist_ok=True)
        folder_gif.write_bytes(b"GIF89a")
        r = client.get("/api/directories/preview.gif", params={"path": ""})
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/gif"
