"""Conversion profile CRUD (Data Model §4, Specification §7).

A profile is a saved ffmpeg parameter set reused by the `convert` job
(`app/jobs/convert.py`). Profiles have no built-in/protected concept (unlike
`preview_layout_presets`), so deletion is unconditional.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

DEFAULT_VIDEO_CODEC = "h265"
DEFAULT_CONTAINER = "mp4"
DEFAULT_CRF = 26
DEFAULT_HARDWARE_ACCEL = "off"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "is_default": bool(row.is_default),
        "video_codec": row.video_codec,
        "container": row.container,
        "max_dimension": row.max_dimension,
        "crf": row.crf,
        "drop_audio": bool(row.drop_audio),
        "hardware_accel": row.hardware_accel,
        "extra_encoder_args": json.loads(row.extra_encoder_args) if row.extra_encoder_args else None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_profiles(engine) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM conversion_profiles ORDER BY name COLLATE NOCASE")
        ).all()
    return [_row_to_dict(row) for row in rows]


def get_profile(engine, profile_id: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM conversion_profiles WHERE id = :id"), {"id": profile_id}
        ).fetchone()
    return _row_to_dict(row) if row else None


def create_profile(engine, data: dict) -> dict:
    profile_id = str(uuid.uuid4())
    now = _now()
    is_default = bool(data.get("is_default", False))

    with engine.begin() as conn:
        if is_default:
            conn.execute(text("UPDATE conversion_profiles SET is_default = 0"))
        conn.execute(
            text(
                """
                INSERT INTO conversion_profiles
                    (id, name, is_default, video_codec, container, max_dimension,
                     crf, drop_audio, hardware_accel, extra_encoder_args, created_at, updated_at)
                VALUES
                    (:id, :name, :is_default, :video_codec, :container, :max_dimension,
                     :crf, :drop_audio, :hardware_accel, :extra_encoder_args, :now, :now)
                """
            ),
            {
                "id": profile_id,
                "name": data["name"],
                "is_default": is_default,
                "video_codec": data.get("video_codec", DEFAULT_VIDEO_CODEC),
                "container": data.get("container", DEFAULT_CONTAINER),
                "max_dimension": data.get("max_dimension"),
                "crf": data.get("crf", DEFAULT_CRF),
                "drop_audio": bool(data.get("drop_audio", True)),
                "hardware_accel": data.get("hardware_accel", DEFAULT_HARDWARE_ACCEL),
                "extra_encoder_args": json.dumps(data["extra_encoder_args"])
                if data.get("extra_encoder_args") is not None
                else None,
                "now": now,
            },
        )
    return get_profile(engine, profile_id)


def update_profile(engine, profile_id: str, data: dict) -> dict | None:
    existing = get_profile(engine, profile_id)
    if existing is None:
        return None

    merged = {**existing, **data}
    now = _now()
    is_default = bool(merged.get("is_default", False))

    with engine.begin() as conn:
        if is_default:
            conn.execute(
                text("UPDATE conversion_profiles SET is_default = 0 WHERE id != :id"),
                {"id": profile_id},
            )
        conn.execute(
            text(
                """
                UPDATE conversion_profiles
                SET name = :name, is_default = :is_default, video_codec = :video_codec,
                    container = :container, max_dimension = :max_dimension, crf = :crf,
                    drop_audio = :drop_audio, hardware_accel = :hardware_accel,
                    extra_encoder_args = :extra_encoder_args,
                    updated_at = :now
                WHERE id = :id
                """
            ),
            {
                "id": profile_id,
                "name": merged["name"],
                "is_default": is_default,
                "video_codec": merged["video_codec"],
                "container": merged["container"],
                "max_dimension": merged["max_dimension"],
                "crf": merged["crf"],
                "drop_audio": bool(merged["drop_audio"]),
                "hardware_accel": merged.get("hardware_accel", DEFAULT_HARDWARE_ACCEL),
                "extra_encoder_args": json.dumps(merged["extra_encoder_args"])
                if merged.get("extra_encoder_args") is not None
                else None,
                "now": now,
            },
        )
    return get_profile(engine, profile_id)


def delete_profile(engine, profile_id: str) -> bool:
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM conversion_profiles WHERE id = :id"), {"id": profile_id}
        )
    return result.rowcount > 0
