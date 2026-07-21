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
import threading
from pathlib import Path

import pytest
from smbprotocol.exceptions import SMBException
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
from app.sources import get_source_access, smb_backend, smb_stats
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


def test_remote_mkdir_and_rmdir(fake_smb):
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass")

    backend.remote_mkdir("clips")
    assert backend.exists("clips")

    backend.remote_rmdir("clips")
    assert not backend.exists("clips")


def test_commit_new_file_uploads_and_cleans_up_local_temp(fake_smb, tmp_path):
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass")
    local_file = tmp_path / "output.mp4"
    local_file.write_bytes(b"encoded-bytes")

    backend.commit_new_file(local_file, "clips/output.mp4")

    assert fake_smb.read("clips/output.mp4") == b"encoded-bytes"
    assert not local_file.exists()


def test_commit_new_file_creates_missing_parent_directories(fake_smb, tmp_path):
    # Regression: unlike a same-volume local move, `smbclient.open_file()`
    # does not create missing parent directories on the share -- writing the
    # very first backup into `.video-archive/backups/` (neither ancestor
    # directory pre-exists) used to fail with NtStatus 0xc000003a.
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass")
    local_file = tmp_path / "backup.zip"
    local_file.write_bytes(b"zip-bytes")

    backend.commit_new_file(local_file, ".video-archive/backups/backup.zip")

    assert fake_smb.read(".video-archive/backups/backup.zip") == b"zip-bytes"


def test_local_copy_downloads_and_cleans_up(fake_smb):
    fake_smb.seed("clips/movie.mp4", b"remote-bytes")
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass")

    with backend.local_copy("clips/movie.mp4") as local_path:
        assert local_path.name == "movie.mp4"
        assert local_path.read_bytes() == b"remote-bytes"
        captured_path = local_path
    assert not captured_path.exists()


def test_local_copy_ignores_direct_access_when_disabled(fake_smb, monkeypatch):
    # Regression: `direct_access_enabled` defaults to False, so today's
    # download-based behavior must stay byte-for-byte unchanged even if the
    # OS-level UNC path would in principle be usable.
    fake_smb.seed("clips/movie.mp4", b"remote-bytes")
    monkeypatch.setattr(smb_backend.windows_unc, "available", lambda *a, **k: True)
    monkeypatch.setattr(smb_backend, "_unc_readable", lambda p: True)
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass", direct_access_enabled=False)

    with backend.local_copy("clips/movie.mp4") as local_path:
        # A real local temp file, not the UNC path -- proves the download
        # path ran rather than the direct-access one.
        assert local_path.exists()
        assert local_path.read_bytes() == b"remote-bytes"


def test_local_copy_uses_unc_path_when_direct_access_available(fake_smb, monkeypatch):
    fake_smb.seed("clips/movie.mp4", b"remote-bytes")
    monkeypatch.setattr(smb_backend.windows_unc, "available", lambda *a, **k: True)
    monkeypatch.setattr(smb_backend, "_unc_readable", lambda p: True)
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass", direct_access_enabled=True)

    with backend.local_copy("clips/movie.mp4") as path:
        assert str(path) == backend._unc("clips/movie.mp4")


def test_local_copy_falls_back_when_unc_path_not_actually_readable(fake_smb, monkeypatch):
    # `windows_unc.available()` says yes (OS has a session to the host) but
    # the specific path can't actually be opened right now -- must fall back
    # to the download path instead of yielding a dead path to the caller,
    # and must report the failure so the next check re-probes.
    fake_smb.seed("clips/movie.mp4", b"remote-bytes")
    monkeypatch.setattr(smb_backend.windows_unc, "available", lambda *a, **k: True)
    monkeypatch.setattr(smb_backend, "_unc_readable", lambda p: False)
    reported = []
    monkeypatch.setattr(smb_backend.windows_unc, "report_failure", lambda host, user: reported.append((host, user)))
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass", direct_access_enabled=True)

    with backend.local_copy("clips/movie.mp4") as local_path:
        assert local_path.exists()
        assert local_path.read_bytes() == b"remote-bytes"
    assert reported == [("testnas", "user")]


def test_local_copy_falls_back_when_direct_access_unavailable(fake_smb, monkeypatch):
    fake_smb.seed("clips/movie.mp4", b"remote-bytes")
    monkeypatch.setattr(smb_backend.windows_unc, "available", lambda *a, **k: False)
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass", direct_access_enabled=True)

    with backend.local_copy("clips/movie.mp4") as local_path:
        assert local_path.exists()
        assert local_path.read_bytes() == b"remote-bytes"


def test_local_copy_fires_on_copy_start_only_on_download_branch(fake_smb):
    # `on_copy_start` (user request: log "copying locally" for a slow SMB
    # download) must fire exactly once for the download path -- callers rely
    # on "did it fire at all" to decide whether to log a copy duration.
    fake_smb.seed("clips/movie.mp4", b"remote-bytes")
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass")
    calls = []

    with backend.local_copy("clips/movie.mp4", on_copy_start=lambda: calls.append(1)):
        pass
    assert calls == [1]


def test_local_copy_does_not_fire_on_copy_start_on_unc_fast_path(fake_smb, monkeypatch):
    fake_smb.seed("clips/movie.mp4", b"remote-bytes")
    monkeypatch.setattr(smb_backend.windows_unc, "available", lambda *a, **k: True)
    monkeypatch.setattr(smb_backend, "_unc_readable", lambda p: True)
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass", direct_access_enabled=True)
    calls = []

    with backend.local_copy("clips/movie.mp4", on_copy_start=lambda: calls.append(1)):
        pass
    assert calls == []


def test_read_bytes_and_open_range_add_to_smb_stats_counter(fake_smb):
    fake_smb.seed("clips/movie.mp4", b"x" * 40)
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass")

    before = smb_stats.get_total_bytes_transferred()
    backend.read_bytes("clips/movie.mp4")
    assert smb_stats.get_total_bytes_transferred() == before + 40

    before = smb_stats.get_total_bytes_transferred()
    total_from_range = sum(len(chunk) for chunk in backend.open_range("clips/movie.mp4", start=10, end=29))
    assert smb_stats.get_total_bytes_transferred() == before + total_from_range


def test_local_copy_and_commit_new_file_add_to_smb_stats_counter(fake_smb, tmp_path):
    # Regression: these two used a raw `shutil.copyfileobj()` that bypassed
    # `smb_stats` entirely -- a whole conversion job's download-then-upload
    # round trip (its only network activity) was invisible to the frontend's
    # network gauge as a result (chat request 2026-07-19 follow-up, caught by
    # comparing against a real Kubernetes deployment during an active job).
    fake_smb.seed("clips/movie.mp4", b"r" * 40)
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass")

    before = smb_stats.get_total_bytes_transferred()
    with backend.local_copy("clips/movie.mp4"):
        pass
    assert smb_stats.get_total_bytes_transferred() == before + 40

    local_file = tmp_path / "output.mp4"
    local_file.write_bytes(b"u" * 25)
    before = smb_stats.get_total_bytes_transferred()
    backend.commit_new_file(local_file, "clips/output.mp4")
    assert smb_stats.get_total_bytes_transferred() == before + 25


# --- process-wide `_smb_lock` status/force-release (Settings UI) ------------


def test_get_lock_status_reports_idle_when_not_held():
    assert smb_backend.get_lock_status() == {
        "held": False,
        "held_since": None,
        "seconds_held": None,
        "description": None,
    }


def test_get_lock_status_reports_held_while_locked():
    with smb_backend._locked("test operation"):
        status = smb_backend.get_lock_status()
        assert status["held"] is True
        assert status["description"] == "test operation"
        assert status["seconds_held"] >= 0
        assert status["held_since"] is not None
    assert smb_backend.get_lock_status()["held"] is False


def test_force_release_lock_unblocks_new_callers_even_if_old_holder_never_returns():
    """Regression test for the escape hatch the Settings UI's "release lock"
    button uses: a caller stuck holding `_smb_lock` forever (the real-world
    symptom is a hung SMB read) must not be able to block a brand-new caller
    once `force_release_lock()` has been called."""
    still_locked = threading.Event()
    release_stuck_caller = threading.Event()

    def _stuck_caller():
        with smb_backend._locked("stuck operation"):
            still_locked.set()
            release_stuck_caller.wait(timeout=5)

    stuck_thread = threading.Thread(target=_stuck_caller, daemon=True)
    stuck_thread.start()
    try:
        assert still_locked.wait(timeout=5)
        assert smb_backend.get_lock_status()["held"] is True

        smb_backend.force_release_lock()
        assert smb_backend.get_lock_status()["held"] is False

        new_caller_acquired = threading.Event()

        def _new_caller():
            with smb_backend._locked("new operation"):
                new_caller_acquired.set()

        new_thread = threading.Thread(target=_new_caller, daemon=True)
        new_thread.start()
        assert new_caller_acquired.wait(timeout=2)
        new_thread.join(timeout=5)
    finally:
        release_stuck_caller.set()
        stuck_thread.join(timeout=5)


# --- write-side direct-access fast path (commit/rename/remove) --------------


def test_commit_new_file_uses_raw_replace_when_allow_direct_and_available(fake_smb, monkeypatch, tmp_path):
    monkeypatch.setattr(smb_backend.windows_unc, "available", lambda *a, **k: True)
    calls = []
    monkeypatch.setattr(smb_backend.os, "replace", lambda src, dst: calls.append((src, dst)))
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass", direct_access_enabled=True)
    local_file = tmp_path / "output.mp4"
    local_file.write_bytes(b"encoded-bytes")

    backend.commit_new_file(local_file, "clips/output.mp4", allow_direct=True)

    assert calls == [(local_file, backend._unc("clips/output.mp4"))]
    # The raw rename "succeeded" (mocked), so the smbclient upload path never
    # ran -- the fake share was never touched.
    assert not fake_smb.exists("clips/output.mp4")


def test_commit_new_file_falls_back_to_upload_when_raw_replace_fails(fake_smb, monkeypatch, tmp_path):
    monkeypatch.setattr(smb_backend.windows_unc, "available", lambda *a, **k: True)
    monkeypatch.setattr(smb_backend.os, "replace", lambda src, dst: (_ for _ in ()).throw(OSError("cross-device")))
    reported = []
    monkeypatch.setattr(smb_backend.windows_unc, "report_failure", lambda host, user: reported.append((host, user)))
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass", direct_access_enabled=True)
    local_file = tmp_path / "output.mp4"
    local_file.write_bytes(b"encoded-bytes")

    backend.commit_new_file(local_file, "clips/output.mp4", allow_direct=True)

    assert fake_smb.read("clips/output.mp4") == b"encoded-bytes"
    assert not local_file.exists()
    assert reported == [("testnas", "user")]


def test_commit_new_file_ignores_allow_direct_when_direct_access_disabled(fake_smb, monkeypatch, tmp_path):
    # Per-source `direct_access_enabled` still gates the fast path even when
    # a caller passes `allow_direct=True` -- a source that never opted in to
    # direct access must keep uploading via smbclient regardless.
    monkeypatch.setattr(smb_backend.windows_unc, "available", lambda *a, **k: True)
    monkeypatch.setattr(smb_backend.os, "replace", lambda src, dst: pytest.fail("raw replace should not run"))
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass", direct_access_enabled=False)
    local_file = tmp_path / "output.mp4"
    local_file.write_bytes(b"encoded-bytes")

    backend.commit_new_file(local_file, "clips/output.mp4", allow_direct=True)

    assert fake_smb.read("clips/output.mp4") == b"encoded-bytes"


def test_remote_rename_uses_raw_replace_when_allow_direct_and_available(fake_smb, monkeypatch):
    monkeypatch.setattr(smb_backend.windows_unc, "available", lambda *a, **k: True)
    calls = []
    monkeypatch.setattr(smb_backend.os, "replace", lambda src, dst: calls.append((src, dst)))
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass", direct_access_enabled=True)
    fake_smb.seed("clips/movie.mp4", b"data")

    backend.remote_rename("clips/movie.mp4", "clips/movie.original.mp4", allow_direct=True)

    assert calls == [(backend._unc("clips/movie.mp4"), backend._unc("clips/movie.original.mp4"))]
    # smbclient.rename() never ran -- the fake share still has the old name.
    assert fake_smb.exists("clips/movie.mp4")
    assert not fake_smb.exists("clips/movie.original.mp4")


def test_remote_rename_falls_back_to_smbclient_when_raw_replace_fails(fake_smb, monkeypatch):
    monkeypatch.setattr(smb_backend.windows_unc, "available", lambda *a, **k: True)
    monkeypatch.setattr(smb_backend.os, "replace", lambda src, dst: (_ for _ in ()).throw(OSError("busy")))
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass", direct_access_enabled=True)
    fake_smb.seed("clips/movie.mp4", b"data")

    backend.remote_rename("clips/movie.mp4", "clips/movie.original.mp4", allow_direct=True)

    assert not fake_smb.exists("clips/movie.mp4")
    assert fake_smb.read("clips/movie.original.mp4") == b"data"


def test_remote_remove_uses_raw_remove_when_allow_direct_and_available(fake_smb, monkeypatch):
    monkeypatch.setattr(smb_backend.windows_unc, "available", lambda *a, **k: True)
    calls = []
    monkeypatch.setattr(smb_backend.os, "remove", lambda path: calls.append(path))
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass", direct_access_enabled=True)
    fake_smb.seed("clips/movie.mp4", b"data")

    backend.remote_remove("clips/movie.mp4", allow_direct=True)

    assert calls == [backend._unc("clips/movie.mp4")]
    # smbclient.remove() never ran -- the fake share still has the file.
    assert fake_smb.exists("clips/movie.mp4")


def test_remote_remove_falls_back_to_smbclient_when_raw_remove_fails(fake_smb, monkeypatch):
    monkeypatch.setattr(smb_backend.windows_unc, "available", lambda *a, **k: True)
    monkeypatch.setattr(smb_backend.os, "remove", lambda path: (_ for _ in ()).throw(OSError("busy")))
    backend = SMBBackend("testnas", 445, "testshare", "user", "pass", direct_access_enabled=True)
    fake_smb.seed("clips/movie.mp4", b"data")

    backend.remote_remove("clips/movie.mp4", allow_direct=True)

    assert not fake_smb.exists("clips/movie.mp4")


# --- _resolve_output_directory (app/jobs/convert.py) -------------------------


def test_resolve_output_directory_uses_share_dir_when_direct_write_enabled(fake_smb, engine, smb_source):
    access = get_source_access(_source_row(engine, smb_source["id"]))
    old_path = Path(access.direct_path("clips/movie.mp4"))
    assert str(old_path).startswith("\\\\")

    with convert._resolve_output_directory(access, old_path, True) as (directory, allow_direct):
        assert directory == old_path.parent
        assert allow_direct is True


def test_resolve_output_directory_uses_local_scratch_when_direct_write_disabled(fake_smb, engine, smb_source):
    # Regression: without this, a temp encode output would land straight on
    # the network share by accident whenever a direct-access source's read
    # happened to take the UNC fast path.
    access = get_source_access(_source_row(engine, smb_source["id"]))
    old_path = Path(access.direct_path("clips/movie.mp4"))

    with convert._resolve_output_directory(access, old_path, False) as (directory, allow_direct):
        assert directory != old_path.parent
        assert directory.exists()
        assert allow_direct is False
        captured = directory
    assert not captured.exists()


def test_resolve_output_directory_unaffected_for_non_unc_path(fake_smb, engine, smb_source, tmp_path):
    # A genuine local temp copy (the download-fallback case) is unaffected by
    # `direct_write_enabled` either way -- it already lives in its own
    # throwaway directory.
    access = get_source_access(_source_row(engine, smb_source["id"]))
    old_path = tmp_path / "downloaded.mp4"
    old_path.write_bytes(b"x")

    with convert._resolve_output_directory(access, old_path, True) as (directory, allow_direct):
        assert directory == old_path.parent
        assert allow_direct is False


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


# --- folder create/delete (user request, app/directory_ops.py) --------------


def test_create_and_delete_directory_over_smb(engine, smb_source):
    row = directory_ops.create_directory(engine, "", "NewFolder")
    assert row.relative_path == "NewFolder"
    assert smb_source["fs"].exists("NewFolder")

    directory_ops.delete_directory(engine, "NewFolder")
    assert not smb_source["fs"].exists("NewFolder")

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM directories WHERE source_id = :sid AND relative_path = 'NewFolder'"),
            {"sid": smb_source["id"]},
        ).fetchone()
    assert row is None


# --- conversion, preview, tagging (require real ffmpeg/ffprobe) --------------


@pytest.mark.skipif(not ffmpeg_available, reason="ffmpeg/ffprobe not on PATH")
def test_convert_production_mode_over_smb(engine, smb_source, tmp_path):
    local_video = tmp_path / "movie.mp4"
    # Bigger than the module default so the h265 re-encode actually shrinks
    # it -- a trivially tiny clip's re-encode can end up bigger than the
    # source from container/codec overhead alone, which the size-reduction
    # guard would (correctly) skip instead of replacing. The threshold is
    # also lowered below the modest real reduction such a small clip
    # achieves -- this test is about the SMB round-trip, not the guard.
    make_video(local_video, size="480x360", duration=1.0)
    conversion_settings.update_settings(engine, {"min_size_reduction_percent": 0})
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
    make_video(local_video, size="480x360", duration=1.0)
    conversion_settings.update_settings(engine, {"min_size_reduction_percent": 0})
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
    # The collage is uploaded back to the SMB source next to the video (user
    # request); the GIF is uploaded the same way into the source's own
    # technical folder (`app/media.py`).
    assert smb_source["fs"].exists("clips/movie.jpg")
    assert smb_source["fs"].exists(preview_gif_relative_path("clips/movie.mp4"))


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


def _write_temp(tmp_path, data: bytes):
    path = tmp_path / "downloaded-check.mp4"
    path.write_bytes(data)
    return path
