from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

from .errors import ApiError


CODEC_ALIASES = {
    "h264": {"h264", "avc1"},
    "h265": {"hevc", "h265"},
    "av1": {"av1"},
}

CONTAINER_ALIASES = {
    "mp4": {"mp4", "mov,mp4,m4a,3gp,3g2,mj2"},
}

ENCODER_BY_CODEC = {
    "h264": "libx264",
    "h265": "libx265",
    "av1": "libsvtav1",
}


class ConversionService:
    def __init__(self, *, ffmpeg_binary: str = "ffmpeg", ffprobe_binary: str = "ffprobe") -> None:
        self._ffmpeg_binary = ffmpeg_binary
        self._ffprobe_binary = ffprobe_binary

    def convert_file(self, *, source_root: str, file_row: dict, profile: dict, mode: str) -> dict:
        source_path = Path(file_row["path"])
        source_root_path = Path(source_root)
        if not source_path.exists():
            raise ApiError("source_file_missing", f"Source file is missing: {source_path}", status=404)

        container = profile["container"].lower().lstrip(".")
        temp_output = source_path.parent / f".video-archive-{uuid.uuid4().hex}.tmp.{container}"

        try:
            self._run_ffmpeg(source_path, temp_output, profile)
            validation = self._validate_output(temp_output, profile)
            if mode == "production":
                final_path = self._replace_source(source_path, temp_output, container)
            elif mode == "test":
                final_path = self._write_test_output(source_path, temp_output, profile, container)
            else:
                raise ApiError("invalid_conversion_mode", "Conversion mode must be 'production' or 'test'.", status=400)

            stat_result = final_path.stat()
            return {
                "path": str(final_path),
                "relative_path": final_path.relative_to(source_root_path).as_posix(),
                "file_name": final_path.name,
                "extension": final_path.suffix.lower(),
                "size_bytes": int(stat_result.st_size),
                "modified_at": _timestamp_from_epoch(stat_result.st_mtime),
                "output_ref": str(final_path),
                "validation": validation,
            }
        finally:
            if temp_output.exists():
                temp_output.unlink()

    def _run_ffmpeg(self, source_path: Path, temp_output: Path, profile: dict) -> None:
        if shutil.which(self._ffmpeg_binary) is None:
            raise ApiError("ffmpeg_not_available", "ffmpeg is not available on the backend machine.", status=500)

        command = [
            self._ffmpeg_binary,
            "-y",
            "-i",
            str(source_path),
            "-map",
            "0:v:0",
            "-c:v",
            ENCODER_BY_CODEC.get(str(profile.get("video_codec") or "h265").lower(), "libx265"),
            "-movflags",
            "+faststart",
        ]

        max_dimension = profile.get("max_dimension")
        if isinstance(max_dimension, int) and max_dimension > 0:
            command.extend(["-vf", f"scale={max_dimension}:{max_dimension}:force_original_aspect_ratio=decrease"])

        quality_value = profile.get("quality_value")
        if isinstance(quality_value, str) and quality_value.strip():
            command.extend(["-crf", quality_value.strip()])

        if profile.get("drop_audio", True):
            command.append("-an")
        else:
            command.extend(["-c:a", "aac", "-b:a", "128k"])

        extra_encoder_args = profile.get("extra_encoder_args")
        if isinstance(extra_encoder_args, str) and extra_encoder_args.strip():
            command.extend(extra_encoder_args.strip().split())

        command.append(str(temp_output))
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "ffmpeg failed").strip().splitlines()[-1]
            raise ApiError("conversion_failed", f"ffmpeg conversion failed: {detail}", status=500)

    def _validate_output(self, temp_output: Path, profile: dict) -> dict:
        if not temp_output.exists():
            raise ApiError("conversion_validation_failed", "Converted output file was not created.", status=500)
        if temp_output.stat().st_size <= 0:
            raise ApiError("conversion_validation_failed", "Converted output file is empty.", status=500)
        if shutil.which(self._ffprobe_binary) is None:
            raise ApiError("ffprobe_not_available", "ffprobe is not available on the backend machine.", status=500)

        command = [
            self._ffprobe_binary,
            "-v",
            "error",
            "-show_entries",
            "format=format_name:stream=codec_type,codec_name,width,height",
            "-of",
            "json",
            str(temp_output),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "ffprobe failed").strip().splitlines()[-1]
            raise ApiError("conversion_validation_failed", f"ffprobe validation failed: {detail}", status=500)

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ApiError("conversion_validation_failed", "ffprobe returned invalid JSON.", status=500) from exc

        streams = payload.get("streams") or []
        video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        if video_stream is None:
            raise ApiError("conversion_validation_failed", "Converted output has no video stream.", status=500)

        codec_name = str(video_stream.get("codec_name") or "").lower()
        expected_codec = str(profile["video_codec"]).lower()
        if codec_name not in CODEC_ALIASES.get(expected_codec, {expected_codec}):
            raise ApiError(
                "conversion_validation_failed",
                f"Converted output codec '{codec_name or 'unknown'}' does not match expected '{expected_codec}'.",
                status=500,
            )

        format_name = str((payload.get("format") or {}).get("format_name") or "").lower()
        expected_container = str(profile["container"]).lower().lstrip(".")
        allowed_formats = CONTAINER_ALIASES.get(expected_container, {expected_container})
        if format_name not in allowed_formats:
            raise ApiError(
                "conversion_validation_failed",
                f"Converted output container '{format_name or 'unknown'}' does not match expected '{expected_container}'.",
                status=500,
            )

        width = int(video_stream.get("width") or 0)
        height = int(video_stream.get("height") or 0)
        if width <= 0 or height <= 0:
            raise ApiError("conversion_validation_failed", "Converted output is missing video dimensions.", status=500)

        return {
            "codec_name": codec_name,
            "format_name": format_name,
            "width": width,
            "height": height,
        }

    def _replace_source(self, source_path: Path, temp_output: Path, container: str) -> Path:
        target_path = source_path.with_suffix(f".{container}")
        if target_path == source_path:
            os.replace(temp_output, target_path)
            return target_path

        backup_path = source_path.parent / f".video-archive-backup-{uuid.uuid4().hex}{source_path.suffix}"
        os.replace(source_path, backup_path)
        try:
            os.replace(temp_output, target_path)
        except Exception:
            if backup_path.exists() and not source_path.exists():
                os.replace(backup_path, source_path)
            raise
        else:
            if backup_path.exists():
                backup_path.unlink()
        return target_path

    def _write_test_output(self, source_path: Path, temp_output: Path, profile: dict, container: str) -> Path:
        profile_slug = _slugify(profile["name"])
        target_path = source_path.with_name(f"{source_path.stem}.__test__{profile_slug}.{container}")
        os.replace(temp_output, target_path)
        return target_path


def _slugify(value: str) -> str:
    lowered = "".join(char.lower() if char.isalnum() else "-" for char in value)
    collapsed = "-".join(part for part in lowered.split("-") if part)
    return collapsed or "profile"


def _timestamp_from_epoch(value: float) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(value, UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
