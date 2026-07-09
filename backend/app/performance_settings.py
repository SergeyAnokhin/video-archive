"""Global performance settings singleton (post-V1, user request): how many
files/variants the `convert` and `preview` jobs process concurrently.

A single file's own ffmpeg encode already uses all available CPU cores on
its own (ffmpeg's default thread count), so the concurrency this setting
controls is at the *item* level instead: a single file's independent
frame-extraction calls (`app/preview.py`'s `generate_file_preview()`) or a
single file's independent variant encodes (`app/jobs/convert.py`'s variant
sweep) when there's only one file to work on, and multiple files processed
side by side when a directory-scope job has many. Same singleton pattern as
`preview_settings`/`playback_settings`/`backup_settings`/`interface_settings`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

DEFAULT_PARALLEL_WORKERS = 4
MIN_PARALLEL_WORKERS = 1
MAX_PARALLEL_WORKERS = 16


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    return {"parallel_workers": row.parallel_workers, "updated_at": row.updated_at}


def get_settings(engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM performance_settings WHERE id = 1")).fetchone()
    return _row_to_dict(row)


def update_settings(engine, data: dict) -> dict:
    parallel_workers = max(MIN_PARALLEL_WORKERS, min(MAX_PARALLEL_WORKERS, data["parallel_workers"]))
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE performance_settings SET parallel_workers = :workers, updated_at = :now WHERE id = 1"),
            {"workers": parallel_workers, "now": now},
        )
    return get_settings(engine)


def seed_default_settings(conn) -> None:
    """Idempotently insert the singleton settings row. Called once from
    `init_db()` right after migration 16 creates the table."""
    conn.execute(
        text(
            "INSERT OR IGNORE INTO performance_settings (id, parallel_workers, updated_at) "
            "VALUES (1, :workers, :now)"
        ),
        {"workers": DEFAULT_PARALLEL_WORKERS, "now": _now()},
    )
