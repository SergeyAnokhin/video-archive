"""Shared "switch the active source" flow (user request): replaces the old
destructive single-slot model (every `PUT /source` wiped *all* `sources` rows
and every source-scoped table, with no way back) with support for several
saved sources that can be switched between without losing each one's own
data.

Local metadata (`directories`/`files`/`file_tags`/...) only ever holds the
currently active source's rows -- switching away from a source first backs
it up (`app/backup.py`, written to that source's own `.video-archive/
backups/`) before wiping, and switching to a source auto-restores its own
scoped data from its most recent backup if one exists there. Global settings
tables are never touched by this flow (`include_global=False`), since the
user wants app-wide settings shared across every source, not overwritten by
whatever an old backup happened to contain.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from app import backup
from app.jobs import service
from app.sources import get_source_access

# Wiped unconditionally on every switch, same as the original `PUT /source`
# handler. `jobs`/`job_items`/`app_events` have no `source_id` column (job
# history is short-lived 24h-retention data, never backed up -- see
# `app/backup.py`), so they are simply cleared rather than scoped.
_SCOPED_DELETE_STATEMENTS = (
    "DELETE FROM file_tags",
    "DELETE FROM file_similarity_signatures",
    "DELETE FROM app_events",
    "DELETE FROM job_items",
    "DELETE FROM jobs",
    "DELETE FROM files",
    "DELETE FROM directories",
)


def switch_active_source(engine, new_row) -> dict:
    """Activate `new_row` (an existing `sources` table row). Returns
    `{"row": <refreshed row>, "detected_backups": [...], "auto_restored": {...} | None}`."""
    with engine.connect() as conn:
        old_row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()

    already_active = old_row is not None and old_row.id == new_row.id
    if not already_active and old_row is not None:
        backup.create_backup(engine, get_source_access(old_row), old_row)

    now = datetime.now(timezone.utc).isoformat()
    if not already_active:
        with engine.begin() as conn:
            conn.execute(text("UPDATE sources SET is_active = 0 WHERE is_active = 1"))
            conn.execute(
                text("UPDATE sources SET is_active = 1, updated_at = :now WHERE id = :id"),
                {"now": now, "id": new_row.id},
            )
            for statement in _SCOPED_DELETE_STATEMENTS:
                conn.execute(text(statement))

    access = get_source_access(new_row)
    detected_backups = backup.list_backups(access)
    auto_restored = None
    if not already_active and detected_backups:
        try:
            result = backup.restore_backup(
                engine, access, new_row, detected_backups[0]["id"], include_global=False
            )
            auto_restored = {"backup_id": detected_backups[0]["id"], "counts": result["counts"]}
        except backup.RestoreError:
            pass

    # Diff-based (the same `rescan` job the "rescan whole library" button
    # uses), so this reconciles any filesystem drift since the backup was
    # taken -- or does a first-time scan when there was nothing to restore --
    # while preserving ids/tags the restore just put in place. Runs as a
    # background job rather than a synchronous walk here: a full walk of a
    # large/slow share (SMB especially) can take a while, and a job gives the
    # frontend live per-item progress (top-bar activity indicator, Jobs
    # modal) instead of a request that blocks with no feedback until the
    # whole tree has been walked.
    scan_job = service.create_job(
        engine, job_type="rescan", scope_type="source", scope_ref=None, parameters={"path": ""}
    )

    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM sources WHERE id = :id"), {"id": new_row.id}).fetchone()

    return {
        "row": row,
        "detected_backups": detected_backups,
        "auto_restored": auto_restored,
        "scan_job": scan_job,
    }
