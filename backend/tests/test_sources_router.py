"""HTTP-layer tests for `/api/sources*` (saved-sources list, switching, and
per-source preview-cache management -- user request, see `app/routers/
sources.py`/`app/source_switch.py`)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

from app import preview_cache
from app.jobs import service
from app.main import app


def _insert_source(engine, name: str, root_path, is_active: bool) -> str:
    source_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sources (id, name, protocol, root_path, is_active, created_at, updated_at) "
                "VALUES (:id, :name, 'local', :root, :active, :now, :now)"
            ),
            {"id": source_id, "name": name, "root": str(root_path), "active": 1 if is_active else 0, "now": now},
        )
    return source_id


def _seed_previewed_file(engine, source_id: str) -> tuple[str, str]:
    """One directory + one file, both already marked as previewed."""
    now = datetime.now(timezone.utc).isoformat()
    dir_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO directories (id, source_id, relative_path, name, parent_relative_path, "
                "has_folder_preview, folder_preview_generated_at, last_scanned_at, created_at, updated_at) "
                "VALUES (:id, :sid, '', 'Root', NULL, 1, :now, :now, :now, :now)"
            ),
            {"id": dir_id, "sid": source_id, "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, has_preview_asset, "
                "preview_generated_at, created_at, updated_at) "
                "VALUES (:id, :sid, :did, 'clip.mp4', 'clip.mp4', 'mp4', 1, :now, :now, 1, 1, :now, :now, :now)"
            ),
            {"id": file_id, "sid": source_id, "did": dir_id, "now": now},
        )
    return dir_id, file_id


def test_list_sources_includes_preview_cache_stats(engine, source, tmp_path):
    root_b = tmp_path / "b"
    root_b.mkdir()
    _insert_source(engine, "B", root_b, is_active=False)

    gif = preview_cache.gif_path(source["id"], "clip.mp4")
    gif.parent.mkdir(parents=True, exist_ok=True)
    gif.write_bytes(b"gif-bytes")

    with TestClient(app) as client:
        r = client.get("/api/sources")
        assert r.status_code == 200
        by_name = {row["name"]: row for row in r.json()["sources"]}

    assert set(by_name) == {"Test", "B"}
    assert by_name["Test"]["is_active"] is True
    assert by_name["Test"]["preview_cache"] == {"size_bytes": len(b"gif-bytes"), "file_count": 1}
    assert by_name["B"]["is_active"] is False
    assert by_name["B"]["preview_cache"] == {"size_bytes": 0, "file_count": 0}


def test_activate_switches_source_and_reflects_its_own_files(engine, source, tmp_path):
    root_b = tmp_path / "b"
    root_b.mkdir()
    (root_b / "other.mp4").write_bytes(b"0")
    b_id = _insert_source(engine, "B", root_b, is_active=False)

    with TestClient(app) as client:
        r = client.post(f"/api/sources/{b_id}/activate")
        assert r.status_code == 200
        assert r.json()["id"] == b_id
        assert r.json()["is_active"] is True

        r = client.get("/api/source")
        assert r.json()["id"] == b_id

        r = client.get("/api/files")
        assert [f["file_name"] for f in r.json()["files"]] == ["other.mp4"]


def test_activate_already_active_source_is_a_noop(engine, source):
    service.create_job(engine, "cleanup", "maintenance", None, {})

    with TestClient(app) as client:
        assert client.get("/api/jobs").json()["jobs"]

        r = client.post(f"/api/sources/{source['id']}/activate")
        assert r.status_code == 200
        assert r.json()["auto_restored"] is None

        assert client.get("/api/jobs").json()["jobs"]


def test_activate_unknown_source_404s(engine, source):
    with TestClient(app) as client:
        r = client.post("/api/sources/does-not-exist/activate")
        assert r.status_code == 404
        assert r.json()["detail"]["error"]["code"] == "source_not_found"


def test_forget_refuses_the_active_source(engine, source):
    with TestClient(app) as client:
        r = client.delete(f"/api/sources/{source['id']}")
        assert r.status_code == 400
        assert r.json()["detail"]["error"]["code"] == "active_source"


def test_forget_removes_an_inactive_source_and_its_preview_cache(engine, source, tmp_path):
    root_b = tmp_path / "b"
    root_b.mkdir()
    b_id = _insert_source(engine, "B", root_b, is_active=False)
    gif = preview_cache.gif_path(b_id, "clip.mp4")
    gif.parent.mkdir(parents=True, exist_ok=True)
    gif.write_bytes(b"gif-bytes")

    with TestClient(app) as client:
        r = client.delete(f"/api/sources/{b_id}")
        assert r.status_code == 200
        assert r.json()["deleted"] is True

        remaining_ids = {row["id"] for row in client.get("/api/sources").json()["sources"]}
        assert b_id not in remaining_ids
    assert not preview_cache.preview_cache_dir_for_source(b_id).exists()


def test_clear_preview_cache_for_active_source_resets_db_flags(engine, source):
    dir_id, file_id = _seed_previewed_file(engine, source["id"])
    gif = preview_cache.gif_path(source["id"], "clip.mp4")
    gif.parent.mkdir(parents=True, exist_ok=True)
    gif.write_bytes(b"gif-bytes")

    with TestClient(app) as client:
        r = client.delete(f"/api/sources/{source['id']}/preview-cache")
        assert r.status_code == 200
        assert r.json()["cleared"] is True

    assert not gif.exists()
    with engine.connect() as conn:
        file_row = conn.execute(
            text("SELECT has_preview_asset, preview_generated_at FROM files WHERE id = :id"), {"id": file_id}
        ).fetchone()
        dir_row = conn.execute(
            text("SELECT has_folder_preview, folder_preview_generated_at FROM directories WHERE id = :id"),
            {"id": dir_id},
        ).fetchone()
    assert file_row.has_preview_asset == 0
    assert file_row.preview_generated_at is None
    assert dir_row.has_folder_preview == 0
    assert dir_row.folder_preview_generated_at is None


def test_clear_preview_cache_for_inactive_source_only_touches_its_own_cache(engine, source, tmp_path):
    root_b = tmp_path / "b"
    root_b.mkdir()
    b_id = _insert_source(engine, "B", root_b, is_active=False)

    active_gif = preview_cache.gif_path(source["id"], "clip.mp4")
    active_gif.parent.mkdir(parents=True, exist_ok=True)
    active_gif.write_bytes(b"gif-bytes")
    b_gif = preview_cache.gif_path(b_id, "other.mp4")
    b_gif.parent.mkdir(parents=True, exist_ok=True)
    b_gif.write_bytes(b"gif-bytes")

    with TestClient(app) as client:
        r = client.delete(f"/api/sources/{b_id}/preview-cache")
        assert r.status_code == 200

    assert not b_gif.exists()
    assert active_gif.exists()
