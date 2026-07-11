"""`DELETE /api/files/{id}` and `POST /api/files/{id}/move` tests (new file
delete/move capability), plus the `is_variant`/`is_original` marker fields
added to file listing responses.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

from app import preview_cache
from app.main import app


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_directory(engine, source_id: str, relative_path: str, parent: str | None) -> str:
    dir_id = str(uuid.uuid4())
    now = _now()
    name = relative_path.rsplit("/", 1)[-1] if relative_path else "Root"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO directories (id, source_id, relative_path, name, parent_relative_path, "
                "has_folder_preview, last_scanned_at, created_at, updated_at) "
                "VALUES (:id, :sid, :rel, :name, :parent, 0, :now, :now, :now)"
            ),
            {"id": dir_id, "sid": source_id, "rel": relative_path, "name": name, "parent": parent, "now": now},
        )
    return dir_id


def _insert_file(engine, source_id: str, dir_id: str, relative_path: str, file_name: str) -> str:
    file_id = str(uuid.uuid4())
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, converted_at, "
                "has_preview_asset, created_at, updated_at) "
                "VALUES (:id, :sid, :did, :rel, :name, 'mp4', 1, :now, :now, 1, NULL, 0, :now, :now)"
            ),
            {"id": file_id, "sid": source_id, "did": dir_id, "rel": relative_path, "name": file_name, "now": now},
        )
    return file_id


def test_delete_file_removes_disk_file_and_db_row(engine, source):
    root_id = _insert_directory(engine, source["id"], "", None)
    video_path = source["root"] / "clip.mp4"
    video_path.write_bytes(b"data")
    file_id = _insert_file(engine, source["id"], root_id, "clip.mp4", "clip.mp4")

    with TestClient(app) as client:
        res = client.delete(f"/api/files/{file_id}")
        assert res.status_code == 200
        assert res.json() == {"deleted": True}

        assert not video_path.exists()
        with engine.connect() as conn:
            row = conn.execute(text("SELECT id FROM files WHERE id = :id"), {"id": file_id}).fetchone()
        assert row is None

        assert client.get(f"/api/files/{file_id}").status_code == 404


def test_delete_file_also_removes_preview_assets(engine, source):
    root_id = _insert_directory(engine, source["id"], "", None)
    (source["root"] / "clip.mp4").write_bytes(b"data")
    (source["root"] / "clip.jpg").write_bytes(b"jpg")
    previews_dir = source["root"] / ".video-archive" / "previews"
    previews_dir.mkdir(parents=True)
    (previews_dir / "clip.gif").write_bytes(b"gif")
    file_id = _insert_file(engine, source["id"], root_id, "clip.mp4", "clip.mp4")

    with TestClient(app) as client:
        res = client.delete(f"/api/files/{file_id}")
        assert res.status_code == 200

    assert not (source["root"] / "clip.jpg").exists()
    assert not (previews_dir / "clip.gif").exists()


def test_delete_file_not_found(engine, source):
    with TestClient(app) as client:
        res = client.delete(f"/api/files/{uuid.uuid4()}")
    assert res.status_code == 404


def test_media_info_not_found(engine, source):
    with TestClient(app) as client:
        res = client.get(f"/api/files/{uuid.uuid4()}/media-info")
    assert res.status_code == 404


def test_media_info_gracefully_nulls_when_unprobeable(engine, source):
    # Not a real video (ffprobe will fail or be absent), so codec/resolution
    # fields should come back null rather than erroring.
    root_id = _insert_directory(engine, source["id"], "", None)
    (source["root"] / "clip.mp4").write_bytes(b"not actually a video")
    file_id = _insert_file(engine, source["id"], root_id, "clip.mp4", "clip.mp4")

    with TestClient(app) as client:
        res = client.get(f"/api/files/{file_id}/media-info")
    assert res.status_code == 200
    body = res.json()
    assert body["width"] is None
    assert body["aspect_ratio"] is None
    assert body["conversion_profile"] is None


def test_media_info_includes_conversion_profile_used(engine, source):
    root_id = _insert_directory(engine, source["id"], "", None)
    (source["root"] / "clip.mp4").write_bytes(b"data")
    file_id = _insert_file(engine, source["id"], root_id, "clip.mp4", "clip.mp4")

    profile_id = str(uuid.uuid4())
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO conversion_profiles (id, name, is_default, video_codec, container, "
                "max_dimension, crf, drop_audio, created_at, updated_at) "
                "VALUES (:id, 'My Profile', 0, 'h265', 'mp4', 1024, 28, 0, :now, :now)"
            ),
            {"id": profile_id, "now": now},
        )
        conn.execute(
            text("UPDATE files SET last_conversion_profile_id = :pid WHERE id = :id"),
            {"pid": profile_id, "id": file_id},
        )

    with TestClient(app) as client:
        res = client.get(f"/api/files/{file_id}/media-info")
    assert res.status_code == 200
    body = res.json()
    assert body["conversion_profile"]["id"] == profile_id
    assert body["conversion_profile"]["name"] == "My Profile"


def test_move_file_updates_path_and_directory(engine, source):
    root_id = _insert_directory(engine, source["id"], "", None)
    dest_id = _insert_directory(engine, source["id"], "dest", "")
    (source["root"] / "dest").mkdir()
    (source["root"] / "clip.mp4").write_bytes(b"data")
    file_id = _insert_file(engine, source["id"], root_id, "clip.mp4", "clip.mp4")

    with TestClient(app) as client:
        res = client.post(f"/api/files/{file_id}/move", json={"target_directory": "dest"})
        assert res.status_code == 200
        body = res.json()
        assert body["relative_path"] == "dest/clip.mp4"
        assert body["directory_path"] == "dest"

        assert not (source["root"] / "clip.mp4").exists()
        assert (source["root"] / "dest" / "clip.mp4").exists()

        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT relative_path, directory_id FROM files WHERE id = :id"), {"id": file_id}
            ).fetchone()
        assert row.relative_path == "dest/clip.mp4"
        assert row.directory_id == dest_id


def test_move_file_also_moves_preview_assets(engine, source):
    root_id = _insert_directory(engine, source["id"], "", None)
    _insert_directory(engine, source["id"], "dest", "")
    (source["root"] / "dest").mkdir()
    (source["root"] / "clip.mp4").write_bytes(b"data")
    (source["root"] / "clip.jpg").write_bytes(b"jpg")
    previews_dir = source["root"] / ".video-archive" / "previews"
    previews_dir.mkdir(parents=True)
    (previews_dir / "clip.gif").write_bytes(b"gif")
    file_id = _insert_file(engine, source["id"], root_id, "clip.mp4", "clip.mp4")

    with TestClient(app) as client:
        res = client.post(f"/api/files/{file_id}/move", json={"target_directory": "dest"})
        assert res.status_code == 200

    assert (source["root"] / "dest" / "clip.jpg").exists()
    assert (previews_dir / "dest__clip.gif").exists()


def test_move_file_rejects_destination_collision(engine, source):
    root_id = _insert_directory(engine, source["id"], "", None)
    dest_id = _insert_directory(engine, source["id"], "dest", "")
    (source["root"] / "dest").mkdir()
    (source["root"] / "clip.mp4").write_bytes(b"data")
    (source["root"] / "dest" / "clip.mp4").write_bytes(b"existing")
    file_id = _insert_file(engine, source["id"], root_id, "clip.mp4", "clip.mp4")
    _insert_file(engine, source["id"], dest_id, "dest/clip.mp4", "clip.mp4")

    with TestClient(app) as client:
        res = client.post(f"/api/files/{file_id}/move", json={"target_directory": "dest"})
    assert res.status_code == 409


def test_move_file_rejects_unknown_directory(engine, source):
    root_id = _insert_directory(engine, source["id"], "", None)
    (source["root"] / "clip.mp4").write_bytes(b"data")
    file_id = _insert_file(engine, source["id"], root_id, "clip.mp4", "clip.mp4")

    with TestClient(app) as client:
        res = client.post(f"/api/files/{file_id}/move", json={"target_directory": "nope"})
    assert res.status_code == 404


def test_variant_preview_falls_back_to_original_asset(engine, source):
    # A variant-sweep output never gets its own preview generated
    # (Specification §8.3), so it must reuse the original's `.jpg`/`.gif`
    # instead of showing a broken thumbnail.
    root_id = _insert_directory(engine, source["id"], "", None)
    (source["root"] / "clip.mp4").write_bytes(b"data")
    collage_path = preview_cache.collage_path(source["id"], "clip.mp4")
    collage_path.parent.mkdir(parents=True, exist_ok=True)
    collage_path.write_bytes(b"jpg-bytes")
    gif_path = preview_cache.gif_path(source["id"], "clip.mp4")
    gif_path.parent.mkdir(parents=True, exist_ok=True)
    gif_path.write_bytes(b"gif-bytes")
    _insert_file(engine, source["id"], root_id, "clip.mp4", "clip.mp4")
    variant_id = _insert_file(engine, source["id"], root_id, "clip.variant-crf28.mp4", "clip.variant-crf28.mp4")
    with engine.begin() as conn:
        conn.execute(text("UPDATE files SET has_preview_asset = 1 WHERE id = :id"), {"id": variant_id})

    with TestClient(app) as client:
        meta = client.get(f"/api/files/{variant_id}/preview")
        assert meta.status_code == 200
        assert meta.json()["has_preview_asset"] is True

        jpg = client.get(f"/api/files/{variant_id}/preview.jpg")
        assert jpg.status_code == 200
        assert jpg.content == b"jpg-bytes"

        gif = client.get(f"/api/files/{variant_id}/preview.gif")
        assert gif.status_code == 200
        assert gif.content == b"gif-bytes"


def _insert_tag_assignment(engine, file_id: str, tag_key: str) -> None:
    now = _now()
    with engine.begin() as conn:
        row = conn.execute(text("SELECT id FROM tag_catalog WHERE tag_key = :key"), {"key": tag_key}).fetchone()
        tag_id = row.id if row else str(uuid.uuid4())
        if row is None:
            conn.execute(
                text(
                    "INSERT INTO tag_catalog (id, tag_key, display_name, is_active, sort_order, created_at, updated_at) "
                    "VALUES (:id, :key, :key, 1, 0, :now, :now)"
                ),
                {"id": tag_id, "key": tag_key, "now": now},
            )
        conn.execute(
            text(
                "INSERT INTO file_tags (id, file_id, tag_id, score, provider_name, model_name, assigned_at) "
                "VALUES (:id, :fid, :tid, 90, 'manual', NULL, :now)"
            ),
            {"id": str(uuid.uuid4()), "fid": file_id, "tid": tag_id, "now": now},
        )


def test_list_files_tag_search_matches_tag_key_substring(engine, source):
    root_id = _insert_directory(engine, source["id"], "", None)
    garden_id = _insert_file(engine, source["id"], root_id, "a.mp4", "a.mp4")
    party_id = _insert_file(engine, source["id"], root_id, "b.mp4", "b.mp4")
    _insert_file(engine, source["id"], root_id, "c.mp4", "c.mp4")
    _insert_tag_assignment(engine, garden_id, "gardening")
    _insert_tag_assignment(engine, party_id, "party")

    with TestClient(app) as client:
        res = client.get("/api/files", params={"tag_search": "garden"})
        assert res.status_code == 200
        assert [f["id"] for f in res.json()["files"]] == [garden_id]

        # substring, not prefix: "arden" still matches "gardening"
        res = client.get("/api/files", params={"tag_search": "arden"})
        assert [f["id"] for f in res.json()["files"]] == [garden_id]

        res = client.get("/api/files", params={"tag_search": "nothing"})
        assert res.json()["files"] == []


def test_file_listing_flags_variant_and_original_markers(engine, source):
    root_id = _insert_directory(engine, source["id"], "", None)
    _insert_file(engine, source["id"], root_id, "clip.mp4", "clip.mp4")
    _insert_file(engine, source["id"], root_id, "clip.variant-crf28.mp4", "clip.variant-crf28.mp4")
    _insert_file(engine, source["id"], root_id, "clip.original.mp4", "clip.original.mp4")

    with TestClient(app) as client:
        res = client.get("/api/files", params={"directory": ""})
        assert res.status_code == 200
        by_name = {f["file_name"]: f for f in res.json()["files"]}

    assert by_name["clip.mp4"]["is_variant"] is False
    assert by_name["clip.mp4"]["is_original"] is False
    assert by_name["clip.variant-crf28.mp4"]["is_variant"] is True
    assert by_name["clip.original.mp4"]["is_original"] is True
