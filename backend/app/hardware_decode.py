"""Intel hardware-accelerated DECODE availability (QSV/VAAPI) for frame
extraction (`app/preview.py`). This is a separate probe from
`app/hardware_accel.py`'s encode one -- a working hardware encoder doesn't
imply a working hardware decoder (and vice versa), same "real operation
succeeding is the only trustworthy signal" reasoning, just decoding instead
of encoding a throwaway clip. Probed once at startup (`app/main.py`), cached,
logged once via `log_status()`; `reset_cache()` lets tests bypass the cache.

Unlike encode (`hardware_accel.py`, gated behind a per-profile
`hardware_accel` setting because of a real quality/size tradeoff), hardware
decode output is bit-identical to software decode -- there's nothing to
trade off, so `app/preview.py` uses it automatically whenever available, no
setting involved.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from app.conversion import ffmpeg_path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class HardwareDecodeStatus:
    qsv: bool
    vaapi: bool

    @property
    def any_available(self) -> bool:
        return self.qsv or self.vaapi


_lock = threading.Lock()
_cached: HardwareDecodeStatus | None = None


def _make_probe_source(ffmpeg_bin: str, out_path: Path) -> bool:
    """Software-encode a tiny throwaway h264 clip to hand to the decode probe
    below -- hwaccel decode needs a real compressed bitstream, `lavfi`'s
    `testsrc` on its own is just a raw pattern generator."""
    args = [
        ffmpeg_bin, "-y",
        "-f", "lavfi", "-i", "testsrc=duration=0.5:size=320x240:rate=10",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(out_path),
    ]
    try:
        result = subprocess.run(args, capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0


def _probe_backend(ffmpeg_bin: str, backend: str, source_path: Path) -> bool:
    if backend == "vaapi" and not Path("/dev/dri").exists():
        # Cheap short-circuit: no render device node on this host/container.
        return False

    args = [ffmpeg_bin, "-y", "-hwaccel", backend]
    if backend == "vaapi":
        args += ["-hwaccel_device", "/dev/dri/renderD128"]
    args += ["-i", str(source_path), "-frames:v", "1", "-f", "null", "-"]
    try:
        result = subprocess.run(args, capture_output=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def check_hardware_decode(*, force: bool = False) -> HardwareDecodeStatus:
    global _cached
    with _lock:
        if _cached is not None and not force:
            return _cached
        ffmpeg_bin = ffmpeg_path()
        if not ffmpeg_bin:
            _cached = HardwareDecodeStatus(qsv=False, vaapi=False)
            return _cached

        with tempfile.TemporaryDirectory() as tmp_dir:
            source_path = Path(tmp_dir) / "probe_source.mp4"
            if not _make_probe_source(ffmpeg_bin, source_path):
                _cached = HardwareDecodeStatus(qsv=False, vaapi=False)
            else:
                _cached = HardwareDecodeStatus(
                    qsv=_probe_backend(ffmpeg_bin, "qsv", source_path),
                    vaapi=_probe_backend(ffmpeg_bin, "vaapi", source_path),
                )
        return _cached


def log_status(status: HardwareDecodeStatus) -> None:
    """Called once from `app/main.py`'s startup lifespan (not from
    `check_hardware_decode()` itself, which callers may re-invoke per file --
    see `app/preview.py`) so the "what's actually being used" line is logged
    exactly once per process."""
    if status.any_available:
        logger.info("Hardware decode: qsv=%s, vaapi=%s", status.qsv, status.vaapi)
    else:
        logger.info("Hardware decode unavailable, using software decoding")


def reset_cache() -> None:
    """Test-only: clears the module-level cache so a test can force a fresh
    probe (or monkeypatch `_probe_backend`/`check_hardware_decode` beforehand)."""
    global _cached
    with _lock:
        _cached = None
