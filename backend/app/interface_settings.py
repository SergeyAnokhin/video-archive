"""Global interface settings singleton (Settings §9, Design System §2):
UI language, theme preset, and preview-stylization profiles. Persisted the
same way as other settings groups, closing the pre-Stage-9 known gap where
the language preference lived only in the browser's `localStorage` -- the
frontend still keeps a localStorage/browser-locale fallback for the very
first paint before this endpoint responds, then syncs to whatever this
table holds.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

LANGUAGES = ("en", "ru")
THEME_PRESETS = ("strict", "playful", "casino", "neon", "toxic", "cyber", "vivid", "mono")
DEFAULT_LANGUAGE = "en"
DEFAULT_THEME_PRESET = "strict"

# Two named preview-stylization profiles (post-V1, user request): the
# top-bar "hide previews" toggle switches between these instead of
# replacing the thumbnail with a folder/film icon. Field ranges match the
# CSS `filter` functions they drive (see frontend `previewFilterCss()`):
# saturate/brightness/contrast/sepia are percentages, blur is px, hue_rotate
# is degrees. Profile A defaults to a no-op (original colors); profile B
# defaults to heavily blurred + desaturated, standing in for the old
# "hidden" state, but every field is user-editable.
PROFILE_FIELDS = ("saturation", "blur", "brightness", "contrast", "sepia", "hue_rotate")
PROFILE_RANGES = {
    "saturation": (0, 100),
    "blur": (0, 20),
    "brightness": (50, 150),
    "contrast": (50, 150),
    "sepia": (0, 100),
    "hue_rotate": (0, 360),
}
DEFAULT_PROFILE_A = {
    "saturation": 100,
    "blur": 0,
    "brightness": 100,
    "contrast": 100,
    "sepia": 0,
    "hue_rotate": 0,
}
DEFAULT_PROFILE_B = {
    "saturation": 20,
    "blur": 16,
    "brightness": 100,
    "contrast": 100,
    "sepia": 0,
    "hue_rotate": 0,
}


def _column(profile: str, field: str) -> str:
    return f"profile_{profile}_{field}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    data = {"language": row.language, "theme_preset": row.theme_preset, "updated_at": row.updated_at}
    for profile in ("a", "b"):
        for field in PROFILE_FIELDS:
            column = _column(profile, field)
            data[column] = getattr(row, column)
    return data


def get_settings(engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM interface_settings WHERE id = 1")).fetchone()
    return _row_to_dict(row)


def update_settings(engine, data: dict) -> dict:
    now = _now()
    profile_columns = [_column(profile, field) for profile in ("a", "b") for field in PROFILE_FIELDS]
    assignments = ", ".join(f"{column} = :{column}" for column in profile_columns)
    params = {"language": data["language"], "theme_preset": data["theme_preset"], "now": now}
    for column in profile_columns:
        params[column] = data[column]
    with engine.begin() as conn:
        conn.execute(
            text(
                f"UPDATE interface_settings SET language = :language, theme_preset = :theme_preset, "
                f"{assignments}, updated_at = :now WHERE id = 1"
            ),
            params,
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
