"""Global conversion settings singleton (user report): the minimum
size-reduction percentage a converted output must achieve to replace the
source. A production/test-mode replace whose output doesn't shrink the
source by at least this much is skipped instead -- the original is kept
untouched -- rather than landing a conversion that wasn't actually worth it
(most consequential for a directory-scope batch job converting many files
unattended). Read once at job launch by `app/jobs/convert.py`, same
singleton convention as `performance_settings`/`playback_settings`/
`backup_settings`/`interface_settings`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

DEFAULT_MIN_SIZE_REDUCTION_PERCENT = 20
MIN_MIN_SIZE_REDUCTION_PERCENT = 0
MAX_MIN_SIZE_REDUCTION_PERCENT = 90


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    return {"min_size_reduction_percent": row.min_size_reduction_percent, "updated_at": row.updated_at}


def get_settings(engine) -> dict:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM conversion_settings WHERE id = 1")).fetchone()
    return _row_to_dict(row)


def update_settings(engine, data: dict) -> dict:
    value = max(
        MIN_MIN_SIZE_REDUCTION_PERCENT,
        min(MAX_MIN_SIZE_REDUCTION_PERCENT, data["min_size_reduction_percent"]),
    )
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE conversion_settings SET min_size_reduction_percent = :value, updated_at = :now "
                "WHERE id = 1"
            ),
            {"value": value, "now": now},
        )
    return get_settings(engine)


def seed_default_settings(conn) -> None:
    """Idempotently insert the singleton settings row. Called once from
    `init_db()` right after the migration that creates the table."""
    conn.execute(
        text(
            "INSERT OR IGNORE INTO conversion_settings (id, min_size_reduction_percent, updated_at) "
            "VALUES (1, :value, :now)"
        ),
        {"value": DEFAULT_MIN_SIZE_REDUCTION_PERCENT, "now": _now()},
    )
