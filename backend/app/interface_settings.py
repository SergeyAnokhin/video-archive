"""Global interface settings singleton (Settings §9, Design System §2):
UI language and theme preset. Persisted the same way as other settings
groups, closing the pre-Stage-9 known gap where the language preference
lived only in the browser's `localStorage` -- the frontend still keeps a
localStorage/browser-locale fallback for the very first paint before this
endpoint responds, then syncs to whatever this table holds.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

LANGUAGES = ("en", "ru")
THEME_PRESETS = ("strict", "playful", "casino")
DEFAULT_LANGUAGE = "en"
DEFAULT_THEME_PRESET = "strict"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    return {"language": row.language, "theme_preset": row.theme_preset, "updated_at": row.updated_at}


def get_settings(engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM interface_settings WHERE id = 1")).fetchone()
    return _row_to_dict(row)


def update_settings(engine, data: dict) -> dict:
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE interface_settings SET language = :language, theme_preset = :theme_preset, "
                "updated_at = :now WHERE id = 1"
            ),
            {"language": data["language"], "theme_preset": data["theme_preset"], "now": now},
        )
    return get_settings(engine)


def seed_default_settings(conn) -> None:
    """Idempotently insert the singleton settings row. Called once from
    `init_db()` right after migration 9 creates the table."""
    conn.execute(
        text(
            "INSERT OR IGNORE INTO interface_settings (id, language, theme_preset, updated_at) "
            "VALUES (1, :language, :theme_preset, :now)"
        ),
        {"language": DEFAULT_LANGUAGE, "theme_preset": DEFAULT_THEME_PRESET, "now": _now()},
    )
