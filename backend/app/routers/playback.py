"""Playback endpoints (Specification §11.5, API §11): the preferred playback
target (`/playback`) and a Range-capable streaming proxy (`/stream`) used by
the embedded-player strategy. Both playback strategies — backend stream and
direct link/path — work the same way for `local` and `smb` sources, since
every file access goes through `app.sources.SourceAccess`.
"""

from __future__ import annotations

import mimetypes
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from app.db import get_engine
from app.playback_settings import get_settings as get_playback_settings
from app.sources import get_source_access

router = APIRouter()

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def _file_not_found_error(file_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "file_not_found", "message": f"File not found: {file_id}"}},
    )


def _lookup_file_and_source(conn, file_id: str):
    return conn.execute(
        text(
            """
            SELECT f.relative_path, f.file_name, s.*
            FROM files f
            JOIN sources s ON s.id = f.source_id
            WHERE f.id = :id AND s.is_active = 1
            """
        ),
        {"id": file_id},
    ).fetchone()


def _parse_range(range_header: str | None, size: int) -> tuple[int, int, bool]:
    """Returns `(start, end, is_partial)`; `end` is inclusive."""
    if not range_header:
        return 0, size - 1, False
    match = _RANGE_RE.match(range_header)
    if not match:
        return 0, size - 1, False

    start_s, end_s = match.groups()
    if start_s == "":
        if end_s == "":
            return 0, size - 1, False
        suffix_len = int(end_s)
        return max(0, size - suffix_len), size - 1, True

    start = int(start_s)
    end = min(int(end_s), size - 1) if end_s else size - 1
    return start, end, True


@router.get("/files/{file_id}/playback")
def get_playback_info(file_id: str):
    engine = get_engine()
    with engine.connect() as conn:
        row = _lookup_file_and_source(conn, file_id)
    if row is None:
        raise _file_not_found_error(file_id)

    access = get_source_access(row)
    settings = get_playback_settings(engine)

    return {
        "mode": settings["mode"],
        "stream_url": f"/api/files/{file_id}/stream",
        "direct_path": access.direct_path(row.relative_path),
    }


@router.get("/files/{file_id}/stream")
def stream_file(file_id: str, request: Request):
    engine = get_engine()
    with engine.connect() as conn:
        row = _lookup_file_and_source(conn, file_id)
    if row is None:
        raise _file_not_found_error(file_id)

    access = get_source_access(row)
    if not access.exists(row.relative_path):
        raise _file_not_found_error(file_id)

    size = access.size_of(row.relative_path)
    media_type = mimetypes.guess_type(row.file_name)[0] or "application/octet-stream"
    start, end, is_partial = _parse_range(request.headers.get("range"), size)

    headers = {"Accept-Ranges": "bytes", "Content-Length": str(end - start + 1)}
    if is_partial:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"

    return StreamingResponse(
        access.open_range(row.relative_path, start, end),
        status_code=206 if is_partial else 200,
        media_type=media_type,
        headers=headers,
    )
