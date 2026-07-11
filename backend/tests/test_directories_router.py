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


def _insert_video_file(engine, source_id: str, dir_id: str, file_name: str) -> str:
    file_id = str(uuid.uuid4())
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, has_preview_asset, "
                "created_at, updated_at) "
                "VALUES (:id, :sid, :did, :rel, :name, 'mp4', 1, :now, :now, 1, 0, :now, :now)"
            ),
            {"id": file_id, "sid": source_id, "did": dir_id, "rel": file_name, "name": file_name, "now": now},
        )
    return file_id


def test_directory_children_tags_variant_files_with_the_swept_parameter(engine, source):
    dir_id = str(uuid.uuid4())
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO directories (id, source_id, relative_path, name, parent_relative_path, "
                "has_folder_preview, last_scanned_at, created_at, updated_at) "
                "VALUES (:id, :sid, '', 'Root', NULL, 0, :now, :now, :now)"
            ),
            {"id": dir_id, "sid": source["id"], "now": now},
        )
    _insert_video_file(engine, source["id"], dir_id, "clip.mp4")
    variant_a = _insert_video_file(engine, source["id"], dir_id, "clip.variant-d960-crf26.mp4")
    variant_b = _insert_video_file(engine, source["id"], dir_id, "clip.variant-d1920-crf26.mp4")

    with TestClient(app) as client:
        res = client.get("/api/directories/children", params={"path": ""})
        assert res.status_code == 200
        by_id = {f["id"]: f for f in res.json()["files"]}

    assert by_id[variant_a]["variant_tags"] == [{"param": "dimension", "value": 960}]
    assert by_id[variant_b]["variant_tags"] == [{"param": "dimension", "value": 1920}]


def _insert_dir(engine, source_id: str, relative_path: str, name: str, parent: str) -> None:
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO directories (id, source_id, relative_path, name, parent_relative_path, "
                "has_folder_preview, last_scanned_at, created_at, updated_at) "
                "VALUES (:id, :sid, :rel, :name, :parent, 0, :now, :now, :now)"
            ),
            {"id": str(uuid.uuid4()), "sid": source_id, "rel": relative_path, "name": name, "parent": parent, "now": now},
        )


def test_search_directories_matches_name_substring(engine, source):
    _insert_dir(engine, source["id"], "", "Root", None)
    _insert_dir(engine, source["id"], "Family", "Family", "")
    _insert_dir(engine, source["id"], "Family/Birthdays", "Birthdays", "Family")
    _insert_dir(engine, source["id"], "Work", "Work", "")

    with TestClient(app) as client:
        res = client.get("/api/directories/search", params={"q": "fam"})
        assert res.status_code == 200
        entries = res.json()["directories"]
        # matches the folder's own name only, not the full path -- "Birthdays"
        # lives under Family/ but its name doesn't contain "fam"
        assert [e["path"] for e in entries] == ["Family"]
        assert entries[0]["name"] == "Family"

        res = client.get("/api/directories/search", params={"q": "day"})
        assert [e["path"] for e in res.json()["directories"]] == ["Family/Birthdays"]

        res = client.get("/api/directories/search", params={"q": "a", "limit": 1, "offset": 1})
        assert len(res.json()["directories"]) == 1

        res = client.get("/api/directories/search", params={"q": "zzz"})
        assert res.json()["directories"] == []


def test_directory_children_variant_borrows_original_has_preview_asset(engine, source):
    """A variant-sweep output never gets its own preview generated
    (Specification §8.3); the listing should report `has_preview_asset` as
    true for it whenever its original sibling has one, so the grid shows a
    thumbnail instead of a fallback icon (user request)."""
    dir_id = str(uuid.uuid4())
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO directories (id, source_id, relative_path, name, parent_relative_path, "
                "has_folder_preview, last_scanned_at, created_at, updated_at) "
                "VALUES (:id, :sid, '', 'Root', NULL, 0, :now, :now, :now)"
            ),
            {"id": dir_id, "sid": source["id"], "now": now},
        )
    original_id = _insert_video_file(engine, source["id"], dir_id, "clip.mp4")
    variant_id = _insert_video_file(engine, source["id"], dir_id, "clip.variant-crf28.mp4")
    with engine.begin() as conn:
        conn.execute(text("UPDATE files SET has_preview_asset = 1 WHERE id = :id"), {"id": original_id})

    with TestClient(app) as client:
        res = client.get("/api/directories/children", params={"path": ""})
        assert res.status_code == 200
        by_id = {f["id"]: f for f in res.json()["files"]}

    assert by_id[original_id]["has_preview_asset"] is True
    assert by_id[variant_id]["has_preview_asset"] is True
