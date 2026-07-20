"""`discover_filesystem()` classification tests (Data Model): video vs.
standalone image vs. a video's own `.jpg` preview collage (never an
independent row), and the interaction between the two (post-V1, user
request -- images are first-class library items too).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from app.scan import discover_filesystem, upsert_directory, upsert_file
from app.sources import SourceAccess
from app.sources.local_backend import LocalBackend


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _discover(root):
    access = SourceAccess(LocalBackend(root), "local")
    return discover_filesystem(access)


def test_standalone_image_is_classified_as_image_not_video(tmp_path):
    (tmp_path / "photo.jpg").write_bytes(b"fake-jpeg")

    _dirs, files = _discover(tmp_path)

    assert files["photo.jpg"]["is_image_supported"] is True
    assert files["photo.jpg"]["is_video_supported"] is False


def test_image_matching_video_stem_is_absorbed_as_collage_not_a_row(tmp_path):
    (tmp_path / "clip.mp4").write_bytes(b"fake-video")
    (tmp_path / "clip.jpg").write_bytes(b"fake-collage")

    _dirs, files = _discover(tmp_path)

    assert set(files) == {"clip.mp4"}
    assert files["clip.mp4"]["is_video_supported"] is True
    assert files["clip.mp4"]["has_preview_asset"] is True


def test_various_image_extensions_are_all_recognized(tmp_path):
    for name in ("a.png", "b.gif", "c.webp", "d.bmp", "e.tiff"):
        (tmp_path / name).write_bytes(b"fake-image")

    _dirs, files = _discover(tmp_path)

    for name in ("a.png", "b.gif", "c.webp", "d.bmp", "e.tiff"):
        assert files[name]["is_image_supported"] is True
        assert files[name]["is_video_supported"] is False


def test_unsupported_file_is_neither_video_nor_image(tmp_path):
    (tmp_path / "notes.txt").write_bytes(b"hello")

    _dirs, files = _discover(tmp_path)

    assert files["notes.txt"]["is_video_supported"] is False
    assert files["notes.txt"]["is_image_supported"] is False


def _make_file_row(engine, source):
    """Inserts a file row with every migration-37 cache column populated,
    as if a prior probe (GET media-info, or a convert/preview job) already
    ran. Returns (file_id, attrs) where `attrs` is the `upsert_file()`-shaped
    dict matching the row's current on-disk stat."""
    attrs = {
        "file_name": "clip.mp4",
        "extension": "mp4",
        "size_bytes": 1000,
        "modified_at": "2026-01-01T00:00:00+00:00",
        "is_video_supported": True,
        "is_image_supported": False,
        "has_preview_asset": False,
    }
    with engine.begin() as conn:
        dir_id = upsert_directory(conn, source["id"], "", "Root", None, False, _now())
        file_id = upsert_file(conn, source["id"], dir_id, "clip.mp4", attrs, _now())
        conn.execute(
            text(
                "UPDATE files SET width = 1920, height = 1080, video_codec = 'hevc', "
                "format_name = 'mov,mp4,m4a,3gp,3g2,mj2', bit_rate = 5000000, "
                "duration_seconds = 12.5, media_probed_at = :now WHERE id = :id"
            ),
            {"now": _now(), "id": file_id},
        )
    return file_id, dir_id, attrs


def test_upsert_file_keeps_cached_media_info_when_unchanged(engine, source):
    """A routine rescan that finds the same size/mtime must not touch the
    cached technical-data columns -- this is the common, no-op path and must
    stay free (no ffprobe, not even a column write)."""
    file_id, dir_id, attrs = _make_file_row(engine, source)

    with engine.begin() as conn:
        upsert_file(conn, source["id"], dir_id, "clip.mp4", attrs, _now(), existing_id=file_id)
        row = conn.execute(
            text("SELECT width, height, video_codec, duration_seconds, media_probed_at FROM files WHERE id = :id"),
            {"id": file_id},
        ).fetchone()

    assert row.width == 1920
    assert row.height == 1080
    assert row.video_codec == "hevc"
    assert row.duration_seconds == 12.5
    assert row.media_probed_at is not None


def test_upsert_file_clears_cached_media_info_when_file_changed(engine, source):
    """A rescan that detects a different size (the file was replaced on
    disk outside the app) must invalidate every cached technical-data
    column, so the next media-info request re-probes instead of showing
    stale data for the new bytes."""
    file_id, dir_id, attrs = _make_file_row(engine, source)

    changed_attrs = {**attrs, "size_bytes": 2000}
    with engine.begin() as conn:
        upsert_file(conn, source["id"], dir_id, "clip.mp4", changed_attrs, _now(), existing_id=file_id)
        row = conn.execute(
            text(
                "SELECT width, height, video_codec, format_name, bit_rate, "
                "duration_seconds, media_probed_at FROM files WHERE id = :id"
            ),
            {"id": file_id},
        ).fetchone()

    assert row.width is None
    assert row.height is None
    assert row.video_codec is None
    assert row.format_name is None
    assert row.bit_rate is None
    assert row.duration_seconds is None
    assert row.media_probed_at is None
