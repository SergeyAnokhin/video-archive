"""Global tagging settings singleton (Settings §5, Specification §12.2).

Holds the tagging job's non-vocabulary configuration: how many frames to
sample per video, whether to combine them into one collage image before
sending to the provider (default behavior per Specification §12.2), how many
top-scoring tags to keep, and a default provider/model shortcut used when a
tagging job doesn't override it. The tag vocabulary itself lives in
`app/tags.py`; provider credentials/enablement live in
`app/provider_configs.py` + `app/secrets_store.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

DEFAULT_SAMPLE_FRAME_COUNT = 9
DEFAULT_COMBINE_INTO_COLLAGE = True
DEFAULT_TOP_TAG_COUNT = 10


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    return {
        "sample_frame_count": row.sample_frame_count,
        "combine_into_collage": bool(row.combine_into_collage),
        "top_tag_count": row.top_tag_count,
        "default_provider": row.default_provider,
        "default_vision_model": row.default_vision_model,
        "updated_at": row.updated_at,
    }


def get_settings(engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM tagging_settings WHERE id = 1")).fetchone()
    return _row_to_dict(row)


def update_settings(engine, data: dict) -> dict:
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE tagging_settings
                SET sample_frame_count = :frame_count,
                    combine_into_collage = :combine,
                    top_tag_count = :top_count,
                    default_provider = :provider,
                    default_vision_model = :model,
                    updated_at = :now
                WHERE id = 1
                """
            ),
            {
                "frame_count": data.get("sample_frame_count", DEFAULT_SAMPLE_FRAME_COUNT),
                "combine": bool(data.get("combine_into_collage", DEFAULT_COMBINE_INTO_COLLAGE)),
                "top_count": data.get("top_tag_count", DEFAULT_TOP_TAG_COUNT),
                "provider": data.get("default_provider"),
                "model": data.get("default_vision_model"),
                "now": now,
            },
        )
    return get_settings(engine)


def seed_default_settings(conn) -> None:
    """Idempotently insert the singleton settings row. Called once from
    `init_db()` right after migration 6 creates the table."""
    conn.execute(
        text(
            """
            INSERT OR IGNORE INTO tagging_settings
                (id, sample_frame_count, combine_into_collage, top_tag_count,
                 default_provider, default_vision_model, updated_at)
            VALUES (1, :frame_count, :combine, :top_count, NULL, NULL, :now)
            """
        ),
        {
            "frame_count": DEFAULT_SAMPLE_FRAME_COUNT,
            "combine": DEFAULT_COMBINE_INTO_COLLAGE,
            "top_count": DEFAULT_TOP_TAG_COUNT,
            "now": _now(),
        },
    )
