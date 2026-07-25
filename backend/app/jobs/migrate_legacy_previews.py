"""`migrate_legacy_previews` job execution -- a one-time compatibility shim
for sources that already had per-file animated GIF previews generated
before `preview_gif_relative_path()` (`app/media.py`) switched from a flat
`PREVIEW_GIF_DIR` layout to one mirroring the video's own folder hierarchy
(same scheme `folder_gif_relative_path()` already used for folder previews).

For every video file, renames its GIF from the old flat location to the new
hierarchical one if the old one exists and the new one doesn't yet -- so
already-generated previews are kept instead of forcing a full regenerate.
Driven off the `files` table's authoritative `relative_path` rather than
parsing the legacy flat filename back apart, since `__` (the old separator)
isn't guaranteed unambiguous against real folder/file names.
"""

from __future__ import annotations

from pathlib import PurePosixPath

from sqlalchemy import text

from app.jobs import service
from app.media import PREVIEW_GIF_DIR, preview_gif_relative_path
from app.sources import get_source_access


def _legacy_preview_gif_relative_path(rel_path: str) -> str:
    """The flat path `preview_gif_relative_path()` used to compute before the
    hierarchical migration, kept only for this one-time job."""
    encoded = PurePosixPath(rel_path).with_suffix(".gif").as_posix().replace("/", "__")
    return f"{PREVIEW_GIF_DIR}/{encoded}"


def run_migrate_legacy_previews_job(engine, job: dict) -> tuple[str, str]:
    with engine.connect() as conn:
        source_row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()
    if source_row is None:
        raise RuntimeError("No active source is configured.")

    source_id = source_row.id
    access = get_source_access(source_row)

    with engine.connect() as conn:
        file_rows = conn.execute(
            text(
                "SELECT id, relative_path FROM files WHERE source_id = :sid AND is_video_supported = 1 "
                "ORDER BY relative_path"
            ),
            {"sid": source_id},
        ).all()

    total = len(file_rows)
    service.set_job_total_items(engine, job["id"], total)

    migrated = 0
    skipped = 0
    failed = 0
    for row in file_rows:
        stop = service.check_stop_requested(job["id"])
        if stop:
            verb = "Cancelled" if stop == "cancel" else "Paused"
            status = "cancelled" if stop == "cancel" else "paused"
            message = f"{verb} after migrating {migrated} of {total} file(s)."
            service.log_event(engine, job["id"], None, "info", f"job_{stop}_honored", message)
            return status, message

        item_id = service.create_job_item(
            engine, job["id"], item_key=row.relative_path, file_id=row.id, step_name="migrate_preview_gif"
        )
        service.start_job_item(engine, item_id)
        try:
            legacy_rel = _legacy_preview_gif_relative_path(row.relative_path)
            new_rel = preview_gif_relative_path(row.relative_path)
            if legacy_rel != new_rel and access.exists(legacy_rel) and not access.exists(new_rel):
                access.ensure_dir(str(PurePosixPath(new_rel).parent))
                access.remote_rename(legacy_rel, new_rel)
                service.complete_job_item(engine, item_id, file_id=row.id, message="Migrated to the new layout.")
                service.log_event(
                    engine, job["id"], row.id, "debug", "job_item_completed",
                    f"Migrated preview GIF for {row.relative_path}",
                )
                migrated += 1
            else:
                service.skip_job_item(engine, item_id, "No legacy preview GIF to migrate.")
                skipped += 1
        except Exception as exc:  # noqa: BLE001 - one file's failure must not abort the job
            failed += 1
            service.fail_job_item(engine, item_id, message=str(exc))
            service.log_event(
                engine, job["id"], row.id, "error", "job_item_failed",
                f"Failed to migrate preview GIF for {row.relative_path}: {exc}",
            )

    summary = f"Migrated {migrated} of {total} preview GIF(s) to the new layout"
    if skipped:
        summary += f", {skipped} skipped"
    if failed:
        summary += f", {failed} failed"
    summary += "."

    status = "failed" if failed and migrated == 0 and total > 0 else "completed"
    return status, summary
