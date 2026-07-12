"""Local, per-source cache for generated GIF preview assets (per-file gif,
folder gif). Kept on the backend's own disk rather than written back to the
source itself (user request): fast to read regardless of source protocol (no
SMB round-trip per thumbnail), and it survives switching to another source
and back without regenerating, since it's keyed by `source_id` rather than
tied to whichever source is currently active.

The JPEG collage is *not* cached here -- it's written next to the video on
the source itself (user request, `app/jobs/preview.py`'s `_generate_one_file`
via `access.commit_new_file`), so it can be browsed/backed up alongside the
video like any other sibling file.

`PREVIEW_CACHE_DIR` is imported by value below, so tests must patch
`app.preview_cache.PREVIEW_CACHE_DIR` directly rather than `app.config`'s
(same convention as `app/secrets_store.py`'s `SECRETS_PATH`) -- see
`tests/conftest.py`'s `isolated_preview_cache` fixture.
"""

from __future__ import annotations

import shutil
from pathlib import Path, PurePosixPath

from app.config import PREVIEW_CACHE_DIR
from app.media import preview_gif_relative_path


def preview_cache_dir_for_source(source_id: str) -> Path:
    return PREVIEW_CACHE_DIR / source_id


def _to_path(rel: str) -> Path:
    return Path(*PurePosixPath(rel).parts)


def gif_path(source_id: str, relative_path: str) -> Path:
    return preview_cache_dir_for_source(source_id) / _to_path(preview_gif_relative_path(relative_path))


def folder_gif_path(source_id: str, directory_relative_path: str) -> Path:
    dest_rel = f"{directory_relative_path}/folder-preview.gif" if directory_relative_path else "folder-preview.gif"
    return preview_cache_dir_for_source(source_id) / _to_path(dest_rel)


def cache_stats(source_id: str) -> dict:
    root = preview_cache_dir_for_source(source_id)
    size_bytes = 0
    file_count = 0
    if root.is_dir():
        for path in root.rglob("*"):
            if path.is_file():
                size_bytes += path.stat().st_size
                file_count += 1
    return {"size_bytes": size_bytes, "file_count": file_count}


def clear_cache(source_id: str) -> None:
    shutil.rmtree(preview_cache_dir_for_source(source_id), ignore_errors=True)
