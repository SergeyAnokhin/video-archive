"""`cleanup` job execution (Specification §16 "stale-record cleanup").

Unlike `rescan` (which re-discovers the whole subtree and refreshes
metadata), cleanup never touches existing rows or discovers new files: it
only checks whether each already-known file/directory still exists on the
source and removes the row if it doesn't. Directories are checked
deepest-first so a stale parent doesn't shadow which of its children are
also gone.
"""

from __future__ import annotations

from sqlalchemy import text

from app.jobs import service
from app.sources import get_source_access


def run_cleanup_job(engine, job: dict) -> tuple[str, str]:
    with engine.connect() as conn:
        source_row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()
    if source_row is None:
        raise RuntimeError("No active source is configured.")

    source_id = source_row.id
    access = get_source_access(source_row)

    with engine.connect() as conn:
        file_rows = conn.execute(
            text("SELECT id, relative_path FROM files WHERE source_id = :sid ORDER BY relative_path"),
            {"sid": source_id},
        ).all()
        dir_rows = conn.execute(
            text(
                "SELECT id, relative_path FROM directories WHERE source_id = :sid "
                "ORDER BY relative_path DESC"
            ),
            {"sid": source_id},
        ).all()

    removed_files = 0
    for row in file_rows:
        if service.is_cancel_requested(job["id"]):
            message = f"Cancelled after removing {removed_files} stale file record(s)."
            service.log_event(engine, job["id"], None, "info", "job_cancel_honored", message)
            return "cancelled", message

        if access.exists(row.relative_path):
            continue
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM file_tags WHERE file_id = :id"), {"id": row.id})
            conn.execute(text("DELETE FROM file_similarity_signatures WHERE file_id = :id"), {"id": row.id})
            conn.execute(text("DELETE FROM files WHERE id = :id"), {"id": row.id})
        service.log_event(
            engine, job["id"], None, "info", "job_item_completed",
            f"Removed stale file record: {row.relative_path}",
        )
        removed_files += 1

    removed_dirs = 0
    for row in dir_rows:
        if service.is_cancel_requested(job["id"]):
            message = (
                f"Cancelled after removing {removed_files} stale file(s) and {removed_dirs} stale folder(s)."
            )
            service.log_event(engine, job["id"], None, "info", "job_cancel_honored", message)
            return "cancelled", message

        if not row.relative_path or access.is_dir(row.relative_path):
            continue
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM directories WHERE id = :id"), {"id": row.id})
        service.log_event(
            engine, job["id"], None, "info", "job_item_completed",
            f"Removed stale folder record: {row.relative_path}",
        )
        removed_dirs += 1

    message = f"Removed {removed_files} stale file record(s) and {removed_dirs} stale folder record(s)."
    return "completed", message
