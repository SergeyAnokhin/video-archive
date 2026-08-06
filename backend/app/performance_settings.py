"""Global performance settings singleton (post-V1, user request): how many
files/variants the `convert` and `preview` jobs process concurrently.

A single file's own ffmpeg encode already uses all available CPU cores on
its own (ffmpeg's default thread count), so the concurrency these settings
control is at the *item* level instead: a single file's independent
frame-extraction calls (`app/preview.py`'s `generate_file_preview()`) or a
single file's independent variant encodes (`app/jobs/convert.py`'s variant
sweep) when there's only one file to work on, and multiple files processed
side by side when a directory-scope job has many. Same singleton pattern as
`preview_settings`/`playback_settings`/`backup_settings`/`interface_settings`.

Two separate counts (user request 2026-07-30): `convert_workers` for the
`convert` job, `parallel_workers` for everything else -- see
`DEFAULT_CONVERT_WORKERS` below for why conversion needed its own.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

DEFAULT_PARALLEL_WORKERS = 4
MIN_PARALLEL_WORKERS = 1
MAX_PARALLEL_WORKERS = 16

# Conversion's own worker count (user request 2026-07-30), separate from the
# shared `parallel_workers` above and defaulting to 1: a convert job started
# with more than one worker reproducibly wedges before its first file on an
# SMB source, while the same job at one worker starts in the same second (see
# `app/jobs/convert.py`'s note at the `worker_count` read). Splitting the
# setting keeps preview at its useful parallelism instead of forcing the whole
# app down to one worker to get conversion running.
DEFAULT_CONVERT_WORKERS = 1

# The job ETA estimate (`frontend/src/utils/eta.ts`) extrapolates from the
# completion rate measured over just the last `eta_window_minutes` of
# progress, not the whole job lifetime -- a job younger than the window
# naturally falls back to its full elapsed time instead, since there's
# nothing older than "now" to trim.
DEFAULT_ETA_WINDOW_MINUTES = 5
MIN_ETA_WINDOW_MINUTES = 1
MAX_ETA_WINDOW_MINUTES = 180


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    return {
        "parallel_workers": row.parallel_workers,
        "convert_workers": row.convert_workers,
        "eta_window_minutes": row.eta_window_minutes,
        "updated_at": row.updated_at,
    }


def get_settings(engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM performance_settings WHERE id = 1")).fetchone()
    return _row_to_dict(row)


def update_settings(engine, data: dict) -> dict:
    # `.get(..., current[...])` rather than strict indexing (same reasoning
    # as `conversion_settings.update_settings`): existing callers that only
    # ever set `parallel_workers` shouldn't need to know about
    # `eta_window_minutes` too.
    current = get_settings(engine)
    parallel_workers = max(
        MIN_PARALLEL_WORKERS,
        min(MAX_PARALLEL_WORKERS, data.get("parallel_workers", current["parallel_workers"])),
    )
    convert_workers = max(
        MIN_PARALLEL_WORKERS,
        min(MAX_PARALLEL_WORKERS, data.get("convert_workers", current["convert_workers"])),
    )
    eta_window_minutes = max(
        MIN_ETA_WINDOW_MINUTES,
        min(MAX_ETA_WINDOW_MINUTES, data.get("eta_window_minutes", current["eta_window_minutes"])),
    )
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE performance_settings SET parallel_workers = :workers, "
                "convert_workers = :convert_workers, "
                "eta_window_minutes = :eta_window, updated_at = :now WHERE id = 1"
            ),
            {
                "workers": parallel_workers,
                "convert_workers": convert_workers,
                "eta_window": eta_window_minutes,
                "now": now,
            },
        )
    return get_settings(engine)


def seed_default_settings(conn) -> None:
    """Idempotently insert the singleton settings row. Called once from
    `init_db()` right after migration 16 creates the table."""
    conn.execute(
        text(
            "INSERT OR IGNORE INTO performance_settings "
            "(id, parallel_workers, convert_workers, eta_window_minutes, updated_at) "
            "VALUES (1, :workers, :convert_workers, :eta_window, :now)"
        ),
        {
            "workers": DEFAULT_PARALLEL_WORKERS,
            "convert_workers": DEFAULT_CONVERT_WORKERS,
            "eta_window": DEFAULT_ETA_WINDOW_MINUTES,
            "now": _now(),
        },
    )
