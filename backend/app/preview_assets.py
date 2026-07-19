"""Operations on the animated GIF preview assets (per-file gif, folder gif)
living in the active source's own technical folder (`app/media.py`'s
`PREVIEW_GIF_DIR`, `.video-archive/previews/`) -- written there via
`SourceAccess.commit_new_file()` by `app/jobs/preview.py`, same as the JPEG
collage. Only ever meaningful for the active source: computing stats or
clearing requires a live `SourceAccess`, so callers must not invoke these for
an inactive saved source (`app/routers/sources.py`).
"""

from __future__ import annotations

from app.media import PREVIEW_GIF_DIR
from app.sources import SourceAccess


def stats_for_active_source(access: SourceAccess) -> dict:
    size_bytes = 0
    file_count = 0
    for _dir_rel, _parent_rel, entries in access.walk(PREVIEW_GIF_DIR):
        for entry in entries:
            if not entry.is_dir:
                size_bytes += entry.stat.size
                file_count += 1
    return {"size_bytes": size_bytes, "file_count": file_count}


def clear_for_active_source(access: SourceAccess) -> None:
    dirs_found: list[str] = []
    for dir_rel, _parent_rel, entries in access.walk(PREVIEW_GIF_DIR):
        dirs_found.append(dir_rel)
        for entry in entries:
            if not entry.is_dir:
                file_rel = f"{dir_rel}/{entry.name}" if dir_rel else entry.name
                access.remote_remove(file_rel)

    for dir_rel in sorted(dirs_found, key=lambda d: d.count("/"), reverse=True):
        if access.exists(dir_rel):
            access.remote_rmdir(dir_rel)
