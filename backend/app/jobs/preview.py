"""`preview` job execution (Job Model "Preview Jobs", Specification §9).

Handles both scopes:

- **directory** (recursive): generates a `<name>.jpg` collage for every
  supported video under the subtree (skip-processed rule, always excluding
  test-mode artifacts), then refreshes `folder-preview.jpg` for the target
  directory and every descendant directory that contains at least one
  supported video (Specification §9.5).
- **file**: generates a `<name>.jpg` collage for one video; always
  regenerates (no skip-processed toggle — this is an explicit single-file
  action, not a bulk job).

The layout preset and global settings (aspect ratio, folder-preview frame
count) are resolved once at launch and reused for the whole job (Job Model
"Preview Jobs" — "use preview settings snapshot at launch time").
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app import preview, preview_layouts, preview_settings
from app.jobs import service
from app.media import is_test_artifact


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _rel(source_root: Path, path: Path) -> str:
    return path.relative_to(source_root).as_posix()


def _resolve_layout(engine, preset_id: str | None) -> dict:
    preset = preview_layouts.get_preset(engine, preset_id) if preset_id else None
    if preset is None:
        preset = preview_layouts.get_default_preset(engine)
    if preset is None:
        raise RuntimeError("No preview layout preset is available.")
    return preset


def _mark_file_previewed(engine, file_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE files SET has_preview_asset = 1, preview_generated_at = :now, updated_at = :now "
                "WHERE id = :id"
            ),
            {"now": _now(), "id": file_id},
        )


def _mark_folder_previewed(engine, directory_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE directories SET has_folder_preview = 1, folder_preview_generated_at = :now, "
                "updated_at = :now WHERE id = :id"
            ),
            {"now": _now(), "id": directory_id},
        )


def _generate_one_file(source_root: Path, file_row, layout: dict, aspect_ratio: float) -> str:
    video_path = source_root / file_row.relative_path
    if not video_path.exists():
        raise RuntimeError("Source file no longer exists on disk.")
    dest_path = video_path.with_suffix(".jpg")
    preview.generate_file_preview(video_path, dest_path, layout=layout, aspect_ratio=aspect_ratio)
    return _rel(source_root, dest_path)


def run_preview_job(engine, job: dict) -> tuple[str, str]:
    params = job["parameters"] or {}
    layout = _resolve_layout(engine, params.get("layout_preset_id"))
    settings = preview_settings.get_settings(engine)
    aspect_ratio = preview_settings.effective_aspect_ratio(settings)

    with engine.connect() as conn:
        source_row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()
    if source_row is None:
        raise RuntimeError("No active source is configured.")
    source_root = Path(source_row.root_path)

    if job["scope_type"] == "file":
        return _run_file_scope(engine, job, source_root, params, layout, aspect_ratio)
    return _run_directory_scope(engine, job, source_root, params, layout, aspect_ratio, settings)


def _run_file_scope(engine, job: dict, source_root: Path, params: dict, layout: dict, aspect_ratio: float) -> tuple[str, str]:
    file_id = params.get("file_id")
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM files WHERE id = :id"), {"id": file_id}).fetchone()
    if row is None:
        raise RuntimeError("File not found.")

    item_id = service.create_job_item(engine, job["id"], file_id=row.id, step_name="preview_file")
    service.start_job_item(engine, item_id)
    try:
        output_ref = _generate_one_file(source_root, row, layout, aspect_ratio)
        _mark_file_previewed(engine, row.id)
        service.complete_job_item(engine, item_id, output_ref=output_ref, message="Preview generated.")
        service.log_event(
            engine, job["id"], row.id, "info", "job_item_completed", f"Preview generated for {row.relative_path}"
        )
        return "completed", "Preview generated."
    except Exception as exc:  # noqa: BLE001 - failure is reported through the job, not raised further
        service.fail_job_item(engine, item_id, message=str(exc))
        service.log_event(
            engine, job["id"], row.id, "error", "job_item_failed",
            f"Failed to generate preview for {row.relative_path}: {exc}",
        )
        return "failed", str(exc)


def _run_directory_scope(
    engine, job: dict, source_root: Path, params: dict, layout: dict, aspect_ratio: float, settings: dict
) -> tuple[str, str]:
    relative_path = params.get("path", "") or ""
    skip_processed = params.get("skip_processed", True)

    with engine.connect() as conn:
        source_id = conn.execute(text("SELECT id FROM sources WHERE is_active = 1 LIMIT 1")).fetchone().id

        clauses = ["source_id = :sid", "is_video_supported = 1"]
        query_params: dict = {"sid": source_id}
        if relative_path:
            clauses.append("(relative_path = :rel OR relative_path LIKE :prefix)")
            query_params["rel"] = relative_path
            query_params["prefix"] = f"{relative_path}/%"

        rows = conn.execute(
            text(f"SELECT * FROM files WHERE {' AND '.join(clauses)} ORDER BY relative_path"),
            query_params,
        ).all()

    candidates = [row for row in rows if not is_test_artifact(row.file_name)]

    processed = 0
    skipped = 0
    failed = 0
    total = len(candidates)
    cancelled = False

    for row in candidates:
        if service.is_cancel_requested(job["id"]):
            cancelled = True
            break

        item_id = service.create_job_item(engine, job["id"], file_id=row.id, step_name="preview_file")

        if skip_processed and row.has_preview_asset:
            service.skip_job_item(engine, item_id, "Already has a preview; skipped.")
            service.log_event(
                engine, job["id"], row.id, "debug", "job_item_skipped",
                f"Skipped {row.relative_path} (already previewed).",
            )
            skipped += 1
            continue

        service.start_job_item(engine, item_id)
        try:
            output_ref = _generate_one_file(source_root, row, layout, aspect_ratio)
            _mark_file_previewed(engine, row.id)
            service.complete_job_item(engine, item_id, output_ref=output_ref, message="Preview generated.")
            service.log_event(
                engine, job["id"], row.id, "info", "job_item_completed", f"Preview generated for {row.relative_path}"
            )
            processed += 1
        except Exception as exc:  # noqa: BLE001 - one file's failure must not abort the job
            failed += 1
            service.fail_job_item(engine, item_id, message=str(exc))
            service.log_event(
                engine, job["id"], row.id, "error", "job_item_failed",
                f"Failed to generate preview for {row.relative_path}: {exc}",
            )

    folder_count = 0
    if not cancelled:
        folder_count, cancelled = _generate_folder_previews(engine, job, source_id, source_root, relative_path, settings)

    if cancelled:
        message = f"Cancelled after {processed} of {total} file(s)."
        service.log_event(engine, job["id"], None, "info", "job_cancel_honored", message)
        return "cancelled", message

    summary = f"Generated previews for {processed} of {total} file(s)"
    if skipped:
        summary += f", {skipped} skipped"
    if failed:
        summary += f", {failed} failed"
    summary += f"; {folder_count} folder preview(s) updated."

    status = "failed" if failed and processed == 0 and total > 0 else "completed"
    return status, summary


def _generate_folder_previews(
    engine, job: dict, source_id: str, source_root: Path, relative_path: str, settings: dict
) -> tuple[int, bool]:
    """Refresh folder-preview.jpg for the target directory and every
    descendant directory that contains at least one supported video
    (Specification §9.5). Returns `(updated_count, cancelled)`."""
    with engine.connect() as conn:
        dir_clauses = ["source_id = :sid"]
        dir_params: dict = {"sid": source_id}
        if relative_path:
            dir_clauses.append("(relative_path = :rel OR relative_path LIKE :prefix)")
            dir_params["rel"] = relative_path
            dir_params["prefix"] = f"{relative_path}/%"
        directories = conn.execute(
            text(f"SELECT * FROM directories WHERE {' AND '.join(dir_clauses)}"), dir_params
        ).all()

    aspect_ratio = preview_settings.effective_aspect_ratio(settings)
    frame_count = settings["folder_preview_frame_count"]
    updated = 0

    for directory in directories:
        if service.is_cancel_requested(job["id"]):
            return updated, True

        with engine.connect() as conn:
            if directory.relative_path:
                video_rows = conn.execute(
                    text(
                        "SELECT relative_path, file_name FROM files "
                        "WHERE source_id = :sid AND is_video_supported = 1 AND relative_path LIKE :prefix "
                        "ORDER BY relative_path"
                    ),
                    {"sid": source_id, "prefix": f"{directory.relative_path}/%"},
                ).all()
            else:
                video_rows = conn.execute(
                    text(
                        "SELECT relative_path, file_name FROM files "
                        "WHERE source_id = :sid AND is_video_supported = 1 ORDER BY relative_path"
                    ),
                    {"sid": source_id},
                ).all()

        candidates = [
            source_root / row.relative_path for row in video_rows if not is_test_artifact(row.file_name)
        ]
        if not candidates:
            continue

        directory_path = source_root / directory.relative_path if directory.relative_path else source_root
        dest_path = directory_path / "folder-preview.jpg"
        caption = directory.name or source_root.name

        try:
            preview.generate_folder_preview(candidates, frame_count, dest_path, caption, aspect_ratio)
            _mark_folder_previewed(engine, directory.id)
            service.log_event(
                engine, job["id"], None, "info", "job_item_completed",
                f"Folder preview generated for {directory.relative_path or '(root)'}",
            )
            updated += 1
        except Exception as exc:  # noqa: BLE001 - one folder's failure must not abort the pass
            service.log_event(
                engine, job["id"], None, "error", "job_item_failed",
                f"Failed folder preview for {directory.relative_path or '(root)'}: {exc}",
            )

    return updated, False
