"""`backup` job execution (Job Model, Specification §19): wraps
`app/backup.py`'s `create_backup()` in a job since it writes to the source's
technical folder and, for SMB, involves a network round-trip. A single,
fast, whole-source action with no per-file notion, so it never creates job
items (same reasoning as `optimize_db`)."""

from __future__ import annotations

from sqlalchemy import text

from app import backup
from app.jobs import service
from app.sources import get_source_access


def run_backup_job(engine, job: dict) -> tuple[str, str]:
    params = job["parameters"] or {}
    include_secrets = bool(params.get("include_secrets", False))

    with engine.connect() as conn:
        source_row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()
    if source_row is None:
        raise RuntimeError("No active source is configured.")

    access = get_source_access(source_row)
    result = backup.create_backup(engine, access, source_row, include_secrets=include_secrets)

    message = f"Backup created: {result['filename']}"
    if result.get("removed_old_backups"):
        message += f" ({result['removed_old_backups']} old backup(s) removed by retention)."
    service.log_event(engine, job["id"], None, "info", "job_item_completed", message)
    return "completed", message
