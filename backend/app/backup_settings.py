"""Global backup settings singleton (Settings §7, Specification §19).

Holds only the retention count: how many backup packages to keep in
`.video-archive/backups/` before the oldest are removed after a successful
new backup (`app/backup.py`'s `_enforce_retention()`). The backup destination
itself is fixed to the source's technical folder for V1, so there is no
"destination" setting to store.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

DEFAULT_RETENTION_COUNT = 5


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    return {"retention_count": row.retention_count, "updated_at": row.updated_at}


def get_settings(engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM backup_settings WHERE id = 1")).fetchone()
    return _row_to_dict(row)


def update_settings(engine, data: dict) -> dict:
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE backup_settings SET retention_count = :count, updated_at = :now WHERE id = 1"),
            {"count": data.get("retention_count", DEFAULT_RETENTION_COUNT), "now": now},
        )
    return get_settings(engine)


def seed_default_settings(conn) -> None:
    """Idempotently insert the singleton settings row. Called once from
    `init_db()` right after migration 8 creates the table."""
    conn.execute(
        text(
            "INSERT OR IGNORE INTO backup_settings (id, retention_count, updated_at) VALUES (1, :count, :now)"
        ),
        {"count": DEFAULT_RETENTION_COUNT, "now": _now()},
    )
