"""Playback endpoint tests (Specification §11.5, API §11, Roadmap Stage 7):
`/api/files/{id}/playback` (mode + stream URL + direct path) and
`/api/files/{id}/stream` (HTTP Range support), for both a `local` source and
an `smb` source (via the `fake_smb` fixture — no real SMB server is available
in this environment).

`StreamingResponse` wraps a sync generator in an async-only iterator, so
`response.body_iterator` isn't consumable in a sync test without a
`pytest-asyncio`-style event loop (not a project dependency); byte-level
correctness is verified directly against `_parse_range()`/`access.open_range()`
instead of via the wrapped response body.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app import playback_settings
from app.routers.playback import _parse_range
from app.sources import get_source_access


def _insert_file(engine, source_id: str, relative_path: str, file_name: str) -> str:
    now = datetime.now(timezone.utc).isoformat()
    dir_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO directories (id, source_id, relative_path, name, parent_relative_path, "
                "has_folder_preview, last_scanned_at, created_at, updated_at) "
                "VALUES (:id, :sid, '', 'root', NULL, 0, :now, :now, :now)"
            ),
            {"id": dir_id, "sid": source_id, "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, created_at, updated_at) "
                "VALUES (:id, :sid, :did, :rel, :fname, 'mp4', 0, :now, :now, 1, :now, :now)"
            ),
            {"id": file_id, "sid": source_id, "did": dir_id, "rel": relative_path, "fname": file_name, "now": now},
        )
    return file_id


class _FakeRequest:
    def __init__(self, range_header: str | None):
        self.headers = {"range": range_header} if range_header else {}


def _source_row(engine, source_id: str):
    with engine.connect() as conn:
        return conn.execute(text("SELECT * FROM sources WHERE id = :id"), {"id": source_id}).fetchone()


def test_parse_range():
    assert _parse_range(None, 100) == (0, 99, False)
    assert _parse_range("bytes=10-20", 100) == (10, 20, True)
    assert _parse_range("bytes=10-", 100) == (10, 99, True)
    assert _parse_range("bytes=-20", 100) == (80, 99, True)


def test_playback_info_local(engine, source):
    video_path = source["root"] / "movie.mp4"
    video_path.write_bytes(b"0123456789")
    file_id = _insert_file(engine, source["id"], "movie.mp4", "movie.mp4")

    from app.routers.playback import get_playback_info

    info = get_playback_info(file_id)
    assert info["mode"] == "stream"
    assert info["stream_url"] == f"/api/files/{file_id}/stream"
    assert info["direct_path"] == str(video_path)


def test_local_stream_range_headers_and_bytes(engine, source):
    (source["root"] / "movie.mp4").write_bytes(b"0123456789")
    file_id = _insert_file(engine, source["id"], "movie.mp4", "movie.mp4")

    from app.routers.playback import stream_file

    response = stream_file(file_id, _FakeRequest("bytes=2-5"))
    assert response.status_code == 206
    assert response.headers["Content-Range"] == "bytes 2-5/10"

    access = get_source_access(_source_row(engine, source["id"]))
    body = b"".join(access.open_range("movie.mp4", 2, 5))
    assert body == b"2345"


def test_local_stream_without_range_returns_whole_file(engine, source):
    (source["root"] / "movie.mp4").write_bytes(b"0123456789")
    file_id = _insert_file(engine, source["id"], "movie.mp4", "movie.mp4")

    from app.routers.playback import stream_file

    response = stream_file(file_id, _FakeRequest(None))
    assert response.status_code == 200
    assert response.headers["Content-Length"] == "10"


def test_playback_settings_round_trip(engine):
    assert playback_settings.get_settings(engine)["mode"] == "stream"
    updated = playback_settings.update_settings(engine, {"mode": "direct_link"})
    assert updated["mode"] == "direct_link"
    assert playback_settings.get_settings(engine)["mode"] == "direct_link"


def test_playback_info_and_direct_path_over_smb(engine, smb_source):
    smb_source["fs"].seed("clips/movie.mp4", b"0123456789")
    file_id = _insert_file(engine, smb_source["id"], "clips/movie.mp4", "movie.mp4")

    from app.routers.playback import get_playback_info

    info = get_playback_info(file_id)
    assert info["direct_path"] == f"\\\\{smb_source['fs'].host}\\{smb_source['fs'].share}\\clips\\movie.mp4"


def test_stream_range_over_smb(engine, smb_source):
    smb_source["fs"].seed("clips/movie.mp4", b"abcdefghij")
    file_id = _insert_file(engine, smb_source["id"], "clips/movie.mp4", "movie.mp4")

    from app.routers.playback import stream_file

    response = stream_file(file_id, _FakeRequest("bytes=2-4"))
    assert response.status_code == 206
    assert response.headers["Content-Range"] == "bytes 2-4/10"

    access = get_source_access(_source_row(engine, smb_source["id"]))
    body = b"".join(access.open_range("clips/movie.mp4", 2, 4))
    assert body == b"cde"
