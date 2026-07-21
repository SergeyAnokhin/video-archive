"""Detects `.jpg` preview-collage files that sit in a directory but are no
longer referenced by any video row known in that directory (user request:
folders occasionally accumulate stray collages after a video was renamed,
moved, or deleted outside the app). Scoped to a single, non-recursive
directory -- the animated-GIF preview cache under `.video-archive/previews/`
is a separate, whole-cache-scoped concern (`app/preview_assets.py`) and is
out of scope here.
"""

from __future__ import annotations

import logging
from pathlib import PurePosixPath

from sqlalchemy import text

from app import file_ops
from app.media import preview_gif_relative_path, sibling_relative_path, variant_base_stem

logger = logging.getLogger(__name__)


def find_orphaned_previews(
    engine, access, directory_id: str, directory_relative_path: str
) -> list[str]:
    """Returns the relative paths of `.jpg` files physically present directly
    in `directory_relative_path` that aren't a known file's collage preview
    and aren't themselves a tracked standalone image (post-V1: `.jpg` is also
    a supported first-class image type, `app/media.py`'s
    `SUPPORTED_IMAGE_EXTENSIONS`) -- so a real library image is never treated
    as an orphan just because it happens to be a `.jpg`.

    User report: some folders (bulk-downloaded content) contain a leftover
    `<video file name>.jpg` -- the *full* video file name, extension and all
    (e.g. `Clip.mp4.jpg` next to `Clip.mp4`) -- rather than this app's own
    collage naming (`<stem>.jpg`, extension stripped). `discover_filesystem()`
    doesn't recognize that naming as a video's collage, so it ends up tracked
    as its own standalone-image `files` row, which used to make it look like
    a "real library image" here and get protected from deletion -- exactly
    backwards, since it's virtually always a foreign thumbnail bundled with
    the video by whatever tool downloaded it, not a genuine photo. Any `.jpg`
    whose name (minus the `.jpg`) case-insensitively matches a video file's
    full name in the same directory is therefore never protected, regardless
    of how it got classified during scan."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT relative_path, file_name, is_video_supported, is_image_supported "
                "FROM files WHERE directory_id = :dir_id"
            ),
            {"dir_id": directory_id},
        ).all()

    video_file_names = {row.file_name.lower() for row in rows if row.is_video_supported}

    protected: set[str] = set()
    for row in rows:
        if row.is_video_supported and variant_base_stem(row.file_name) is None:
            stem = PurePosixPath(row.file_name).stem
            protected.add(sibling_relative_path(row.relative_path, f"{stem}.jpg"))
        if row.is_image_supported and row.file_name.lower().endswith(".jpg"):
            looks_like_leftover_video_thumbnail = row.file_name[: -len(".jpg")].lower() in video_file_names
            if not looks_like_leftover_video_thumbnail:
                protected.add(row.relative_path)

    actual: set[str] = set()
    for entry in access.scandir(directory_relative_path):
        if entry.is_dir or not entry.name.lower().endswith(".jpg"):
            continue
        rel = f"{directory_relative_path}/{entry.name}" if directory_relative_path else entry.name
        actual.add(rel)

    return sorted(actual - protected)


def delete_orphaned_previews(
    engine, access, directory_id: str, directory_relative_path: str
) -> int:
    """Deletes every orphan `find_orphaned_previews()` finds, tolerating a
    single file's removal failure so it doesn't abort the rest of the batch.

    A "leftover video thumbnail" orphan (`<video file name>.jpg`, see
    `find_orphaned_previews()`'s docstring) was tracked as its own
    standalone-image `files` row by `discover_filesystem()` -- removing only
    the on-disk file and leaving that row behind would keep it showing up in
    the directory listing (and its now-gone thumbnail/stream would 404), so
    any matching row (plus its `file_tags`/`file_similarity_signatures` and
    GIF preview asset, mirroring `file_ops.delete_file()`) is cleaned up too."""
    orphans = find_orphaned_previews(engine, access, directory_id, directory_relative_path)

    deleted_count = 0
    for rel_path in orphans:
        try:
            access.remote_remove(rel_path)
        except Exception as exc:  # noqa: BLE001 - one file's failure must not abort the batch
            logger.warning("Failed to delete orphaned preview %s: %s", rel_path, exc)
            continue
        deleted_count += 1

        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT id FROM files WHERE directory_id = :dir_id AND relative_path = :rel"),
                {"dir_id": directory_id, "rel": rel_path},
            ).fetchone()
            if row is not None:
                gif_rel = preview_gif_relative_path(rel_path)
                if access.exists(gif_rel):
                    access.remote_remove(gif_rel)
                file_ops.delete_file_rows(conn, row.id)

    return deleted_count
