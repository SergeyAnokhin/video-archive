"""`find_orphaned_previews()` tests (user request: "delete orphaned previews"
directory action): a `.jpg` on disk is only an orphan if it isn't a known
video's collage and isn't itself a genuine tracked standalone image -- a
`<video file name>.jpg` (extension kept) leftover thumbnail doesn't count as
a genuine image even though `discover_filesystem()` had to track it as one."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from app.orphan_previews import delete_orphaned_previews, find_orphaned_previews
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


def test_leftover_full_filename_jpg_is_flagged_even_when_tracked_as_image(engine, source):
    """User report: a `<video file name>.jpg` -- extension kept, e.g.
    `Clip.mp4.jpg` next to `Clip.mp4` -- is a foreign thumbnail bundled by
    whatever tool downloaded the video, not this app's own collage naming
    (`<stem>.jpg`). `discover_filesystem()` doesn't recognize that naming as
    a collage, so it gets its own standalone-image `files` row -- which must
    not make it look "protected"; it should still be flagged for deletion."""
    dir_id = _root_dir_id(engine, source["id"])
    _insert_file(engine, source["id"], dir_id, "Clip.mp4", "Clip.mp4")
    _insert_file(
        engine, source["id"], dir_id, "Clip.mp4.jpg", "Clip.mp4.jpg", is_video=0, is_image=1,
    )
    (source["root"] / "Clip.mp4.jpg").write_bytes(b"leftover-thumbnail")

    access = SourceAccess(LocalBackend(source["root"]), "local")
    orphans = find_orphaned_previews(engine, access, dir_id, "")

    assert orphans == ["Clip.mp4.jpg"]


def test_delete_removes_leftover_thumbnails_tracked_files_row_too(engine, source):
    """The DB-row counterpart of the test above: a leftover-thumbnail orphan
    was tracked as its own standalone-image `files` row, so deleting it must
    also remove that row (and its tags) -- otherwise the directory listing
    keeps showing a ghost card whose thumbnail/stream now 404s, even though
    the file is genuinely gone from disk (user report)."""
    dir_id = _root_dir_id(engine, source["id"])
    _insert_file(engine, source["id"], dir_id, "Clip.mp4", "Clip.mp4")
    _insert_file(
        engine, source["id"], dir_id, "Clip.mp4.jpg", "Clip.mp4.jpg", is_video=0, is_image=1,
    )
    (source["root"] / "Clip.mp4.jpg").write_bytes(b"leftover-thumbnail")

    with engine.begin() as conn:
        file_id = conn.execute(
            text("SELECT id FROM files WHERE relative_path = 'Clip.mp4.jpg'")
        ).scalar_one()
        conn.execute(
            text(
                "INSERT INTO tag_catalog (id, tag_key, display_name, is_active, sort_order, created_at, updated_at) "
                "VALUES ('tag1', 'sample', 'sample', 1, 0, :now, :now)"
            ),
            {"now": _now()},
        )
        conn.execute(
            text(
                "INSERT INTO file_tags (id, file_id, tag_id, score, provider_name, model_name, assigned_at) "
                "VALUES ('ft1', :fid, 'tag1', 90, 'manual', NULL, :now)"
            ),
            {"fid": file_id, "now": _now()},
        )

    access = SourceAccess(LocalBackend(source["root"]), "local")
    deleted_count = delete_orphaned_previews(engine, access, dir_id, "")

    assert deleted_count == 1
    assert not (source["root"] / "Clip.mp4.jpg").exists()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT id FROM files WHERE relative_path = 'Clip.mp4.jpg'")).fetchone() is None
        assert conn.execute(text("SELECT * FROM file_tags WHERE file_id = :fid"), {"fid": file_id}).fetchone() is None
