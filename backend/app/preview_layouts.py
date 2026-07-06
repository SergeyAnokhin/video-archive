"""Preview layout preset CRUD and grid geometry (Data Model §5, Specification
§9.2, §10). A layout preset only stores enlarged-tile placements; the small
tiles that fill the rest of the grid are always derived by
`compute_layout_tiles()` so the grid stays fully covered by construction
(Specification §9.2 "the grid must always remain completely filled").

Built-in presets ship with the app (`is_builtin = 1`) and are seeded once from
`seed_builtin_presets()`, called by `app/db.py`'s `init_db()`; they are not
editable or deletable (Data Model §5).
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

VALID_SPANS = (2, 3)
VALID_TIMELINE_FLOWS = ("row", "column", "shuffle")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class LayoutValidationError(Exception):
    """Raised when an enlarged-tile layout doesn't fit the grid without
    overlaps or out-of-bounds placements."""


class PresetProtectedError(Exception):
    """Raised when attempting to edit or delete a built-in preset."""


# --- grid geometry ------------------------------------------------------


def compute_layout_tiles(grid_rows: int, grid_cols: int, enlarged: list[dict]) -> list[dict]:
    """Return every tile covering the grid: the given enlarged tiles plus an
    auto-filled small (1x1) tile for each remaining cell, in row-major order.
    Raises `LayoutValidationError` if an enlarged tile is out of bounds, has
    an invalid span, or overlaps another.
    """
    occupied = [[False] * grid_cols for _ in range(grid_rows)]
    tiles: list[dict] = []

    for tile in enlarged:
        row, col, span = tile["row"], tile["col"], tile["span"]
        if span not in VALID_SPANS:
            raise LayoutValidationError(f"Invalid enlarged tile span: {span} (must be 2 or 3).")
        if row < 0 or col < 0 or row + span > grid_rows or col + span > grid_cols:
            raise LayoutValidationError(
                f"Enlarged tile at ({row}, {col}) with span {span} does not fit a {grid_rows}x{grid_cols} grid."
            )
        for r in range(row, row + span):
            for c in range(col, col + span):
                if occupied[r][c]:
                    raise LayoutValidationError(f"Enlarged tiles overlap at cell ({r}, {c}).")
                occupied[r][c] = True
        tiles.append({"row": row, "col": col, "span": span, "type": "enlarged"})

    for r in range(grid_rows):
        for c in range(grid_cols):
            if not occupied[r][c]:
                tiles.append({"row": r, "col": c, "span": 1, "type": "small"})

    return tiles


def frame_count_for_layout(grid_rows: int, grid_cols: int, enlarged: list[dict]) -> int:
    """Total sampled frames needed: one per tile, small or enlarged
    (Specification §9.2)."""
    tiles = compute_layout_tiles(grid_rows, grid_cols, enlarged)
    return len(tiles)


# --- row <-> dict mapping ------------------------------------------------


def _row_to_dict(row) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "grid_rows": row.grid_rows,
        "grid_cols": row.grid_cols,
        "timeline_flow": row.timeline_flow,
        "identity_diversity_enabled": bool(row.identity_diversity_enabled),
        "layout_definition": json.loads(row.layout_definition),
        "is_builtin": bool(row.is_builtin),
        "is_default": bool(row.is_default),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_presets(engine) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM preview_layout_presets ORDER BY is_builtin DESC, name COLLATE NOCASE")
        ).all()
    return [_row_to_dict(row) for row in rows]


def get_preset(engine, preset_id: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM preview_layout_presets WHERE id = :id"), {"id": preset_id}
        ).fetchone()
    return _row_to_dict(row) if row else None


def create_preset(engine, data: dict) -> dict:
    compute_layout_tiles(data["grid_rows"], data["grid_cols"], data["layout_definition"])

    preset_id = str(uuid.uuid4())
    now = _now()
    is_default = bool(data.get("is_default", False))

    with engine.begin() as conn:
        if is_default:
            conn.execute(text("UPDATE preview_layout_presets SET is_default = 0"))
        conn.execute(
            text(
                """
                INSERT INTO preview_layout_presets
                    (id, name, grid_rows, grid_cols, timeline_flow, identity_diversity_enabled,
                     layout_definition, is_builtin, is_default, created_at, updated_at)
                VALUES
                    (:id, :name, :grid_rows, :grid_cols, :timeline_flow, :identity_diversity,
                     :layout_definition, 0, :is_default, :now, :now)
                """
            ),
            {
                "id": preset_id,
                "name": data["name"],
                "grid_rows": data["grid_rows"],
                "grid_cols": data["grid_cols"],
                "timeline_flow": data.get("timeline_flow", "row"),
                "identity_diversity": bool(data.get("identity_diversity_enabled", True)),
                "layout_definition": json.dumps(data["layout_definition"]),
                "is_default": is_default,
                "now": now,
            },
        )
    return get_preset(engine, preset_id)


def update_preset(engine, preset_id: str, data: dict) -> dict | None:
    existing = get_preset(engine, preset_id)
    if existing is None:
        return None
    if existing["is_builtin"]:
        raise PresetProtectedError("Built-in presets cannot be edited.")

    merged = {**existing, **data}
    compute_layout_tiles(merged["grid_rows"], merged["grid_cols"], merged["layout_definition"])

    now = _now()
    is_default = bool(merged.get("is_default", False))

    with engine.begin() as conn:
        if is_default:
            conn.execute(
                text("UPDATE preview_layout_presets SET is_default = 0 WHERE id != :id"),
                {"id": preset_id},
            )
        conn.execute(
            text(
                """
                UPDATE preview_layout_presets
                SET name = :name, grid_rows = :grid_rows, grid_cols = :grid_cols,
                    timeline_flow = :timeline_flow, identity_diversity_enabled = :identity_diversity,
                    layout_definition = :layout_definition, is_default = :is_default, updated_at = :now
                WHERE id = :id
                """
            ),
            {
                "id": preset_id,
                "name": merged["name"],
                "grid_rows": merged["grid_rows"],
                "grid_cols": merged["grid_cols"],
                "timeline_flow": merged["timeline_flow"],
                "identity_diversity": bool(merged["identity_diversity_enabled"]),
                "layout_definition": json.dumps(merged["layout_definition"]),
                "is_default": is_default,
                "now": now,
            },
        )
    return get_preset(engine, preset_id)


def delete_preset(engine, preset_id: str) -> bool:
    existing = get_preset(engine, preset_id)
    if existing is None:
        return False
    if existing["is_builtin"]:
        raise PresetProtectedError("Built-in presets cannot be deleted.")

    with engine.begin() as conn:
        result = conn.execute(text("DELETE FROM preview_layout_presets WHERE id = :id"), {"id": preset_id})
    return result.rowcount > 0


def get_default_preset(engine) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM preview_layout_presets WHERE is_default = 1 LIMIT 1")
        ).fetchone()
        if row is None:
            row = conn.execute(text("SELECT * FROM preview_layout_presets ORDER BY created_at LIMIT 1")).fetchone()
    return _row_to_dict(row) if row else None


# --- built-in preset gallery ---------------------------------------------

# Fixed ids so re-running the seed (idempotent, INSERT OR IGNORE) never
# duplicates rows across restarts. Arrangement mirrors the reference
# screenshot's gallery: large tile at a corner, along an edge, at two
# corners, centered, and a plain grid with no enlarged tiles.
_BUILTIN_PRESETS = [
    {
        "id": "10000000-0000-0000-0000-000000000001",
        "name": "Corner Large",
        "grid_rows": 4,
        "grid_cols": 4,
        "layout_definition": [{"row": 0, "col": 0, "span": 2}],
        "is_default": True,
    },
    {
        "id": "10000000-0000-0000-0000-000000000002",
        "name": "Edge Large",
        "grid_rows": 4,
        "grid_cols": 4,
        "layout_definition": [{"row": 0, "col": 1, "span": 2}],
        "is_default": False,
    },
    {
        "id": "10000000-0000-0000-0000-000000000003",
        "name": "Two Corners",
        "grid_rows": 4,
        "grid_cols": 4,
        "layout_definition": [{"row": 0, "col": 0, "span": 2}, {"row": 2, "col": 2, "span": 2}],
        "is_default": False,
    },
    {
        "id": "10000000-0000-0000-0000-000000000004",
        "name": "Centered Large",
        "grid_rows": 5,
        "grid_cols": 5,
        "layout_definition": [{"row": 1, "col": 1, "span": 3}],
        "is_default": False,
    },
    {
        "id": "10000000-0000-0000-0000-000000000005",
        "name": "Classic Grid",
        "grid_rows": 4,
        "grid_cols": 4,
        "layout_definition": [],
        "is_default": False,
    },
]


def seed_builtin_presets(conn) -> None:
    """Idempotently insert the built-in preset gallery. Called once from
    `init_db()` right after migration 5 creates the table; safe to call again
    (existing ids are left untouched)."""
    now = _now()
    for preset in _BUILTIN_PRESETS:
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO preview_layout_presets
                    (id, name, grid_rows, grid_cols, timeline_flow, identity_diversity_enabled,
                     layout_definition, is_builtin, is_default, created_at, updated_at)
                VALUES
                    (:id, :name, :grid_rows, :grid_cols, 'row', 1,
                     :layout_definition, 1, :is_default, :now, :now)
                """
            ),
            {
                "id": preset["id"],
                "name": preset["name"],
                "grid_rows": preset["grid_rows"],
                "grid_cols": preset["grid_cols"],
                "layout_definition": json.dumps(preset["layout_definition"]),
                "is_default": preset["is_default"],
                "now": now,
            },
        )
