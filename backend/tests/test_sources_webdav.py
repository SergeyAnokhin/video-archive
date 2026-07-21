"""WebDAV source tests: browsing (scan), conversion, preview generation,
tagging, and folder operations against the in-memory `fake_webdav`/
`webdav_source` fixtures (`conftest.py`) — no real WebDAV server is available
in this environment, so these exercise the real
`app.sources.webdav_backend.WebDAVBackend` code paths (URL building, PROPFIND
XML building/parsing, Range-header handling) against a fake remote store
instead, mirroring `test_sources_smb.py`.

Conversion/preview/tagging tests are skipped automatically if ffmpeg/ffprobe
aren't on PATH, same as the local/SMB-source equivalents.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from sqlalchemy import text

from app import (
    conversion,
    conversion_profiles,
    conversion_settings,
    directory_ops,
    preview_layouts,
    preview_settings,
    tags as tags_service,
)
from app.jobs import convert, preview as preview_job, service, tag as tag_job
from app.media import preview_gif_relative_path
from app.scan import scan_source_access
from app.sources import get_source_access
from app.sources.webdav_backend import WebDAVBackend, test_connection as webdav_test_connection

from .conftest import make_video

ffmpeg_available = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _source_row(engine, source_id: str):
    with engine.connect() as conn:
        return conn.execute(text("SELECT * FROM sources WHERE id = :id"), {"id": source_id}).fetchone()


def _backend(fake_webdav) -> WebDAVBackend:
    return WebDAVBackend(fake_webdav.base_url, None, "", "user", "pass")


# --- WebDAVBackend unit behavior ---------------------------------------------


def test_url_building(fake_webdav):
    backend = WebDAVBackend("nas.local", 5006, "videos/nested", "user", "pass")
    assert backend._url("clips/movie.mp4") == "https://nas.local:5006/videos/nested/clips/movie.mp4"
    assert backend._url("") == "https://nas.local:5006/videos/nested"


def test_url_building_defaults_to_https_when_host_has_no_scheme():
    backend = WebDAVBackend("nas.local", None, "", None, None)
    assert backend._url("a.mp4") == "https://nas.local/a.mp4"


def test_url_building_respects_explicit_scheme_in_host():
    backend = WebDAVBackend("http://nas.local", 5005, "", None, None)
    assert backend._url("a.mp4") == "http://nas.local:5005/a.mp4"


def test_scandir_and_exists(fake_webdav):
    fake_webdav.seed("clips/movie.mp4", b"0" * 10)
    fake_webdav.seed("clips/movie.jpg", b"1")
    backend = _backend(fake_webdav)

    root_entries = {e.name: e for e in backend.scandir("")}
    assert root_entries["clips"].is_dir

    clip_entries = {e.name: e for e in backend.scandir("clips")}
    assert clip_entries["movie.mp4"].stat.size == 10
    assert backend.exists("clips/movie.mp4")
    assert not backend.exists("clips/missing.mp4")


def test_stat_rel_and_size_of(fake_webdav):
    fake_webdav.seed("clips/movie.mp4", b"x" * 25)
    backend = _backend(fake_webdav)

    assert backend.stat_rel("clips/movie.mp4").size == 25
    assert backend.size_of("clips/movie.mp4") == 25


def test_is_dir(fake_webdav):
    fake_webdav.seed("clips/movie.mp4", b"0")
    backend = _backend(fake_webdav)

    assert backend.is_dir("")
    assert backend.is_dir("clips")
    assert not backend.is_dir("clips/movie.mp4")


def test_remote_mkdir_and_rmdir(fake_webdav):
    backend = _backend(fake_webdav)

    backend.remote_mkdir("clips")
    assert backend.exists("clips")

    backend.remote_rmdir("clips")
    assert not backend.exists("clips")


def test_remote_rmdir_refuses_non_empty_directory(fake_webdav):
    # Unlike a plain WebDAV `DELETE` (which is typically recursive), this
    # backend must match `os.rmdir`/`smbclient.rmdir`'s strict "must be
    # empty" semantics -- otherwise a caller expecting a safe no-op-if-empty
    # check could silently wipe out a non-empty directory.
    fake_webdav.seed("clips/movie.mp4", b"0")
    backend = _backend(fake_webdav)

    with pytest.raises(OSError):
        backend.remote_rmdir("clips")
    assert fake_webdav.exists("clips/movie.mp4")


def test_commit_new_file_uploads_and_cleans_up_local_temp(fake_webdav, tmp_path):
    backend = _backend(fake_webdav)
    local_file = tmp_path / "output.mp4"
    local_file.write_bytes(b"encoded-bytes")

    backend.commit_new_file(local_file, "clips/output.mp4")

    assert fake_webdav.read("clips/output.mp4") == b"encoded-bytes"
    assert not local_file.exists()


def test_commit_new_file_creates_missing_parent_directories(fake_webdav, tmp_path):
    backend = _backend(fake_webdav)
    local_file = tmp_path / "backup.zip"
    local_file.write_bytes(b"zip-bytes")

    backend.commit_new_file(local_file, ".video-archive/backups/backup.zip")

    assert fake_webdav.read(".video-archive/backups/backup.zip") == b"zip-bytes"


def test_local_copy_downloads_and_cleans_up(fake_webdav):
    fake_webdav.seed("clips/movie.mp4", b"remote-bytes")
    backend = _backend(fake_webdav)

    with backend.local_copy("clips/movie.mp4") as local_path:
        assert local_path.name == "movie.mp4"
        assert local_path.read_bytes() == b"remote-bytes"
        captured_path = local_path
    assert not captured_path.exists()


def test_local_copy_fires_on_copy_start(fake_webdav):
    fake_webdav.seed("clips/movie.mp4", b"remote-bytes")
    backend = _backend(fake_webdav)
    calls = []

    with backend.local_copy("clips/movie.mp4", on_copy_start=lambda: calls.append(1)):
        pass
    assert calls == [1]


def test_open_range_partial_read(fake_webdav):
    fake_webdav.seed("clips/movie.mp4", b"0123456789")
    backend = _backend(fake_webdav)

    chunk = b"".join(backend.open_range("clips/movie.mp4", start=2, end=5))
    assert chunk == b"2345"


def test_read_bytes(fake_webdav):
    fake_webdav.seed("clips/movie.mp4", b"full-content")
    backend = _backend(fake_webdav)

    assert backend.read_bytes("clips/movie.mp4") == b"full-content"


def test_remote_rename(fake_webdav):
    fake_webdav.seed("clips/movie.mp4", b"data")
    backend = _backend(fake_webdav)

    backend.remote_rename("clips/movie.mp4", "clips/movie.original.mp4")

    assert not fake_webdav.exists("clips/movie.mp4")
    assert fake_webdav.read("clips/movie.original.mp4") == b"data"


def test_remote_remove(fake_webdav):
    fake_webdav.seed("clips/movie.mp4", b"data")
    backend = _backend(fake_webdav)

    backend.remote_remove("clips/movie.mp4")

    assert not fake_webdav.exists("clips/movie.mp4")


def test_direct_access_status_is_always_none(fake_webdav):
    assert _backend(fake_webdav).direct_access_status() is None


def test_webdav_test_connection(fake_webdav):
    fake_webdav.seed("clips/movie.mp4", b"0")
    ok, message = webdav_test_connection(fake_webdav.base_url, None, "", "user", "pass")
    assert ok is True
    assert message is None


def test_webdav_test_connection_reports_failure(fake_webdav):
    fake_webdav.fail_next.append(ConnectionError("nas unreachable"))
    ok, message = webdav_test_connection(fake_webdav.base_url, None, "", "user", "pass")
    assert ok is False
    assert message


# --- scan (browsing) ----------------------------------------------------------


def test_scan_webdav_source_discovers_files(engine, webdav_source):
    webdav_source["fs"].seed("Cam1/2024/01/clip.mp4", b"0" * 100)
    webdav_source["fs"].seed("Cam1/2024/01/clip.jpg", b"1")  # own preview asset

    access = get_source_access(_source_row(engine, webdav_source["id"]))
    result = scan_source_access(engine, webdav_source["id"], access)

    assert result.video_files_count == 1
    with engine.connect() as conn:
        file_row = conn.execute(
            text("SELECT * FROM files WHERE relative_path = 'Cam1/2024/01/clip.mp4'")
        ).fetchone()
    assert file_row is not None
    assert file_row.has_preview_asset == 1
    assert file_row.size_bytes == 100


# --- folder create/delete (user request, app/directory_ops.py) --------------


def test_create_and_delete_directory_over_webdav(engine, webdav_source):
    row = directory_ops.create_directory(engine, "", "NewFolder")
    assert row.relative_path == "NewFolder"
    assert webdav_source["fs"].exists("NewFolder")

    directory_ops.delete_directory(engine, "NewFolder")
    assert not webdav_source["fs"].exists("NewFolder")

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM directories WHERE source_id = :sid AND relative_path = 'NewFolder'"),
            {"sid": webdav_source["id"]},
        ).fetchone()
    assert row is None


# --- conversion, preview, tagging (require real ffmpeg/ffprobe) --------------


@pytest.mark.skipif(not ffmpeg_available, reason="ffmpeg/ffprobe not on PATH")
def test_convert_production_mode_over_webdav(engine, webdav_source, tmp_path):
    local_video = tmp_path / "movie.mp4"
    make_video(local_video, size="480x360", duration=1.0)
    conversion_settings.update_settings(engine, {"min_size_reduction_percent": 0})
    webdav_source["fs"].seed("clips/movie.mp4", local_video.read_bytes())

    access = get_source_access(_source_row(engine, webdav_source["id"]))
    scan_source_access(engine, webdav_source["id"], access)
    profile = conversion_profiles.create_profile(
        engine, {"name": "P", "video_codec": "h265", "container": "mp4", "crf": 30, "drop_audio": True}
    )
    with engine.connect() as conn:
        file_row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'clips/movie.mp4'")).fetchone()

    job = service.create_job(
        engine, "convert", "file", file_row.id,
        {"file_id": file_row.id, "profile_id": profile["id"], "mode": "production"},
    )
    service.start_job(engine, job["id"])
    status, message = convert.run_convert_job(engine, job)
    service.finish_job(engine, job["id"], status, message)

    assert status == "completed"
    assert webdav_source["fs"].exists("clips/movie.mp4")
    info = conversion.probe_media(_write_temp(tmp_path, webdav_source["fs"].read("clips/movie.mp4")))
    assert info["video_codec_name"] == "hevc"


@pytest.mark.skipif(not ffmpeg_available, reason="ffmpeg/ffprobe not on PATH")
def test_preview_file_over_webdav(engine, webdav_source, tmp_path):
    local_video = tmp_path / "movie.mp4"
    make_video(local_video, duration=1.0)
    webdav_source["fs"].seed("clips/movie.mp4", local_video.read_bytes())

    access = get_source_access(_source_row(engine, webdav_source["id"]))
    scan_source_access(engine, webdav_source["id"], access)
    with engine.connect() as conn:
        file_row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'clips/movie.mp4'")).fetchone()

    preview_layouts.get_default_preset(engine)
    preview_settings.get_settings(engine)
    job = service.create_job(engine, "preview", "file", file_row.id, {"file_id": file_row.id})
    service.start_job(engine, job["id"])
    status, message = preview_job.run_preview_job(engine, job)
    service.finish_job(engine, job["id"], status, message)

    assert status == "completed"
    assert webdav_source["fs"].exists("clips/movie.jpg")
    assert webdav_source["fs"].exists(preview_gif_relative_path("clips/movie.mp4"))


@pytest.mark.skipif(not ffmpeg_available, reason="ffmpeg/ffprobe not on PATH")
def test_tag_file_over_webdav(engine, webdav_source, tmp_path, monkeypatch):
    local_video = tmp_path / "movie.mp4"
    make_video(local_video, duration=1.0)
    webdav_source["fs"].seed("clips/movie.mp4", local_video.read_bytes())

    access = get_source_access(_source_row(engine, webdav_source["id"]))
    scan_source_access(engine, webdav_source["id"], access)
    tags_service.create_tag(engine, {"display_name": "Cat"})
    with engine.connect() as conn:
        file_row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'clips/movie.mp4'")).fetchone()

    from app import provider_entries
    from app.providers import registry

    provider_entries.create_entry(engine, {"provider_type": "openrouter", "enabled": True, "api_key": "sk-test"})
    monkeypatch.setattr(
        registry, "score_tags_with_fallback", lambda engine, entries, images, tags, dead, **_kwargs: ([77], entries[0])
    )

    job = service.create_job(engine, "tag", "file", file_row.id, {"file_id": file_row.id})
    service.start_job(engine, job["id"])
    status, message = tag_job.run_tag_job(engine, job)
    service.finish_job(engine, job["id"], status, message)

    assert status == "completed"
    with engine.connect() as conn:
        tag_row = conn.execute(text("SELECT * FROM file_tags WHERE file_id = :id"), {"id": file_row.id}).fetchone()
    assert tag_row.score == 77


def _write_temp(tmp_path, data: bytes) -> Path:
    path = tmp_path / "downloaded-check.mp4"
    path.write_bytes(data)
    return path
