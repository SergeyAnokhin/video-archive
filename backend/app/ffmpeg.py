"""ffmpeg availability check, per Tech Stack: verified once at startup."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class FfmpegStatus:
    available: bool
    version: str | None
    path: str | None


def check_ffmpeg() -> FfmpegStatus:
    path = shutil.which("ffmpeg")
    if not path:
        return FfmpegStatus(available=False, version=None, path=None)

    try:
        result = subprocess.run(
            [path, "-version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        first_line = result.stdout.splitlines()[0] if result.stdout else ""
        # Typical output: "ffmpeg version 8.0.1-full_build-www.gyan.dev Copyright ..."
        version = first_line.removeprefix("ffmpeg version ").split(" ", 1)[0].strip() or None
    except (OSError, subprocess.SubprocessError, IndexError):
        version = None

    return FfmpegStatus(available=True, version=version, path=path)
