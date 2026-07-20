"""Intel hardware-accelerated encoder availability (QSV on Windows, VAAPI
groundwork for Linux/k3s): analogous to `app/ffmpeg.py`'s `check_ffmpeg()`,
but `ffmpeg -encoders` only proves the encoder was compiled in, not that a
working iGPU + driver is actually present on this host -- a real hevc_qsv
encode succeeding is the only trustworthy signal. Probed once at startup
(`app/main.py`), cached, exposed via `GET /app/info` so the frontend can
show/gate the per-profile `hardware_accel` option; `reset_cache()` lets
tests bypass the cache.
"""

from __future__ import annotations

import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from app.conversion import ffmpeg_path, resolve_encoder


@dataclass(frozen=True)
class HardwareAccelStatus:
    qsv: bool
    vaapi: bool


_lock = threading.Lock()
_cached: HardwareAccelStatus | None = None


def _probe_backend(ffmpeg_bin: str, backend: str) -> bool:
    encoder = resolve_encoder("h264", backend)
    if encoder == "h264":
        # No hw mapping registered for this backend at all.
        return False
    if backend == "vaapi" and not Path("/dev/dri").exists():
        # Cheap short-circuit: no render device node on this host/container.
        return False

    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "probe.mp4"
        args = [ffmpeg_bin, "-y"]
        if backend == "vaapi":
            args += ["-vaapi_device", "/dev/dri/renderD128"]
        args += ["-f", "lavfi", "-i", "testsrc=duration=0.1:size=64x64:rate=5"]
        if backend == "vaapi":
            args += ["-vf", "format=nv12,hwupload"]
        args += ["-c:v", encoder, "-frames:v", "1", str(out_path)]
        try:
            result = subprocess.run(args, capture_output=True, timeout=15, check=False)
        except (OSError, subprocess.SubprocessError):
            return False
        return result.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0


def check_hardware_accel(*, force: bool = False) -> HardwareAccelStatus:
    global _cached
    with _lock:
        if _cached is not None and not force:
            return _cached
        ffmpeg_bin = ffmpeg_path()
        if not ffmpeg_bin:
            _cached = HardwareAccelStatus(qsv=False, vaapi=False)
        else:
            _cached = HardwareAccelStatus(
                qsv=_probe_backend(ffmpeg_bin, "qsv"),
                vaapi=_probe_backend(ffmpeg_bin, "vaapi"),
            )
        return _cached


def reset_cache() -> None:
    """Test-only: clears the module-level cache so a test can force a fresh
    probe (or monkeypatch `_probe_backend`/`check_hardware_accel` beforehand)."""
    global _cached
    with _lock:
        _cached = None
