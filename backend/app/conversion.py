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
from pathlib import Path

# Short codec names used in profiles/variants -> (ffmpeg encoder, ffprobe-reported codec name).
_CODEC_INFO = {
    "h265": ("libx265", "hevc"),
    "h264": ("libx264", "h264"),
    "vp9": ("libvpx-vp9", "vp9"),
    "av1": ("libaom-av1", "av1"),
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
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    if result.returncode != 0:
        return None

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    video_streams = [s for s in data.get("streams", []) if s.get("codec_type") == "video"]
    video_stream = video_streams[0] if video_streams else None
    fmt = data.get("format", {})

    return {
        "has_video_stream": video_stream is not None,
        "width": video_stream.get("width") if video_stream else None,
        "height": video_stream.get("height") if video_stream else None,
        "video_codec_name": video_stream.get("codec_name") if video_stream else None,
        "format_name": fmt.get("format_name"),
        "duration": float(fmt["duration"]) if fmt.get("duration") else None,
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


def build_ffmpeg_command(
    input_path: Path,
    output_path: Path,
    *,
    video_codec: str,
    crf: int,
    drop_audio: bool,
    max_dimension: int | None = None,
    extra_encoder_args: list[str] | None = None,
) -> list[str]:
    encoder, _ = _CODEC_INFO.get(video_codec, (video_codec, video_codec))

    args = [ffmpeg_path() or "ffmpeg", "-y", "-i", str(input_path), "-c:v", encoder, "-crf", str(crf)]

    if max_dimension:
        # Shrink only the larger side, preserve aspect ratio, keep both
        # dimensions even (required by libx265/libx264 4:2:0 encoding).
        args += [
            "-vf",
            f"scale='if(gt(iw,ih),min(iw,{max_dimension}),-2)':'if(gt(iw,ih),-2,min(ih,{max_dimension}))'",
        ]

    if drop_audio:
        args.append("-an")
    else:
        args += ["-c:a", "copy"]

    if extra_encoder_args:
        args += extra_encoder_args

    args.append(str(output_path))
    return args


def run_ffmpeg(args: list[str], timeout: int = 3600) -> tuple[bool, str]:
    """Run an ffmpeg command; returns (success, stderr tail for diagnostics)."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)

    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-10:])
        return False, tail or f"ffmpeg exited with code {result.returncode}"
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
