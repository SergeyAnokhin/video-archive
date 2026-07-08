"""`rescan` job execution (Job Model "Job Types", scope: source or directory).

Refreshes existing metadata for a directory subtree (or the whole source when
no path is given). Unlike the Stage 2 `scan_source()` batch sync, files are
processed one at a time so each becomes a visible `job_items` row with its
own progress, and the loop checks for cooperative cancellation between files
(Job Model "Cancellation Rules").
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from app.jobs import service
from app.scan import discover_filesystem, upsert_directory, upsert_file
from app.sources import get_source_access


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_rescan_job(engine, job: dict) -> tuple[str, str]:
    relative_path = (job["parameters"] or {}).get("path", "") or ""

    with engine.connect() as conn:
        source_row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()
    if source_row is None:
        raise RuntimeError("No active source is configured.")

    source_id = source_row.id
    access = get_source_access(source_row)

    if relative_path and not access.is_dir(relative_path):
        raise RuntimeError(f"Directory not found on source: {relative_path}")

    touched_dirs, touched_files = discover_filesystem(access, relative_path)
    now = _now()

    # Directories aren't individually meaningful job items; sync them as one
    # batch, same as the whole-source scan does.
    with engine.begin() as conn:
        dir_ids: dict[str, str] = {}
        for rel_dir, (name, parent_rel, has_preview) in touched_dirs.items():
            existing = conn.execute(
                text("SELECT id FROM directories WHERE source_id = :sid AND relative_path = :rel"),
                {"sid": source_id, "rel": rel_dir},
            ).fetchone()
            dir_ids[rel_dir] = upsert_directory(
                conn, source_id, rel_dir, name, parent_rel, has_preview, now,
                existing_id=existing.id if existing else None,
            )

    processed = 0
    failed = 0
    total = len(touched_files)
    service.set_job_total_items(engine, job["id"], total)

    for rel_file, attrs in touched_files.items():
        if service.is_cancel_requested(job["id"]):
            message = f"Cancelled after {processed} of {total} file(s)."
            service.log_event(engine, job["id"], None, "info", "job_cancel_honored", message)
            return "cancelled", message

        item_id = service.create_job_item(engine, job["id"], item_key=rel_file, step_name="rescan_file")
        service.start_job_item(engine, item_id)
        try:
            with engine.begin() as conn:
                existing = conn.execute(
                    text("SELECT id FROM files WHERE source_id = :sid AND relative_path = :rel"),
                    {"sid": source_id, "rel": rel_file},
                ).fetchone()
                file_id = upsert_file(
                    conn, source_id, dir_ids[attrs["directory_rel"]], rel_file, attrs, now,
                    existing_id=existing.id if existing else None,
                )
            service.complete_job_item(engine, item_id, file_id=file_id, message="Metadata refreshed.")
            service.log_event(engine, job["id"], file_id, "debug", "job_item_completed", f"Rescanned {rel_file}")
            processed += 1
        except Exception as exc:  # noqa: BLE001 - one file's failure must not abort the job
            failed += 1
            service.fail_job_item(engine, item_id, message=str(exc))
            service.log_event(
                engine, job["id"], None, "error", "job_item_failed", f"Failed to rescan {rel_file}: {exc}"
            )

    removed = _remove_stale(engine, source_id, relative_path, touched_dirs, touched_files)

    summary = f"Rescanned {processed} of {total} file(s)"
    if failed:
        summary += f", {failed} failed"
    if removed:
        summary += f", removed {removed} stale record(s)"
    summary += "."

    status = "failed" if failed and processed == 0 and total > 0 else "completed"
    return status, summary


def _remove_stale(
    engine,
    source_id: str,
    relative_path: str,
    touched_dirs: dict[str, tuple[str, str | None, bool]],
    touched_files: dict[str, dict],
) -> int:
    with engine.begin() as conn:
        if relative_path:
            prefix = f"{relative_path}/%"
            file_rows = conn.execute(
                text(
                    "SELECT id, relative_path FROM files WHERE source_id = :sid "
                    "AND (relative_path = :rel OR relative_path LIKE :prefix)"
                ),
                {"sid": source_id, "rel": relative_path, "prefix": prefix},
            ).all()
            dir_rows = conn.execute(
                text(
                    "SELECT id, relative_path FROM directories WHERE source_id = :sid "
                    "AND (relative_path = :rel OR relative_path LIKE :prefix)"
                ),
                {"sid": source_id, "rel": relative_path, "prefix": prefix},
            ).all()
        else:
            file_rows = conn.execute(
                text("SELECT id, relative_path FROM files WHERE source_id = :sid"), {"sid": source_id}
            ).all()
            dir_rows = conn.execute(
                text("SELECT id, relative_path FROM directories WHERE source_id = :sid"), {"sid": source_id}
            ).all()

        stale_files = [{"id": row.id} for row in file_rows if row.relative_path not in touched_files]
        stale_dirs = [{"id": row.id} for row in dir_rows if row.relative_path not in touched_dirs]

        if stale_files:
            conn.execute(text("DELETE FROM files WHERE id = :id"), stale_files)
        if stale_dirs:
            conn.execute(text("DELETE FROM directories WHERE id = :id"), stale_dirs)

    return len(stale_files) + len(stale_dirs)
