from __future__ import annotations

import uuid
from pathlib import Path

from .db import connection
from .errors import ApiError
from .time_utils import utc_now


DEFAULT_PROFILE_ID = "default-h265-mp4"


class ConversionProfileService:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path
        self.ensure_default_profile()

    def ensure_default_profile(self) -> None:
        now = utc_now()
        with connection(self._database_path) as conn, conn:
            has_default = conn.execute(
                "SELECT id FROM conversion_profiles WHERE is_default = 1 LIMIT 1"
            ).fetchone()
            if has_default is not None:
                return

            has_any = conn.execute(
                "SELECT id FROM conversion_profiles LIMIT 1"
            ).fetchone()
            if has_any is not None:
                conn.execute(
                    """
                    UPDATE conversion_profiles
                    SET is_default = 1, updated_at = ?
                    WHERE id = (
                        SELECT id
                        FROM conversion_profiles
                        ORDER BY created_at ASC, id ASC
                        LIMIT 1
                    )
                    """,
                    (now,),
                )
                return

            conn.execute(
                """
                INSERT INTO conversion_profiles (
                    id, name, is_default, video_codec, container, max_dimension,
                    quality_mode, quality_value, drop_audio, extra_encoder_args,
                    created_at, updated_at
                ) VALUES (?, ?, 1, ?, ?, NULL, NULL, NULL, 1, NULL, ?, ?)
                """,
                (DEFAULT_PROFILE_ID, "Default H.265 MP4", "h265", "mp4", now, now),
            )

    def list_profiles(self) -> list[dict]:
        self.ensure_default_profile()
        with connection(self._database_path) as conn:
            rows = conn.execute(
                """
                SELECT id, name, is_default, video_codec, container, max_dimension,
                       quality_mode, quality_value, drop_audio, extra_encoder_args,
                       created_at, updated_at
                FROM conversion_profiles
                ORDER BY is_default DESC, name COLLATE NOCASE ASC, id ASC
                """
            ).fetchall()
        return [self._serialize_profile_row(row) for row in rows]

    def create_profile(self, payload: dict) -> dict:
        normalized = _normalize_profile_payload(payload)
        now = utc_now()
        profile_id = str(uuid.uuid4())
        with connection(self._database_path) as conn, conn:
            if normalized["is_default"]:
                conn.execute("UPDATE conversion_profiles SET is_default = 0, updated_at = ?", (now,))
            conn.execute(
                """
                INSERT INTO conversion_profiles (
                    id, name, is_default, video_codec, container, max_dimension,
                    quality_mode, quality_value, drop_audio, extra_encoder_args,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile_id,
                    normalized["name"],
                    int(normalized["is_default"]),
                    normalized["video_codec"],
                    normalized["container"],
                    normalized["max_dimension"],
                    normalized["quality_mode"],
                    normalized["quality_value"],
                    int(normalized["drop_audio"]),
                    normalized["extra_encoder_args"],
                    now,
                    now,
                ),
            )
        return self.get_profile(profile_id)

    def get_profile(self, profile_id: str) -> dict:
        with connection(self._database_path) as conn:
            row = conn.execute(
                """
                SELECT id, name, is_default, video_codec, container, max_dimension,
                       quality_mode, quality_value, drop_audio, extra_encoder_args,
                       created_at, updated_at
                FROM conversion_profiles
                WHERE id = ?
                """,
                (profile_id,),
            ).fetchone()
        if row is None:
            raise ApiError("conversion_profile_not_found", "Requested conversion profile does not exist.", status=404)
        return self._serialize_profile_row(row)

    def resolve_profile(self, profile_id: str | None) -> dict:
        self.ensure_default_profile()
        if profile_id:
            return self.get_profile(profile_id)

        with connection(self._database_path) as conn:
            row = conn.execute(
                """
                SELECT id, name, is_default, video_codec, container, max_dimension,
                       quality_mode, quality_value, drop_audio, extra_encoder_args,
                       created_at, updated_at
                FROM conversion_profiles
                WHERE is_default = 1
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            raise ApiError("conversion_profile_not_found", "No default conversion profile is configured.", status=400)
        return self._serialize_profile_row(row)

    def _serialize_profile_row(self, row) -> dict:
        return {
            "id": row["id"],
            "name": row["name"],
            "is_default": bool(row["is_default"]),
            "video_codec": row["video_codec"],
            "container": row["container"],
            "max_dimension": row["max_dimension"],
            "quality_mode": row["quality_mode"],
            "quality_value": row["quality_value"],
            "drop_audio": bool(row["drop_audio"]),
            "extra_encoder_args": row["extra_encoder_args"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


def _normalize_profile_payload(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ApiError("invalid_request", "Profile payload must be a JSON object.", status=400)

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ApiError("invalid_request", "Field 'name' must be a non-empty string.", status=400)

    video_codec = str(payload.get("video_codec") or "h265").strip().lower()
    container = str(payload.get("container") or "mp4").strip().lower().lstrip(".")
    if video_codec == "hevc":
        video_codec = "h265"
    if video_codec not in {"h264", "h265", "av1"}:
        raise ApiError("invalid_request", "Supported codecs are H.264, H.265, and AV1.", status=400)
    if container != "mp4":
        raise ApiError("invalid_request", "Only MP4 output is supported in this step.", status=400)

    max_dimension = payload.get("max_dimension")
    if max_dimension is not None:
        if isinstance(max_dimension, bool) or not isinstance(max_dimension, int) or max_dimension < 1:
            raise ApiError("invalid_request", "Field 'max_dimension' must be a positive integer when provided.", status=400)

    quality_mode = payload.get("quality_mode")
    quality_value = payload.get("quality_value")
    if quality_mode is not None and not isinstance(quality_mode, str):
        raise ApiError("invalid_request", "Field 'quality_mode' must be a string when provided.", status=400)
    if quality_value is not None and not isinstance(quality_value, str):
        raise ApiError("invalid_request", "Field 'quality_value' must be a string when provided.", status=400)

    drop_audio = payload.get("drop_audio", True)
    if not isinstance(drop_audio, bool):
        raise ApiError("invalid_request", "Field 'drop_audio' must be a boolean.", status=400)

    extra_encoder_args = payload.get("extra_encoder_args")
    if extra_encoder_args is not None and not isinstance(extra_encoder_args, str):
        raise ApiError("invalid_request", "Field 'extra_encoder_args' must be a string when provided.", status=400)

    is_default = bool(payload.get("is_default", False))
    return {
        "name": name.strip(),
        "is_default": is_default,
        "video_codec": video_codec,
        "container": "mp4",
        "max_dimension": max_dimension,
        "quality_mode": quality_mode.strip() if isinstance(quality_mode, str) and quality_mode.strip() else None,
        "quality_value": quality_value.strip() if isinstance(quality_value, str) and quality_value.strip() else None,
        "drop_audio": drop_audio,
        "extra_encoder_args": extra_encoder_args.strip() if isinstance(extra_encoder_args, str) and extra_encoder_args.strip() else None,
    }
