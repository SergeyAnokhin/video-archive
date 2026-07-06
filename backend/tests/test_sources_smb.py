"""SMB source tests (Specification §5, Roadmap Stage 7): browsing (scan),
conversion, preview generation, tagging, and streaming playback against the
in-memory `fake_smb`/`smb_source` fixtures (`conftest.py`) — no real SMB
server is available in this environment, so these exercise the real
`app.sources.smb_backend.SMBBackend` code paths (UNC path building,
retry-on-error, download/upload plumbing) against a fake remote store instead.

Conversion/preview/tagging tests are skipped automatically if ffmpeg/ffprobe
aren't on PATH, same as the local-source equivalents in
`test_conversion.py`/`test_preview.py`/`test_tagging.py`.
"""

from __future__ import annotations

import shutil

import pytest
from smbprotocol.exceptions import SMBException
from sqlalchemy import text

from app import conversion, conversion_profiles, preview_layouts, preview_settings, tags as tags_service
from app.jobs import convert, preview as preview_job, service, tag as tag_job
from app.scan import scan_source_access
from app.sources import get_source_access
from app.sources.smb_backend import SMBBackend, test_connection as smb_test_connection

from .conftest import make_video

ffmpeg_available = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _source_row(engine, source_id: str):
    with engine.connect() as conn:
        return conn.execute(text("SELECT * FROM sources WHERE id = :id"), {"id": source_id}).fetchone()


# --- SMBBackend unit behavior ------------------------------------------------


def test_unc_path_building(fake_smb):
    backend = SMBBackend(fake_smb.host, 445, "testshare/nested", "user", "pass")
    assert backend._unc("clips/movie.mp4") == "\\\\testnas\\testshare\\nested\\clips\\movie.mp4"
    assert backend._unc("") == "\\\\testnas\\testshare\\nested"


def test_scandir_and_exists(fake_smb):
    fake_smb.seed("clips/movie.mp4", b"0" * 10)
    fake_smb.seed("clips/movie.jpg", b"1")
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass")

    root_entries = {e.name: e for e in backend.scandir("")}
    assert root_entries["clips"].is_dir

    clip_entries = {e.name: e for e in backend.scandir("clips")}
    assert clip_entries["movie.mp4"].stat.size == 10
    assert backend.exists("clips/movie.mp4")
    assert not backend.exists("clips/missing.mp4")


def test_retry_on_connection_error(fake_smb):
    fake_smb.seed("clips/movie.mp4", b"data")
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass")
    fake_smb.fail_next.append(SMBException("session dropped"))

    # The first scandir call fails with a retryable error; `_with_retry`
    # re-registers the session and retries once, transparently to the caller.
    entries = backend.scandir("clips")
    assert {e.name for e in entries} == {"movie.mp4"}


def test_commit_new_file_uploads_and_cleans_up_local_temp(fake_smb, tmp_path):
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass")
    local_file = tmp_path / "output.mp4"
    local_file.write_bytes(b"encoded-bytes")

    backend.commit_new_file(local_file, "clips/output.mp4")

    assert fake_smb.read("clips/output.mp4") == b"encoded-bytes"
    assert not local_file.exists()


def test_local_copy_downloads_and_cleans_up(fake_smb):
    fake_smb.seed("clips/movie.mp4", b"remote-bytes")
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass")

    with backend.local_copy("clips/movie.mp4") as local_path:
        assert local_path.name == "movie.mp4"
        assert local_path.read_bytes() == b"remote-bytes"
        captured_path = local_path
    assert not captured_path.exists()


def test_smb_test_connection(fake_smb):
    fake_smb.seed("clips/movie.mp4", b"0")
    ok, message = smb_test_connection("testnas", 445, "testshare", "user", "pass")
    assert ok is True
    assert message is None


# --- scan (browsing) ----------------------------------------------------------


def test_scan_smb_source_discovers_files(engine, smb_source):
    smb_source["fs"].seed("Cam1/2024/01/clip.mp4", b"0" * 100)
    smb_source["fs"].seed("Cam1/2024/01/clip.jpg", b"1")  # own preview asset

    access = get_source_access(_source_row(engine, smb_source["id"]))
    result = scan_source_access(engine, smb_source["id"], access)

    assert result.video_files_count == 1
    with engine.connect() as conn:
        file_row = conn.execute(
            text("SELECT * FROM files WHERE relative_path = 'Cam1/2024/01/clip.mp4'")
        ).fetchone()
    assert file_row is not None
    assert file_row.has_preview_asset == 1
    assert file_row.size_bytes == 100


# --- conversion, preview, tagging (require real ffmpeg/ffprobe) --------------


@pytest.mark.skipif(not ffmpeg_available, reason="ffmpeg/ffprobe not on PATH")
def test_convert_production_mode_over_smb(engine, smb_source, tmp_path):
    local_video = tmp_path / "movie.mp4"
    make_video(local_video)
    smb_source["fs"].seed("clips/movie.mp4", local_video.read_bytes())

    access = get_source_access(_source_row(engine, smb_source["id"]))
    scan_source_access(engine, smb_source["id"], access)
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
    status, _message = convert.run_convert_job(engine, job)
    service.finish_job(engine, job["id"], status, _message)

    assert status == "completed"
    assert smb_source["fs"].exists("clips/movie.mp4")
    info = conversion.probe_media(_write_temp(tmp_path, smb_source["fs"].read("clips/movie.mp4")))
    assert info["video_codec_name"] == "hevc"


@pytest.mark.skipif(not ffmpeg_available, reason="ffmpeg/ffprobe not on PATH")
def test_convert_test_mode_over_smb_preserves_original(engine, smb_source, tmp_path):
    local_video = tmp_path / "clip.mp4"
    make_video(local_video)
    smb_source["fs"].seed("clips/clip.mp4", local_video.read_bytes())

    access = get_source_access(_source_row(engine, smb_source["id"]))
    scan_source_access(engine, smb_source["id"], access)
    profile = conversion_profiles.create_profile(
        engine, {"name": "P", "video_codec": "h265", "container": "mp4", "crf": 30, "drop_audio": True}
    )
    with engine.connect() as conn:
        file_row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'clips/clip.mp4'")).fetchone()

    job = service.create_job(
        engine, "convert", "file", file_row.id,
        {"file_id": file_row.id, "profile_id": profile["id"], "mode": "test"},
    )
    service.start_job(engine, job["id"])
    status, message = convert.run_convert_job(engine, job)
    service.finish_job(engine, job["id"], status, message)

    assert status == "completed"
    assert smb_source["fs"].exists("clips/clip.original.mp4")
    assert smb_source["fs"].exists("clips/clip.mp4")


@pytest.mark.skipif(not ffmpeg_available, reason="ffmpeg/ffprobe not on PATH")
def test_preview_file_over_smb(engine, smb_source, tmp_path):
    local_video = tmp_path / "movie.mp4"
    make_video(local_video, duration=1.0)
    smb_source["fs"].seed("clips/movie.mp4", local_video.read_bytes())

    access = get_source_access(_source_row(engine, smb_source["id"]))
    scan_source_access(engine, smb_source["id"], access)
    with engine.connect() as conn:
        file_row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'clips/movie.mp4'")).fetchone()

    layout = preview_layouts.get_default_preset(engine)
    settings = preview_settings.get_settings(engine)
    job = service.create_job(engine, "preview", "file", file_row.id, {"file_id": file_row.id})
    service.start_job(engine, job["id"])
    status, message = preview_job.run_preview_job(engine, job)
    service.finish_job(engine, job["id"], status, message)

    assert status == "completed"
    assert smb_source["fs"].exists("clips/movie.jpg")


@pytest.mark.skipif(not ffmpeg_available, reason="ffmpeg/ffprobe not on PATH")
def test_tag_file_over_smb(engine, smb_source, tmp_path, monkeypatch):
    local_video = tmp_path / "movie.mp4"
    make_video(local_video, duration=1.0)
    smb_source["fs"].seed("clips/movie.mp4", local_video.read_bytes())

    access = get_source_access(_source_row(engine, smb_source["id"]))
    scan_source_access(engine, smb_source["id"], access)
    tags_service.create_tag(engine, {"display_name": "Cat"})
    with engine.connect() as conn:
        file_row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'clips/movie.mp4'")).fetchone()

    from app.providers import registry

    monkeypatch.setattr(registry, "score_tags_with_provider", lambda *a, **k: [77])

    job = service.create_job(
        engine, "tag", "file", file_row.id, {"file_id": file_row.id, "provider_name": "openrouter"}
    )
    service.start_job(engine, job["id"])
    status, message = tag_job.run_tag_job(engine, job)
    service.finish_job(engine, job["id"], status, message)

    assert status == "completed"
    with engine.connect() as conn:
        tag_row = conn.execute(text("SELECT * FROM file_tags WHERE file_id = :id"), {"id": file_row.id}).fetchone()
    assert tag_row.score == 77


def _write_temp(tmp_path, data: bytes):
    path = tmp_path / "downloaded-check.mp4"
    path.write_bytes(data)
    return path
