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
_runtime_broken = False


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
    """Test-only: clears the module-level cache (and the runtime-broken
    flag below) so a test can force a fresh probe (or monkeypatch
    `_probe_backend`/`check_hardware_decode` beforehand)."""
    global _cached, _runtime_broken
    with _lock:
        _cached = None
        _runtime_broken = False


def mark_runtime_broken() -> None:
    """Called by `app/jobs/convert.py` when a hardware-decode attempt
    crashes the ffmpeg process outright (`conversion.is_crash_exit_code()`)
    rather than failing cleanly -- user report: on that driver/host, a
    crashed QSV decode session (Windows `STATUS_DLL_INIT_FAILED`,
    0xC0000142) left the very next ffmpeg process crashing the same way even
    with hardware decode no longer requested, i.e. the crash isn't specific
    to that one file. Once this fires, `decode_backend()` stops offering
    hardware decode for the rest of this process's lifetime -- cheaper and
    safer than re-crashing (and re-triggering the same fallback dance) on
    every subsequent file. Deliberately not reset between jobs; only
    `reset_cache()` (test-only) or a process restart clears it."""
    global _runtime_broken
    with _lock:
        _runtime_broken = True


def decode_backend() -> str | None:
    """QSV preferred over VAAPI when (hypothetically) both probed available,
    same order `app/hardware_accel.py` uses for encode (post-V1, user
    request: shared by `app/preview.py`'s frame extraction and
    `app/conversion.py`'s encode input, both of which use hardware decode
    automatically whenever available -- unlike encode, decode output is
    bit-identical to software decode, so there's no quality trade-off gating
    it behind a setting). Returns `None` once `mark_runtime_broken()` has
    fired, regardless of what the startup probe found."""
    with _lock:
        if _runtime_broken:
            return None
    status = check_hardware_decode()
    if status.qsv:
        return "qsv"
    if status.vaapi:
        return "vaapi"
    return None


def hwaccel_input_args(backend: str | None) -> list[str]:
    """`-hwaccel` flags go *before* `-i` (unlike an encoder's `-c:v`, which
    goes after) -- they configure how the input is decoded, not how the
    output is encoded.

    `-hwaccel_output_format <backend>` (user report, confirmed by a manual
    repro: their own working `-hwaccel qsv -hwaccel_output_format qsv`
    command converted a file the app's `-hwaccel qsv` alone could not)
    forces ffmpeg to keep the decoded frame in its hardware surface format
    instead of auto-negotiating one -- without it, decode can pick a format
    the downstream `hwdownload` filter (`conversion.build_ffmpeg_command()`)
    doesn't get a real hardware frame from, failing with "Error
    reinitializing filters!" / "Function not implemented" (or, seen on one
    host, crashing ffmpeg outright instead of failing cleanly -- see
    `mark_runtime_broken()`)."""
    if backend is None:
        return []
    args = ["-hwaccel", backend, "-hwaccel_output_format", backend]
    if backend == "vaapi":
        args += ["-hwaccel_device", "/dev/dri/renderD128"]
    return args
