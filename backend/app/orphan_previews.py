"""Detects `.jpg` preview-collage files that sit in a directory but are no
longer referenced by any video row known in that directory (user request:
folders occasionally accumulate stray collages after a video was renamed,
moved, or deleted outside the app). Scoped to a single, non-recursive
directory -- the animated-GIF preview cache under `.video-archive/previews/`
is a separate, whole-cache-scoped concern (`app/preview_assets.py`) and is
out of scope here.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from sqlalchemy import text

from app.media import sibling_relative_path, variant_base_stem


def find_orphaned_previews(
    engine, access, directory_id: str, directory_relative_path: str
) -> list[str]:
    """Returns the relative paths of `.jpg` files physically present directly
    in `directory_relative_path` that aren't a known file's collage preview
    and aren't themselves a tracked standalone image (post-V1: `.jpg` is also
    a supported first-class image type, `app/media.py`'s
    `SUPPORTED_IMAGE_EXTENSIONS`) -- so a real library image is never treated
    as an orphan just because it happens to be a `.jpg`."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT relative_path, file_name, is_video_supported, is_image_supported "
                "FROM files WHERE directory_id = :dir_id"
            ),
            {"dir_id": directory_id},
        ).all()

    protected: set[str] = set()
    for row in rows:
        if row.is_video_supported and variant_base_stem(row.file_name) is None:
            stem = PurePosixPath(row.file_name).stem
            protected.add(sibling_relative_path(row.relative_path, f"{stem}.jpg"))
        if row.is_image_supported and row.file_name.lower().endswith(".jpg"):
            protected.add(row.relative_path)

    actual: set[str] = set()
    for entry in access.scandir(directory_relative_path):
        if entry.is_dir or not entry.name.lower().endswith(".jpg"):
            continue
        rel = f"{directory_relative_path}/{entry.name}" if directory_relative_path else entry.name
        actual.add(rel)

    return sorted(actual - protected)
