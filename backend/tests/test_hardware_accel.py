"""Hardware-accelerated encoding tests: pure encoder-resolution logic runs
unconditionally (no ffmpeg needed), availability-probe tests mock the actual
subprocess call so they don't depend on real hardware being present, and a
couple of self-skipping smoke tests exercise the real probe/encode when
ffmpeg happens to be on PATH -- mirroring test_conversion.py's own
`pytest.mark.skipif` convention rather than assuming QSV/VAAPI hardware.
"""

from __future__ import annotations

import shutil

import pytest

from app import conversion, hardware_accel


@pytest.fixture(autouse=True)
def _reset_hardware_accel_cache():
    hardware_accel.reset_cache()
    yield
    hardware_accel.reset_cache()


# --- resolve_encoder / has_hw_mapping (pure, no I/O) --------------------------


def test_resolve_encoder_off_uses_software():
    assert conversion.resolve_encoder("h265", "off") == "libx265"
    assert conversion.resolve_encoder("h264") == "libx264"


def test_resolve_encoder_maps_hw_backend():
    assert conversion.resolve_encoder("h265", "qsv") == "hevc_qsv"
    assert conversion.resolve_encoder("h264", "qsv") == "h264_qsv"
    assert conversion.resolve_encoder("h265", "vaapi") == "hevc_vaapi"


def test_resolve_encoder_falls_back_when_no_hw_mapping():
    # av1+vaapi has no registered hw mapping -- falls back to the software encoder.
    assert conversion.resolve_encoder("av1", "vaapi") == "libaom-av1"
    # Unknown codec: falls back to the software lookup's own passthrough behavior.
    assert conversion.resolve_encoder("mpeg2", "qsv") == "mpeg2"


def test_has_hw_mapping():
    assert conversion.has_hw_mapping("h265", "qsv") is True
    assert conversion.has_hw_mapping("av1", "vaapi") is False
    assert conversion.has_hw_mapping("h265", "off") is False


def test_build_ffmpeg_command_uses_resolved_hw_encoder(tmp_path):
    args = conversion.build_ffmpeg_command(
        tmp_path / "in.mp4", tmp_path / "out.mp4",
        video_codec="h265", crf=26, drop_audio=True, hardware_accel="qsv",
    )
    assert "hevc_qsv" in args
    assert "libx265" not in args


def test_build_ffmpeg_command_defaults_to_software():
    args = conversion.build_ffmpeg_command(
        __import__("pathlib").Path("in.mp4"), __import__("pathlib").Path("out.mp4"),
        video_codec="h265", crf=26, drop_audio=True,
    )
    assert "libx265" in args


# --- check_hardware_accel (mocked probes) -------------------------------------


def test_check_hardware_accel_no_ffmpeg_returns_all_false(monkeypatch):
    monkeypatch.setattr(hardware_accel, "ffmpeg_path", lambda: None)
    status = hardware_accel.check_hardware_accel()
    assert status.qsv is False
    assert status.vaapi is False


def test_check_hardware_accel_caches_result(monkeypatch):
    monkeypatch.setattr(hardware_accel, "ffmpeg_path", lambda: "ffmpeg")
    call_count = {"n": 0}

    def fake_probe(ffmpeg_bin, backend):
        call_count["n"] += 1
        return backend == "qsv"

    monkeypatch.setattr(hardware_accel, "_probe_backend", fake_probe)

    first = hardware_accel.check_hardware_accel()
    second = hardware_accel.check_hardware_accel()
    assert first.qsv is True
    assert first.vaapi is False
    assert second is first  # served from cache, no extra probing
    assert call_count["n"] == 2  # one probe per backend, only once

    forced = hardware_accel.check_hardware_accel(force=True)
    assert call_count["n"] == 4  # force=True re-probes both backends


def test_check_hardware_accel_vaapi_short_circuits_without_dev_dri(monkeypatch):
    monkeypatch.setattr(hardware_accel.Path, "exists", lambda self: False)
    assert hardware_accel._probe_backend("ffmpeg", "vaapi") is False


# --- real-hardware smoke tests (self-skipping) --------------------------------


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_check_hardware_accel_real_probe_does_not_crash():
    status = hardware_accel.check_hardware_accel()
    assert isinstance(status.qsv, bool)
    assert isinstance(status.vaapi, bool)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_qsv_real_encode_when_available(tmp_path):
    if not hardware_accel.check_hardware_accel().qsv:
        pytest.skip("QSV not available on this host")

    from .conftest import make_video

    src = tmp_path / "clip.mp4"
    out = tmp_path / "out.mp4"
    make_video(src, duration=1.0)

    args = conversion.build_ffmpeg_command(
        src, out, video_codec="h265", crf=26, drop_audio=True, hardware_accel="qsv",
    )
    ok, err = conversion.run_ffmpeg(args)
    assert ok, err
    info = conversion.probe_media(out)
    assert info["video_codec_name"] == "hevc"
