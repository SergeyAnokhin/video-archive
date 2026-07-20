"""`find_orphaned_previews()` tests (user request: "delete orphaned previews"
directory action): a `.jpg` on disk is only an orphan if it isn't a known
video's collage and isn't itself a tracked standalone image."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from app.orphan_previews import find_orphaned_previews
from app.sources import SourceAccess
from app.sources.local_backend import LocalBackend


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_file(engine, source_id, dir_id, relative_path, file_name, *, is_video=1, is_image=0):
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, is_image_supported, "
                "has_preview_asset, created_at, updated_at) "
                "VALUES (lower(hex(randomblob(16))), :sid, :did, :rel, :name, :ext, 1, :now, :now, "
                ":is_video, :is_image, 0, :now, :now)"
            ),
            {
                "sid": source_id,
                "did": dir_id,
                "rel": relative_path,
                "name": file_name,
                "ext": file_name.rsplit(".", 1)[-1],
                "is_video": is_video,
                "is_image": is_image,
                "now": _now(),
            },
        )


def _root_dir_id(engine, source_id):
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO directories (id, source_id, relative_path, name, parent_relative_path, "
                "has_folder_preview, last_scanned_at, created_at, updated_at) "
                "VALUES ('root', :sid, '', 'Root', NULL, 0, :now, :now, :now)"
            ),
            {"sid": source_id, "now": _now()},
        )
    return "root"


def test_orphan_jpg_with_no_matching_video_is_flagged(engine, source):
    dir_id = _root_dir_id(engine, source["id"])
    _insert_file(engine, source["id"], dir_id, "clip.mp4", "clip.mp4")
    (source["root"] / "clip.jpg").write_bytes(b"collage")
    (source["root"] / "orphan.jpg").write_bytes(b"stray")

    access = SourceAccess(LocalBackend(source["root"]), "local")
    orphans = find_orphaned_previews(engine, access, dir_id, "")

    assert orphans == ["orphan.jpg"]


def test_standalone_tracked_image_is_never_flagged(engine, source):
    """A `.jpg` that's itself a tracked library image (not a video collage)
    must never be treated as an orphan just because it shares the extension."""
    dir_id = _root_dir_id(engine, source["id"])
    _insert_file(engine, source["id"], dir_id, "photo.jpg", "photo.jpg", is_video=0, is_image=1)
    (source["root"] / "photo.jpg").write_bytes(b"photo")

    access = SourceAccess(LocalBackend(source["root"]), "local")
    orphans = find_orphaned_previews(engine, access, dir_id, "")

    assert orphans == []


def test_variant_files_own_collage_is_not_protected(engine, source):
    """Variant-sweep outputs borrow the original's preview and never get
    their own -- if a `<variant>.jpg` still exists on disk it's leftover and
    should be flagged, not treated as that variant's legitimate collage."""
    dir_id = _root_dir_id(engine, source["id"])
    _insert_file(engine, source["id"], dir_id, "clip.variant-d1000-crf28.mp4", "clip.variant-d1000-crf28.mp4")
    (source["root"] / "clip.variant-d1000-crf28.jpg").write_bytes(b"stray-variant-collage")

    access = SourceAccess(LocalBackend(source["root"]), "local")
    orphans = find_orphaned_previews(engine, access, dir_id, "")

    assert orphans == ["clip.variant-d1000-crf28.jpg"]


def test_no_orphans_when_every_jpg_is_accounted_for(engine, source):
    dir_id = _root_dir_id(engine, source["id"])
    _insert_file(engine, source["id"], dir_id, "clip.mp4", "clip.mp4")
    (source["root"] / "clip.jpg").write_bytes(b"collage")

    access = SourceAccess(LocalBackend(source["root"]), "local")
    orphans = find_orphaned_previews(engine, access, dir_id, "")

    assert orphans == []
