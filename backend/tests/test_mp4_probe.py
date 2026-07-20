"""Tests for `app.mp4_probe`: the header-only MP4/MOV fast path for the
media-info probe. Compares against `conversion.probe_media()` (real ffprobe)
on the same real, ffmpeg-encoded file, so these are skipped when ffmpeg isn't
on PATH, same convention as `test_conversion.py`. The malformed-input tests
need no ffmpeg and always run.
"""

from __future__ import annotations

import shutil

import pytest

from app import conversion, mp4_probe
from app.sources import SourceAccess
from app.sources.local_backend import LocalBackend

from .conftest import make_video

ffmpeg_available = shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


def _access(tmp_path):
    return SourceAccess(LocalBackend(tmp_path), "local")


@pytest.mark.skipif(not ffmpeg_available, reason="ffmpeg/ffprobe not on PATH")
def test_probe_media_matches_ffprobe_for_real_mp4(tmp_path):
    video_path = tmp_path / "clip.mp4"
    make_video(video_path, size="320x240", duration=1.0)
    size_bytes = video_path.stat().st_size

    expected = conversion.probe_media(video_path)
    access = _access(tmp_path)
    actual = mp4_probe.probe_media(access, "clip.mp4", size_bytes)

    assert actual is not None
    assert actual["width"] == expected["width"]
    assert actual["height"] == expected["height"]
    assert actual["video_codec_name"] == expected["video_codec_name"]
    assert actual["duration"] == pytest.approx(expected["duration"], rel=0.05)
    # Approximated from size/duration rather than read off a real bitrate
    # atom, so only a loose tolerance is expected to hold.
    assert actual["bit_rate"] == pytest.approx(expected["bit_rate"], rel=0.3)


@pytest.mark.skipif(not ffmpeg_available, reason="ffmpeg/ffprobe not on PATH")
def test_probe_media_returns_none_for_fragmented_mp4(tmp_path):
    import subprocess

    video_path = tmp_path / "frag.mp4"
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", "testsrc=duration=0.5:size=160x120:rate=5",
            "-pix_fmt", "yuv420p",
            "-movflags", "frag_keyframe+empty_moov",
            str(video_path),
        ],
        capture_output=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    access = _access(tmp_path)
    assert mp4_probe.probe_media(access, "frag.mp4", video_path.stat().st_size) is None


def test_probe_media_returns_none_for_garbage_bytes(tmp_path):
    path = tmp_path / "not-a-video.mp4"
    path.write_bytes(b"this is not an mp4 file, just plain text padding" * 10)
    access = _access(tmp_path)
    assert mp4_probe.probe_media(access, "not-a-video.mp4", path.stat().st_size) is None


def test_probe_media_returns_none_for_truncated_moov(tmp_path):
    # A `moov` box header claiming a size larger than the file actually has.
    path = tmp_path / "truncated.mp4"
    ftyp = b"\x00\x00\x00\x14ftypisom\x00\x00\x02\x00"
    moov_header = (2_000_000).to_bytes(4, "big") + b"moov" + b"\x00" * 20
    path.write_bytes(ftyp + moov_header)
    access = _access(tmp_path)
    assert mp4_probe.probe_media(access, "truncated.mp4", path.stat().st_size) is None


def test_probe_media_returns_none_when_no_moov_box(tmp_path):
    path = tmp_path / "no-moov.mp4"
    ftyp = b"\x00\x00\x00\x14ftypisom\x00\x00\x02\x00"
    path.write_bytes(ftyp)
    access = _access(tmp_path)
    assert mp4_probe.probe_media(access, "no-moov.mp4", path.stat().st_size) is None
