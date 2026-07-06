"""`restore` job execution (Job Model, Specification §19, §5.2): wraps
`app/backup.py`'s `restore_backup()`, which validates the package and
replaces the active source's library metadata (and merges the global
settings tables) from it in one transaction. No per-file job items, same as
`backup`/`optimize_db` — this is a single atomic restore, not a bulk file
workflow."""

from __future__ import annotations

from sqlalchemy import text

from app import backup
from app.jobs import service
from app.sources import get_source_access


def run_restore_job(engine, job: dict) -> tuple[str, str]:
    params = job["parameters"] or {}
    backup_id = params.get("backup_id")
    if not backup_id:
        raise RuntimeError("No backup id given to restore.")

    with engine.connect() as conn:
        source_row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()
    if source_row is None:
        raise RuntimeError("No active source is configured.")

    access = get_source_access(source_row)
    try:
        result = backup.restore_backup(engine, access, source_row, backup_id)
    except backup.RestoreError as exc:
        service.log_event(engine, job["id"], None, "error", "job_item_failed", str(exc))
        return "failed", str(exc)

    counts = result["counts"]
    message = (
        f"Restored {counts.get('files', 0)} file record(s) and {counts.get('directories', 0)} "
        f"folder record(s) from backup {backup_id}."
    )
    service.log_event(engine, job["id"], None, "info", "job_item_completed", message)
    return "completed", message
