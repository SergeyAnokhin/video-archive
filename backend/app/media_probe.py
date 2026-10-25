"""Shared single-file ffprobe/mp4-probe-and-cache helper (migration 37
columns: width/height/video_codec/format_name/bit_rate/duration_seconds/
media_probed_at on `files`).

Used both by the lazy `GET /files/{file_id}/media-info` endpoint
(`app/routers/files.py`) and by a `rescan_with_media_info` job's bulk pass
(`app/jobs/rescan.py`), so the two never drift into probing or caching a
file's technical data differently. `refresh_from_source()` backs the info
panel's manual refresh (`POST /files/{file_id}/refresh`).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from app import conversion, conversion_profiles, mp4_probe


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


def infer_conversion_profile(engine, extension: str, codec_name: str | None) -> dict | None:
    """The conversion profile a file's on-disk state matches: same container
    as its extension and same ffprobe codec name. The default profile wins
    when it matches; otherwise only an unambiguous single match counts."""
    if not codec_name:
        return None
    candidates = [
        profile
        for profile in conversion_profiles.list_profiles(engine)
        if profile["container"].lower() == extension.lower()
        and conversion.ffprobe_codec_name(profile["video_codec"]) == codec_name
    ]
    default = next((profile for profile in candidates if profile["is_default"]), None)
    if default is not None:
        return default
    return candidates[0] if len(candidates) == 1 else None


def refresh_from_source(
    engine,
    access,
    file_id: str,
    relative_path: str,
    extension: str,
    size_bytes: int,
    converted_at: str | None,
) -> dict | None:
    """Manual "refresh file info" (user report: a file converted on disk kept
    showing its old size/codec forever, because the conversion's own `files`
    update never landed -- e.g. the backend restarted between replacing the
    file and writing the row -- and both refresh buttons only re-read the DB).

    Re-stats the file on the source, stores the new size/mtime, drops the
    cached probe columns, and re-probes. If the file shrank on disk, isn't
    marked converted yet, and its new codec/container matches a conversion
    profile (`infer_conversion_profile()`), it is marked converted with that
    profile. Returns the probe dict, or `None`."""
    stat = access.stat_rel(relative_path)
    shrank = stat.size < (size_bytes or 0)
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE files
                SET size_bytes = :size, modified_at = :modified_at,
                    width = NULL, height = NULL, video_codec = NULL, format_name = NULL,
                    bit_rate = NULL, duration_seconds = NULL, media_probed_at = NULL,
                    last_scanned_at = :now, updated_at = :now
                WHERE id = :id
                """
            ),
            {"id": file_id, "size": stat.size, "modified_at": stat.modified_at, "now": now},
        )

    info = probe_and_cache(engine, access, file_id, relative_path, extension, stat.size, stat.modified_at)

    if info is not None and shrank and converted_at is None:
        profile = infer_conversion_profile(engine, extension, info.get("video_codec_name"))
        if profile is not None:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        UPDATE files
                        SET converted_at = :now, last_conversion_profile_id = :profile_id
                        WHERE id = :id AND converted_at IS NULL
                        """
                    ),
                    {"id": file_id, "profile_id": profile["id"], "now": now},
                )

    return info
