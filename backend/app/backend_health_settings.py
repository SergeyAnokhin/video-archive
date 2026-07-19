"""Global backend-health-indicator timeout settings singleton (chat request
2026-07-19 follow-up): how long the top-bar status dot waits for `/api/health`
before turning amber ("slow" -- the backend might just be busy, e.g. mid
conversion) and how much longer it then waits on retry before giving up and
turning red ("offline"). Same singleton pattern as
performance_settings/conversion_settings; consumed by
`useBackendHealth.ts` via `GET /api/backend-health-settings`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

DEFAULT_SLOW_TIMEOUT_SECONDS = 5
MIN_SLOW_TIMEOUT_SECONDS = 1
MAX_SLOW_TIMEOUT_SECONDS = 30

DEFAULT_OFFLINE_TIMEOUT_SECONDS = 10
MIN_OFFLINE_TIMEOUT_SECONDS = 1
MAX_OFFLINE_TIMEOUT_SECONDS = 60


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    return {
        "slow_timeout_seconds": row.slow_timeout_seconds,
        "offline_timeout_seconds": row.offline_timeout_seconds,
        "updated_at": row.updated_at,
    }


def get_settings(engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM backend_health_settings WHERE id = 1")).fetchone()
    return _row_to_dict(row)


def update_settings(engine, data: dict) -> dict:
    slow = max(MIN_SLOW_TIMEOUT_SECONDS, min(MAX_SLOW_TIMEOUT_SECONDS, data["slow_timeout_seconds"]))
    offline = max(MIN_OFFLINE_TIMEOUT_SECONDS, min(MAX_OFFLINE_TIMEOUT_SECONDS, data["offline_timeout_seconds"]))
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE backend_health_settings SET slow_timeout_seconds = :slow, "
                "offline_timeout_seconds = :offline, updated_at = :now WHERE id = 1"
            ),
            {"slow": slow, "offline": offline, "now": now},
        )
    return get_settings(engine)


def seed_default_settings(conn) -> None:
    """Idempotently insert the singleton settings row. Called once from
    `init_db()` right after migration 34 creates the table."""
    conn.execute(
        text(
            "INSERT OR IGNORE INTO backend_health_settings "
            "(id, slow_timeout_seconds, offline_timeout_seconds, updated_at) "
            "VALUES (1, :slow, :offline, :now)"
        ),
        {"slow": DEFAULT_SLOW_TIMEOUT_SECONDS, "offline": DEFAULT_OFFLINE_TIMEOUT_SECONDS, "now": _now()},
    )
