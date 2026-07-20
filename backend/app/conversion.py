"""ffmpeg conversion + validation helpers (Specification §7-8, Tech Stack).

Building blocks used by the `convert` job handler (`app/jobs/convert.py`):
probing a source file with ffprobe, building the ffmpeg command for a
profile, running the encode, and validating the result before it is ever
allowed to replace or preserve-alongside a source file.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

# Short codec names used in profiles/variants -> (ffmpeg encoder, ffprobe-reported codec name).
_CODEC_INFO = {
    "h265": ("libx265", "hevc"),
    "h264": ("libx264", "h264"),
    "vp9": ("libvpx-vp9", "vp9"),
    "av1": ("libaom-av1", "av1"),
}

# (video_codec, hardware_accel) -> ffmpeg hw encoder name. Only pairs with a
# real, reasonably reliable hw encoder are listed; any pair absent here (e.g.
# ("av1", "vaapi") -- av1_vaapi support is inconsistent across Intel
# media-driver versions) falls back to the software encoder in
# resolve_encoder() below.
_HW_CODEC_INFO: dict[tuple[str, str], str] = {
    ("h264", "qsv"): "h264_qsv",
    ("h265", "qsv"): "hevc_qsv",
    ("vp9", "qsv"): "vp9_qsv",
    ("av1", "qsv"): "av1_qsv",
    ("h264", "vaapi"): "h264_vaapi",
    ("h265", "vaapi"): "hevc_vaapi",
    ("vp9", "vaapi"): "vp9_vaapi",
}


def ffmpeg_path() -> str | None:
    return shutil.which("ffmpeg")


def ffprobe_path() -> str | None:
    return shutil.which("ffprobe")


def probe_media(path: Path) -> dict | None:
    """Run ffprobe and return format/video-stream info, or None if the file
    isn't a recognizable media file (or ffprobe isn't available)."""
    probe_bin = ffprobe_path()
    if not probe_bin:
        return None

    try:
        result = subprocess.run(
            [
                probe_bin,
                "-v", "error",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            # ffprobe's JSON output is always UTF-8, regardless of the
            # OS console codepage (e.g. cp1252 on many Windows setups) that
            # `text=True` would otherwise decode with by default -- that
            # mismatch previously raised UnicodeDecodeError inside
            # subprocess's stdout reader thread for any source path
            # containing non-Latin-1 characters (e.g. Cyrillic filenames),
            # silently truncating `result.stdout` to None/empty and making
            # a perfectly valid video look "not probeable".
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    try:
        data = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        # TypeError covers `result.stdout` coming back `None`/empty despite
        # a 0 exit code (e.g. a genuinely unparseable probe).
        return None

    video_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    video_stream = video_streams[0] if video_streams else None
    fmt = data.get("format", {})

    bit_rate = fmt.get("bit_rate") or (video_stream.get("bit_rate") if video_stream else None)

    return {
        "has_video_stream": video_stream is not None,
        "width": video_stream.get("width") if video_stream else None,
        "height": video_stream.get("height") if video_stream else None,
        "video_codec_name": video_stream.get("codec_name") if video_stream else None,
        "format_name": fmt.get("format_name"),
        "duration": float(fmt["duration"]) if fmt.get("duration") else None,
        "bit_rate": int(bit_rate) if bit_rate else None,
    }


def effective_max_dimension(source_info: dict | None, configured_max: int | None) -> int | None:
    """Resizing only applies when the source exceeds the configured maximum
    dimension (Specification §7)."""
    if not configured_max or not source_info:
        return None
    width = source_info.get("width")
    height = source_info.get("height")
    if not width or not height:
        return None
    if max(width, height) <= configured_max:
        return None
    return configured_max


def has_hw_mapping(video_codec: str, hardware_accel: str) -> bool:
    return (video_codec, hardware_accel) in _HW_CODEC_INFO


def resolve_encoder(video_codec: str, hardware_accel: str = "off") -> str:
    """Resolve the actual ffmpeg encoder name for a (codec, backend) pair.
    Callers are responsible for only passing a hardware_accel value that a
    prior availability probe (app/hardware_accel.py) confirmed works on this
    host -- this function does no I/O and never fails, it just falls back to
    the software encoder for any (codec, backend) pair with no hw mapping."""
    if hardware_accel and hardware_accel != "off":
        hw_encoder = _HW_CODEC_INFO.get((video_codec, hardware_accel))
        if hw_encoder:
            return hw_encoder
    encoder, _ = _CODEC_INFO.get(video_codec, (video_codec, video_codec))
    return encoder


def build_ffmpeg_command(
    input_path: Path,
    output_path: Path,
    *,
    video_codec: str,
    crf: int,
    drop_audio: bool,
    max_dimension: int | None = None,
    extra_encoder_args: list[str] | None = None,
    hardware_accel: str = "off",
    decode_hw: bool = True,
) -> list[str]:
    """`decode_hw=True` (the default, post-V1, user request) hardware-decodes
    the source whenever available, same automatic-no-setting-needed
    reasoning `app/preview.py`'s frame extraction already uses: unlike
    `hardware_accel` (the ENCODER, gated behind a per-profile setting
    because of a real quality/size trade-off), decode output is
    bit-identical to software decode, so there's nothing to trade off.
    `decode_hw=False` is for `app/jobs/convert.py::_encode_and_validate`'s
    software-encoder retry after a hardware encode failure -- ruling out
    hardware decode as a variable too on that second attempt."""
    # Local import: `app.hardware_decode` imports `ffmpeg_path` from this
    # module, so a module-level import here would be circular.
    from app import hardware_decode as hw_decode

    encoder = resolve_encoder(video_codec, hardware_accel)
    decode_backend = hw_decode.decode_backend() if decode_hw else None

    args = [ffmpeg_path() or "ffmpeg", "-y", *hw_decode.hwaccel_input_args(decode_backend)]
    args += ["-i", str(input_path), "-c:v", encoder, "-crf", str(crf)]

    filters = []
    if decode_backend:
        # Same "Impossible to convert between the formats" failure
        # `app/preview.py`'s frame extraction hit for mjpeg output applies
        # here too: a hw-decoded frame comes back in a GPU-specific surface
        # format that no downstream filter or software encoder can consume
        # directly without this download step first (verified there against
        # a real file: identical pixel output to software decode).
        filters.append("hwdownload,format=nv12")
    if max_dimension:
        # Shrink only the larger side, preserve aspect ratio, keep both
        # dimensions even (required by libx265/libx264 4:2:0 encoding).
        filters.append(
            f"scale='if(gt(iw,ih),min(iw,{max_dimension}),-2)':'if(gt(iw,ih),-2,min(ih,{max_dimension}))'"
        )
    if filters:
        args += ["-vf", ",".join(filters)]

    if drop_audio:
        args.append("-an")
    else:
        args += ["-c:a", "copy"]

    if extra_encoder_args:
        args += extra_encoder_args

    if output_path.suffix.lower() == ".mp4":
        # Moves the moov atom to the front of the file so the embedded
        # player can start playback after fetching just the first Range
        # request instead of needing the tail of the file first (user
        # report: long stall before playback starts over the streaming
        # proxy). No-op for containers other than mp4.
        args += ["-movflags", "+faststart"]

    args.append(str(output_path))
    return args


def _parse_ffmpeg_out_time(value: str) -> float | None:
    """Parses `-progress`'s `out_time=HH:MM:SS.ffffff` line into seconds."""
    try:
        hours, minutes, seconds = value.split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except (ValueError, AttributeError):
        return None


def run_ffmpeg(
    args: list[str],
    timeout: int = 3600,
    *,
    duration: float | None = None,
    on_progress: Callable[[float], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> tuple[bool, str]:
    """Run an ffmpeg command; returns (success, stderr tail for diagnostics).

    Runs via `Popen` with `-progress pipe:1 -nostats` instead of a single
    blocking `subprocess.run()` so two things become possible (post-V1, user
    request): `on_progress(percent)` is called as the encode advances
    (parsed from the `out_time=` lines against `duration` in seconds) so a
    live progress bar can move within a single file's encode instead of only
    jumping between files; and `should_stop()`, polled between progress
    lines, lets a cooperative cancel/pause request kill an in-flight encode
    right away instead of only being noticed once ffmpeg finishes on its own
    (previously the only way out of a stuck encode was the force-cancel path
    in `app/jobs/service.py::cancel_job`)."""
    # `-progress pipe:1` is a global option -- inserted right after the
    # binary so it applies regardless of where the caller's own args end.
    popen_args = [args[0], "-progress", "pipe:1", "-nostats", *args[1:]]
    try:
        # See probe_media()'s comment: ffmpeg's stderr log can echo the
        # source path, so decoding it against the OS console codepage
        # instead of UTF-8 risks the same reader-thread crash for
        # non-Latin-1 filenames.
        process = subprocess.Popen(
            popen_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except OSError as exc:
        return False, str(exc)

    stderr_tail: list[str] = []

    def _drain_stderr() -> None:
        assert process.stderr is not None
        for line in process.stderr:
            stderr_tail.append(line.rstrip("\n"))
            del stderr_tail[:-10]

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    deadline = time.monotonic() + timeout
    stopped = False
    timed_out = False
    assert process.stdout is not None
    for line in process.stdout:
        line = line.strip()
        if on_progress and duration and line.startswith("out_time="):
            out_time_seconds = _parse_ffmpeg_out_time(line.split("=", 1)[1])
            if out_time_seconds is not None:
                on_progress(min(100.0, out_time_seconds / duration * 100))
        if should_stop is not None and should_stop():
            stopped = True
            process.terminate()
            break
        if time.monotonic() > deadline:
            timed_out = True
            process.kill()
            break

    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)
    stderr_thread.join(timeout=5)

    if stopped:
        return False, "Cancelled."
    if timed_out:
        return False, f"ffmpeg timed out after {timeout}s"
    if process.returncode != 0:
        tail = "\n".join(stderr_tail[-10:])
        return False, tail or f"ffmpeg exited with code {process.returncode}"
    if on_progress:
        on_progress(100.0)
    return True, ""


def validate_converted_output(path: Path, *, video_codec: str, container: str) -> tuple[bool, str]:
    """Lightweight validation pass (Specification §8.1): existence, non-zero
    size, ffprobe-recognized media, expected video stream, and expected
    container/codec combination. Deliberately avoids full decode playback.
    """
    if not path.exists():
        return False, "Output file does not exist."
    if path.stat().st_size == 0:
        return False, "Output file is empty."

    info = probe_media(path)
    if info is None:
        return False, "Output is not recognized as a valid media file by ffprobe."
    if not info["has_video_stream"]:
        return False, "Output has no video stream."

    if path.suffix.lstrip(".").lower() != container.lower():
        return False, f"Output extension does not match expected container: {container}."

    _, expected_codec_name = _CODEC_INFO.get(video_codec, (video_codec, video_codec))
    if info["video_codec_name"] != expected_codec_name:
        return False, (
            f"Output video codec ({info['video_codec_name']}) does not match "
            f"expected codec ({expected_codec_name})."
        )

    return True, ""


def encode_variant_suffix(profile: dict, overrides: dict) -> str:
    """Build the `<params>` part of `<basename>.variant-<params>.mp4`
    (Specification §8.3), e.g. `d1000-crf28` or `h264-d1000-crf28`."""
    parts: list[str] = []

    codec = overrides.get("video_codec", profile["video_codec"])
    if codec != profile["video_codec"]:
        parts.append(codec)

    max_dimension = overrides.get("max_dimension", profile.get("max_dimension"))
    if max_dimension:
        parts.append(f"d{max_dimension}")

    crf = overrides.get("crf", profile["crf"])
    parts.append(f"crf{crf}")

    return "-".join(parts)
