"""`run_rescan_job` tests: plain rescan stays filesystem-metadata-only, while
the `"rescan_with_media_info"` job type (user request) additionally probes
and caches technical metadata for video files, skipping any file whose cache
is already populated.

Runs real ffmpeg/ffprobe against a tiny synthetic video (skipped
automatically if ffmpeg/ffprobe aren't on PATH), same as test_conversion.py.
"""

from __future__ import annotations

import shutil

import pytest
from sqlalchemy import text

from app.jobs import service
from app.jobs.rescan import run_rescan_job

from .conftest import make_video

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not on PATH",
)


def _file_row(engine, source_id, relative_path):
    with engine.connect() as conn:
        return conn.execute(
            text(
                "SELECT id, width, height, video_codec, media_probed_at FROM files "
                "WHERE source_id = :sid AND relative_path = :rel"
            ),
            {"sid": source_id, "rel": relative_path},
        ).fetchone()


def test_plain_rescan_does_not_probe_media_info(engine, source):
    make_video(source["root"] / "clip.mp4", duration=1.0, size="160x120")
    job = service.create_job(engine, "rescan", "source", None, {"path": ""})

    status, _summary = run_rescan_job(engine, job)

    assert status == "completed"
    row = _file_row(engine, source["id"], "clip.mp4")
    assert row is not None
    assert row.media_probed_at is None


def test_rescan_with_media_info_probes_and_caches(engine, source):
    make_video(source["root"] / "clip.mp4", duration=1.0, size="160x120")
    job = service.create_job(engine, "rescan_with_media_info", "source", None, {"path": ""})

    status, summary = run_rescan_job(engine, job)

    assert status == "completed"
    assert "probed 1 file(s)" in summary
    row = _file_row(engine, source["id"], "clip.mp4")
    assert row.media_probed_at is not None
    assert row.width == 160
    assert row.height == 120
    assert row.video_codec is not None


def test_rescan_with_media_info_skips_already_probed_unchanged_file(engine, source, monkeypatch):
    make_video(source["root"] / "clip.mp4", duration=1.0, size="160x120")
    first_job = service.create_job(engine, "rescan_with_media_info", "source", None, {"path": ""})
    run_rescan_job(engine, first_job)

    from app import media_probe

    calls = []
    original = media_probe.probe_and_cache

    def _tracking_probe_and_cache(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    monkeypatch.setattr(media_probe, "probe_and_cache", _tracking_probe_and_cache)

    second_job = service.create_job(engine, "rescan_with_media_info", "source", None, {"path": ""})
    status, summary = run_rescan_job(engine, second_job)

    assert status == "completed"
    assert "probed 0 file(s)" in summary
    assert calls == []


def _insert_profile(engine, video_codec: str) -> str:
    import uuid
    from datetime import datetime, timezone

    profile_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(text("UPDATE conversion_profiles SET is_default = 0"))
        conn.execute(
            text(
                "INSERT INTO conversion_profiles (id, name, is_default, video_codec, container, "
                "max_dimension, crf, drop_audio, created_at, updated_at) "
                "VALUES (:id, 'Test profile', 1, :codec, 'mp4', 1024, 28, 0, :now, :now)"
            ),
            {"id": profile_id, "codec": video_codec, "now": now},
        )
    return profile_id


def _scan_then_inflate_db_size(engine, source) -> None:
    """Simulate a conversion whose own `files` update never landed: the DB
    still records the bigger pre-conversion size."""
    make_video(source["root"] / "sub" / "clip.mp4", duration=1.0, size="160x120")
    run_rescan_job(engine, service.create_job(engine, "rescan", "source", None, {"path": ""}))
    with engine.begin() as conn:
        conn.execute(text("UPDATE files SET size_bytes = size_bytes * 10"))


@pytest.mark.parametrize("job_type", ["rescan", "rescan_with_media_info"])
def test_rescan_marks_shrunk_file_converted_when_profile_matches(engine, source, job_type):
    _scan_then_inflate_db_size(engine, source)
    profile_id = _insert_profile(engine, "h264")  # make_video encodes h264

    status, summary = run_rescan_job(engine, service.create_job(engine, job_type, "source", None, {"path": ""}))

    assert status == "completed"
    assert "marked 1 file(s) converted" in summary
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT size_bytes, converted_at, last_conversion_profile_id, video_codec FROM files")
        ).fetchone()
    assert row.size_bytes == (source["root"] / "sub" / "clip.mp4").stat().st_size
    assert row.converted_at is not None
    assert row.last_conversion_profile_id == profile_id
    assert row.video_codec == "h264"


def test_rescan_does_not_mark_converted_without_matching_profile(engine, source):
    _scan_then_inflate_db_size(engine, source)
    _insert_profile(engine, "h265")

    status, summary = run_rescan_job(engine, service.create_job(engine, "rescan", "source", None, {"path": ""}))

    assert status == "completed"
    assert "converted" not in summary
    with engine.connect() as conn:
        assert conn.execute(text("SELECT converted_at FROM files")).scalar() is None


def test_rescan_does_not_mark_unchanged_file_converted(engine, source):
    make_video(source["root"] / "clip.mp4", duration=1.0, size="160x120")
    _insert_profile(engine, "h264")
    run_rescan_job(engine, service.create_job(engine, "rescan", "source", None, {"path": ""}))

    run_rescan_job(engine, service.create_job(engine, "rescan_with_media_info", "source", None, {"path": ""}))

    with engine.connect() as conn:
        assert conn.execute(text("SELECT converted_at FROM files")).scalar() is None
