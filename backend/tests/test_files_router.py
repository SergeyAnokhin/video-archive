"""`DELETE /api/files/{id}` and `POST /api/files/{id}/move` tests (new file
delete/move capability), plus the `is_variant`/`is_original` marker fields
added to file listing responses.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.media import preview_gif_relative_path


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


def _insert_file_with_kind(
    engine, source_id: str, dir_id: str, relative_path: str, file_name: str, *, is_video: int, is_image: int
) -> str:
    file_id = str(uuid.uuid4())
    now = _now()
    ext = file_name.rsplit(".", 1)[-1]
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, is_image_supported, "
                "converted_at, has_preview_asset, created_at, updated_at) "
                "VALUES (:id, :sid, :did, :rel, :name, :ext, 1, :now, :now, :is_video, :is_image, "
                "NULL, 0, :now, :now)"
            ),
            {
                "id": file_id,
                "sid": source_id,
                "did": dir_id,
                "rel": relative_path,
                "name": file_name,
                "ext": ext,
                "is_video": is_video,
                "is_image": is_image,
                "now": now,
            },
        )
    return file_id


def test_list_files_default_listing_includes_images_excludes_junk(engine, source):
    root_id = _insert_directory(engine, source["id"], "", None)
    video_id = _insert_file(engine, source["id"], root_id, "clip.mp4", "clip.mp4")
    image_id = _insert_file_with_kind(
        engine, source["id"], root_id, "photo.jpg", "photo.jpg", is_video=0, is_image=1
    )
    _insert_file_with_kind(engine, source["id"], root_id, "notes.txt", "notes.txt", is_video=0, is_image=0)

    with TestClient(app) as client:
        res = client.get("/api/files", params={"directory": ""})
        assert res.status_code == 200
        ids = {f["id"] for f in res.json()["files"]}
        assert ids == {video_id, image_id}

        res = client.get("/api/files", params={"directory": "", "video_only": "true"})
        assert res.status_code == 200
        assert {f["id"] for f in res.json()["files"]} == {video_id}


def test_delete_standalone_jpeg_does_not_touch_unrelated_jpg_sibling(engine, source):
    """A standalone `.jpeg` image's sibling-collage path (`with_suffix('.jpg')`)
    computes a *different*, unrelated file -- deleting it must not remove an
    unrelated same-stem `.jpg` neighbor (post-V1, edge case found while
    making images first-class library items)."""
    root_id = _insert_directory(engine, source["id"], "", None)
    (source["root"] / "photo.jpeg").write_bytes(b"jpeg-bytes")
    (source["root"] / "photo.jpg").write_bytes(b"unrelated-jpg-bytes")
    jpeg_id = _insert_file_with_kind(
        engine, source["id"], root_id, "photo.jpeg", "photo.jpeg", is_video=0, is_image=1
    )

    with TestClient(app) as client:
        res = client.delete(f"/api/files/{jpeg_id}")
        assert res.status_code == 200

    assert not (source["root"] / "photo.jpeg").exists()
    assert (source["root"] / "photo.jpg").exists()
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM files WHERE source_id = :sid AND relative_path = 'photo.jpg'"),
            {"sid": source["id"]},
        ).fetchone()
    # No DB row was ever inserted for the unrelated photo.jpg in this test,
    # so this just re-confirms the on-disk file above was left alone.
    assert row is None


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


def test_media_info_gracefully_nulls_when_unprobeable(engine, source, monkeypatch):
    # Not a real video (ffprobe will fail or be absent), so codec/resolution
    # fields should come back null rather than erroring.
    from app.routers import files as files_router

    monkeypatch.setattr(files_router.time, "sleep", lambda _seconds: None)
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
    assert body["probe_failed"] is True


def test_media_info_retries_once_after_transient_probe_failure(engine, source, monkeypatch):
    """User report: right after converting a file, the info panel showed
    size but not codec/resolution -- a freshly written file can briefly be
    unreadable by ffprobe (SMB server catch-up, antivirus scan). One bounded
    retry (`routers/files.py::get_file_media_info`, via
    `app.media_probe.probe_and_cache()`) should recover from a transient
    failure instead of giving up after a single attempt."""
    from app import media_probe
    from app.routers import files as files_router

    root_id = _insert_directory(engine, source["id"], "", None)
    (source["root"] / "clip.mp4").write_bytes(b"data")
    file_id = _insert_file(engine, source["id"], root_id, "clip.mp4", "clip.mp4")

    calls = {"count": 0}
    real_info = {
        "has_video_stream": True,
        "width": 640,
        "height": 480,
        "video_codec_name": "hevc",
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "duration": 5.0,
        "bit_rate": 100000,
    }

    def fake_probe_media(path):
        calls["count"] += 1
        return None if calls["count"] == 1 else real_info

    monkeypatch.setattr(media_probe.conversion, "probe_media", fake_probe_media)
    monkeypatch.setattr(files_router.time, "sleep", lambda _seconds: None)

    with TestClient(app) as client:
        res = client.get(f"/api/files/{file_id}/media-info")
    assert res.status_code == 200
    body = res.json()
    assert calls["count"] == 2
    assert body["probe_failed"] is False
    assert body["width"] == 640
    assert body["video_codec"] == "hevc"


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


def test_media_info_uses_cached_columns_without_probing(engine, source, monkeypatch):
    """Migration 37: once `width`/`height`/etc. and `media_probed_at` are
    populated (by a prior GET, or by the convert/preview jobs), the endpoint
    must serve the response straight from the DB row and never call
    `conversion.probe_media()` again."""
    from app import media_probe

    root_id = _insert_directory(engine, source["id"], "", None)
    (source["root"] / "clip.mp4").write_bytes(b"data")
    file_id = _insert_file(engine, source["id"], root_id, "clip.mp4", "clip.mp4")

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE files SET width = 1920, height = 1080, video_codec = 'hevc', "
                "format_name = 'mov,mp4,m4a,3gp,3g2,mj2', bit_rate = 5000000, "
                "duration_seconds = 12.5, media_probed_at = :now WHERE id = :id"
            ),
            {"now": _now(), "id": file_id},
        )

    def fail_if_called(path):
        raise AssertionError("probe_media() should not be called on a cache hit")

    monkeypatch.setattr(media_probe.conversion, "probe_media", fail_if_called)

    with TestClient(app) as client:
        res = client.get(f"/api/files/{file_id}/media-info")
    assert res.status_code == 200
    body = res.json()
    assert body["width"] == 1920
    assert body["height"] == 1080
    assert body["aspect_ratio"] == "16:9"
    assert body["video_codec"] == "hevc"
    assert body["duration"] == 12.5
    assert body["probe_failed"] is False


def test_media_info_persists_probe_result_for_next_request(engine, source, monkeypatch):
    """A cache-miss request that succeeds should populate the cache columns,
    so a second request for the same file becomes a cache hit."""
    from app import media_probe

    root_id = _insert_directory(engine, source["id"], "", None)
    (source["root"] / "clip.mp4").write_bytes(b"data")
    file_id = _insert_file(engine, source["id"], root_id, "clip.mp4", "clip.mp4")

    calls = {"count": 0}
    real_info = {
        "has_video_stream": True,
        "width": 1280,
        "height": 720,
        "video_codec_name": "h264",
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "duration": 3.0,
        "bit_rate": 200000,
    }

    def fake_probe_media(path):
        calls["count"] += 1
        return real_info

    monkeypatch.setattr(media_probe.conversion, "probe_media", fake_probe_media)

    with TestClient(app) as client:
        first = client.get(f"/api/files/{file_id}/media-info")
        assert first.status_code == 200
        assert calls["count"] == 1

        second = client.get(f"/api/files/{file_id}/media-info")
        assert second.status_code == 200
        assert calls["count"] == 1  # not called again -- served from cache
    assert second.json()["width"] == 1280


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
    collage_path = source["root"] / "clip.jpg"
    collage_path.write_bytes(b"jpg-bytes")
    gif_path = source["root"] / preview_gif_relative_path("clip.mp4")
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
