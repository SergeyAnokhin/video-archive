"""`GET /api/directories/children` tests: this endpoint only feeds the
library grid, so it must filter out non-video files (added this session --
previously any file row, video or not, was returned).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

import app.db as db_module
from app.main import app


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_source_dir_and_files(engine, root):
    root.mkdir(parents=True, exist_ok=True)
    source_id = str(uuid.uuid4())
    dir_id = str(uuid.uuid4())
    now = _now()
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
                "VALUES (:id, :sid, '', 'Root', NULL, 0, :now, :now, :now)"
            ),
            {"id": dir_id, "sid": source_id, "now": now},
        )
        for file_name, supported in (("clip.mp4", 1), ("notes.txt", 0)):
            conn.execute(
                text(
                    "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                    "size_bytes, discovered_at, last_scanned_at, is_video_supported, converted_at, "
                    "has_preview_asset, created_at, updated_at) "
                    "VALUES (:id, :sid, :did, :rel, :name, :ext, 1, :now, :now, :supported, NULL, 0, :now, :now)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "sid": source_id,
                    "did": dir_id,
                    "rel": file_name,
                    "name": file_name,
                    "ext": file_name.rsplit(".", 1)[-1],
                    "supported": supported,
                    "now": now,
                },
            )


def test_directory_children_excludes_non_video_files(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        engine = db_module.get_engine()
        _insert_source_dir_and_files(engine, tmp_path / "source")

        res = client.get("/api/directories/children", params={"path": ""})
        assert res.status_code == 200
        files = res.json()["files"]

    names = {f["file_name"] for f in files}
    assert names == {"clip.mp4"}
