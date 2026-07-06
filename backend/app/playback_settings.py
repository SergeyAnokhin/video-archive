"""Global playback settings singleton (Specification §11.5; Settings §4).

Holds the preferred playback mode. Both strategies remain available at all
times — this only controls which one the "open playback" action defaults to
(`GET /api/files/{file_id}/playback`); the user can always switch per the
Settings §4 rule that both strategies must stay switchable.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

PLAYBACK_MODES = ("stream", "direct_link")
DEFAULT_MODE = "stream"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    return {"mode": row.mode, "updated_at": row.updated_at}


def get_settings(engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM playback_settings WHERE id = 1")).fetchone()
    return _row_to_dict(row)


def update_settings(engine, data: dict) -> dict:
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE playback_settings SET mode = :mode, updated_at = :now WHERE id = 1"),
            {"mode": data["mode"], "now": now},
        )
    return get_settings(engine)


def seed_default_settings(conn) -> None:
    """Idempotently insert the singleton settings row. Called once from
    `init_db()` right after migration 7 creates the table."""
    conn.execute(
        text(
            "INSERT OR IGNORE INTO playback_settings (id, mode, updated_at) VALUES (1, :mode, :now)"
        ),
        {"mode": DEFAULT_MODE, "now": _now()},
    )
