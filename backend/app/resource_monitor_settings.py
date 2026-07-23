"""Global resource-usage monitoring settings singleton (chat request):
whether the backend periodically samples its own CPU/memory (see
`app/resource_monitor.py`) and how often. Added to diagnose Kubernetes OOM
restarts that were silently killing in-progress jobs -- the sampler writes
to its own rotating log file (`logs/resource_usage.log`) so the trend
leading up to a restart is visible without cluster disk access. Same
singleton pattern as `performance_settings`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

DEFAULT_ENABLED = True
DEFAULT_INTERVAL_SECONDS = 30
MIN_INTERVAL_SECONDS = 1
MAX_INTERVAL_SECONDS = 3600


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    return {
        "enabled": bool(row.enabled),
        "interval_seconds": row.interval_seconds,
        "updated_at": row.updated_at,
    }


def get_settings(engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM resource_monitor_settings WHERE id = 1")).fetchone()
    return _row_to_dict(row)


def update_settings(engine, data: dict) -> dict:
    interval_seconds = max(MIN_INTERVAL_SECONDS, min(MAX_INTERVAL_SECONDS, data["interval_seconds"]))
    enabled = bool(data["enabled"])
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE resource_monitor_settings SET enabled = :enabled, "
                "interval_seconds = :interval, updated_at = :now WHERE id = 1"
            ),
            {"enabled": int(enabled), "interval": interval_seconds, "now": now},
        )
    return get_settings(engine)


def seed_default_settings(conn) -> None:
    """Idempotently insert the singleton settings row. Called once from
    `init_db()` right after migration 43 creates the table."""
    conn.execute(
        text(
            "INSERT OR IGNORE INTO resource_monitor_settings (id, enabled, interval_seconds, updated_at) "
            "VALUES (1, :enabled, :interval, :now)"
        ),
        {"enabled": int(DEFAULT_ENABLED), "interval": DEFAULT_INTERVAL_SECONDS, "now": _now()},
    )
