"""Global tagging settings singleton (Settings §5, Specification §12.2).

Holds the tagging job's non-vocabulary configuration: how many frames to
sample per video, whether to combine them into one collage image before
sending to the provider (default behavior per Specification §12.2), and how
many top-scoring tags to keep. There is no manual "default provider" choice
here anymore -- the tag job picks the active provider by trying enabled
`app/provider_entries.py` entries in priority order (see `app/jobs/tag.py`).
The tag vocabulary itself lives in `app/tags.py`; provider credentials/
enablement live in `app/provider_entries.py` + `app/secrets_store.py`.
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
                    updated_at = :now
                WHERE id = 1
                """
            ),
            {
                "frame_count": data.get("sample_frame_count", DEFAULT_SAMPLE_FRAME_COUNT),
                "combine": bool(data.get("combine_into_collage", DEFAULT_COMBINE_INTO_COLLAGE)),
                "top_count": data.get("top_tag_count", DEFAULT_TOP_TAG_COUNT),
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
                (id, sample_frame_count, combine_into_collage, top_tag_count, updated_at)
            VALUES (1, :frame_count, :combine, :top_count, :now)
            """
        ),
        {
            "frame_count": DEFAULT_SAMPLE_FRAME_COUNT,
            "combine": DEFAULT_COMBINE_INTO_COLLAGE,
            "top_count": DEFAULT_TOP_TAG_COUNT,
            "now": _now(),
        },
    )
