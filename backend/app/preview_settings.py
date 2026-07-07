"""Global preview settings singleton (Specification §9.2, §10; Settings §3).

Holds the two preview settings that are explicitly *not* part of a layout
preset (Data Model §5 notes): the overall collage aspect ratio (independent
of grid dimensions) and the folder-preview frame count. Everything else
configurable on the Preview Settings page (grid, enlarged tiles, timeline
flow, identity diversity) lives on the selected `preview_layout_presets` row
instead (see `app/preview_layouts.py`).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

ASPECT_RATIOS = ("standard", "phone-portrait", "phone-landscape", "ultra-wide", "custom")
DEFAULT_FOLDER_PREVIEW_FRAME_COUNT = 4
DEFAULT_ASPECT_RATIO = "phone-landscape"
# Animated-GIF preview size/quality (user request): GIFs are only ever shown
# small (grid/list-view hover thumbnails), so they default well below the
# full collage width/color depth to stay fast to load.
DEFAULT_GIF_MAX_WIDTH = 640
DEFAULT_GIF_COLORS = 64

# Aspect ratio (width / height) for the fixed presets; "custom" uses the
# stored custom width/height instead (Specification §9.2).
# "phone-landscape" (19.5:9, wide/short) is the default, user request: it
# fills a mobile card's width without letterboxing, unlike the 4:3 "standard"
# or 21:9 "ultra-wide" values, which are close but not this specific ratio.
ASPECT_RATIO_VALUES = {
    "standard": 4 / 3,
    "phone-portrait": 9 / 19.5,
    "phone-landscape": 19.5 / 9,
    "ultra-wide": 21 / 9,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    return {
        "aspect_ratio": row.aspect_ratio,
        "aspect_ratio_custom_width": row.aspect_ratio_custom_width,
        "aspect_ratio_custom_height": row.aspect_ratio_custom_height,
        "folder_preview_frame_count": row.folder_preview_frame_count,
        "gif_max_width": row.gif_max_width,
        "gif_colors": row.gif_colors,
        "updated_at": row.updated_at,
    }


def get_settings(engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM preview_settings WHERE id = 1")).fetchone()
    return _row_to_dict(row)


def update_settings(engine, data: dict) -> dict:
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE preview_settings
                SET aspect_ratio = :aspect_ratio,
                    aspect_ratio_custom_width = :custom_width,
                    aspect_ratio_custom_height = :custom_height,
                    folder_preview_frame_count = :frame_count,
                    gif_max_width = :gif_max_width,
                    gif_colors = :gif_colors,
                    updated_at = :now
                WHERE id = 1
                """
            ),
            {
                "aspect_ratio": data["aspect_ratio"],
                "custom_width": data.get("aspect_ratio_custom_width"),
                "custom_height": data.get("aspect_ratio_custom_height"),
                "frame_count": data.get("folder_preview_frame_count", DEFAULT_FOLDER_PREVIEW_FRAME_COUNT),
                "gif_max_width": data.get("gif_max_width", DEFAULT_GIF_MAX_WIDTH),
                "gif_colors": data.get("gif_colors", DEFAULT_GIF_COLORS),
                "now": now,
            },
        )
    return get_settings(engine)


def effective_aspect_ratio(settings: dict) -> float:
    """Resolve the configured aspect ratio setting to a numeric width/height
    ratio for collage canvas sizing."""
    if settings["aspect_ratio"] == "custom":
        width = settings.get("aspect_ratio_custom_width") or 1
        height = settings.get("aspect_ratio_custom_height") or 1
        return width / height
    return ASPECT_RATIO_VALUES.get(settings["aspect_ratio"], ASPECT_RATIO_VALUES["standard"])


def seed_default_settings(conn) -> None:
    """Idempotently insert the singleton settings row. Called once from
    `init_db()` right after migration 5 creates the table."""
    conn.execute(
        text(
            """
            INSERT OR IGNORE INTO preview_settings
                (id, aspect_ratio, aspect_ratio_custom_width, aspect_ratio_custom_height,
                 folder_preview_frame_count, updated_at)
            VALUES (1, :aspect_ratio, NULL, NULL, :frame_count, :now)
            """
        ),
        {"aspect_ratio": DEFAULT_ASPECT_RATIO, "frame_count": DEFAULT_FOLDER_PREVIEW_FRAME_COUNT, "now": _now()},
    )
