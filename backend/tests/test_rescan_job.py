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
