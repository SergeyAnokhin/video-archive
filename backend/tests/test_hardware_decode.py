"""Hardware-accelerated decode tests: availability-probe tests mock the
actual subprocess calls so they don't depend on real hardware being present,
and a couple of self-skipping smoke tests exercise the real probe/decode
when ffmpeg happens to be on PATH -- mirroring `test_hardware_accel.py`'s own
`pytest.mark.skipif` convention rather than assuming QSV/VAAPI hardware.
"""

from __future__ import annotations

import shutil

import pytest

from app import hardware_decode


@pytest.fixture(autouse=True)
def _reset_hardware_decode_cache():
    hardware_decode.reset_cache()
    yield
    hardware_decode.reset_cache()


# --- check_hardware_decode (mocked probes) ------------------------------------


def test_check_hardware_decode_no_ffmpeg_returns_all_false(monkeypatch):
    monkeypatch.setattr(hardware_decode, "ffmpeg_path", lambda: None)
    status = hardware_decode.check_hardware_decode()
    assert status.qsv is False
    assert status.vaapi is False
    assert status.any_available is False


def test_check_hardware_decode_no_probe_source_returns_all_false(monkeypatch):
    monkeypatch.setattr(hardware_decode, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(hardware_decode, "_make_probe_source", lambda ffmpeg_bin, out_path: False)
    status = hardware_decode.check_hardware_decode()
    assert status.qsv is False
    assert status.vaapi is False


def test_check_hardware_decode_caches_result(monkeypatch):
    monkeypatch.setattr(hardware_decode, "ffmpeg_path", lambda: "ffmpeg")
    monkeypatch.setattr(hardware_decode, "_make_probe_source", lambda ffmpeg_bin, out_path: True)
    call_count = {"n": 0}

    def fake_probe(ffmpeg_bin, backend, source_path):
        call_count["n"] += 1
        return backend == "qsv"

    monkeypatch.setattr(hardware_decode, "_probe_backend", fake_probe)

    first = hardware_decode.check_hardware_decode()
    second = hardware_decode.check_hardware_decode()
    assert first.qsv is True
    assert first.vaapi is False
    assert second is first  # served from cache, no extra probing
    assert call_count["n"] == 2  # one probe per backend, only once

    forced = hardware_decode.check_hardware_decode(force=True)
    assert call_count["n"] == 4  # force=True re-probes both backends
    assert forced.qsv is True


def test_check_hardware_decode_vaapi_short_circuits_without_dev_dri(monkeypatch):
    monkeypatch.setattr(hardware_decode.Path, "exists", lambda self: False)
    assert hardware_decode._probe_backend("ffmpeg", "vaapi", hardware_decode.Path("source.mp4")) is False


# --- log_status ----------------------------------------------------------------


def test_log_status_reports_available_backends(caplog):
    with caplog.at_level("INFO", logger="app.hardware_decode"):
        hardware_decode.log_status(hardware_decode.HardwareDecodeStatus(qsv=True, vaapi=False))
    assert "Hardware decode: qsv=True, vaapi=False" in caplog.text


def test_log_status_reports_unavailable(caplog):
    with caplog.at_level("INFO", logger="app.hardware_decode"):
        hardware_decode.log_status(hardware_decode.HardwareDecodeStatus(qsv=False, vaapi=False))
    assert "Hardware decode unavailable, using software decoding" in caplog.text


# --- real-hardware smoke tests (self-skipping) ----------------------------------


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_check_hardware_decode_real_probe_does_not_crash():
    status = hardware_decode.check_hardware_decode()
    assert isinstance(status.qsv, bool)
    assert isinstance(status.vaapi, bool)


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_extract_frame_image_uses_hw_decode_when_available(tmp_path):
    if not hardware_decode.check_hardware_decode().any_available:
        pytest.skip("No hardware decode backend available on this host")

    from app import preview

    from .conftest import make_video

    video_path = tmp_path / "clip.mp4"
    make_video(video_path, duration=2.0, size="320x240")

    image = preview.extract_frame_image(video_path, 1.0)
    assert image is not None
    assert image.shape[:2] == (240, 320)
