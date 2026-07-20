"""Shared single-file ffprobe/mp4-probe-and-cache helper (migration 37
columns: width/height/video_codec/format_name/bit_rate/duration_seconds/
media_probed_at on `files`).

Used both by the lazy `GET /files/{file_id}/media-info` endpoint
(`app/routers/files.py`) and by a `rescan_with_media_info` job's bulk pass
(`app/jobs/rescan.py`), so the two never drift into probing or caching a
file's technical data differently.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from app import conversion, mp4_probe


def probe_and_cache(
    engine,
    access,
    file_id: str,
    relative_path: str,
    extension: str,
    size_bytes: int,
    modified_at: str,
) -> dict | None:
    """One probe attempt: `mp4_probe`'s header-only fast path first (mp4/mov/
    m4v only, no external process, works for SMB sources without a temp
    download), falling back to `local_copy()` + `conversion.probe_media()`
    (ffprobe) for anything else or when the fast path can't tell. On success,
    persists onto `files`, guarded so a slow probe can't clobber fresher data
    a concurrent request or job already wrote (`media_probed_at IS NULL AND
    size_bytes/modified_at` still matching what this probe was based on).
    Returns the probe dict, or `None` if the file couldn't be probed at all.
    """
    info = None
    if extension in ("mp4", "mov", "m4v"):
        info = mp4_probe.probe_media(access, relative_path, size_bytes)

    if info is None:
        with access.local_copy(relative_path) as local_path:
            info = conversion.probe_media(local_path)

    if info is not None:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE files
                    SET width = :width, height = :height, video_codec = :video_codec,
                        format_name = :format_name, bit_rate = :bit_rate,
                        duration_seconds = COALESCE(:duration, duration_seconds),
                        media_probed_at = :now
                    WHERE id = :id AND media_probed_at IS NULL
                      AND size_bytes = :size_bytes AND modified_at IS :modified_at
                    """
                ),
                {
                    "id": file_id,
                    "width": info.get("width"),
                    "height": info.get("height"),
                    "video_codec": info.get("video_codec_name"),
                    "format_name": info.get("format_name"),
                    "bit_rate": info.get("bit_rate"),
                    "duration": info.get("duration"),
                    "now": datetime.now(timezone.utc).isoformat(),
                    "size_bytes": size_bytes,
                    "modified_at": modified_at,
                },
            )

    return info
