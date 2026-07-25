"""Global log-rotation settings singleton (chat request): the backend's
rotating file handler (see `app/logging_config.py`) used to rotate on a
fixed 5-minute timer with one backup, both hardcoded. This lets the user
configure the size threshold that triggers a new file and how many rotated
backups to keep, mirroring `resource_monitor_settings.py`'s singleton
pattern. `logging_config.apply_rotation_settings()` mutates the live
handler in place so a change here takes effect immediately, no restart.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

DEFAULT_MAX_BYTES = 5 * 1024 * 1024
MIN_MAX_BYTES = 1 * 1024 * 1024
MAX_MAX_BYTES = 100 * 1024 * 1024

DEFAULT_BACKUP_COUNT = 5
# 0 would never rotate under stdlib RotatingFileHandler semantics (rollover
# only renames existing backups when backupCount > 0) -- 1 is the floor.
MIN_BACKUP_COUNT = 1
MAX_BACKUP_COUNT = 20


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    return {
        "max_bytes": row.max_bytes,
        "backup_count": row.backup_count,
        "updated_at": row.updated_at,
    }


def get_settings(engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM log_rotation_settings WHERE id = 1")).fetchone()
    return _row_to_dict(row)


def update_settings(engine, data: dict) -> dict:
    max_bytes = max(MIN_MAX_BYTES, min(MAX_MAX_BYTES, data["max_bytes"]))
    backup_count = max(MIN_BACKUP_COUNT, min(MAX_BACKUP_COUNT, data["backup_count"]))
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE log_rotation_settings SET max_bytes = :max_bytes, "
                "backup_count = :backup_count, updated_at = :now WHERE id = 1"
            ),
            {"max_bytes": max_bytes, "backup_count": backup_count, "now": now},
        )
    return get_settings(engine)


def seed_default_settings(conn) -> None:
    """Idempotently insert the singleton settings row. Called once from
    `init_db()` right after migration 45 creates the table."""
    conn.execute(
        text(
            "INSERT OR IGNORE INTO log_rotation_settings (id, max_bytes, backup_count, updated_at) "
            "VALUES (1, :max_bytes, :backup_count, :now)"
        ),
        {"max_bytes": DEFAULT_MAX_BYTES, "backup_count": DEFAULT_BACKUP_COUNT, "now": _now()},
    )
