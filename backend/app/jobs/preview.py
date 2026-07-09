"""`preview` job execution (Job Model "Preview Jobs", Specification §9).

Handles both scopes:

- **directory** (recursive): generates a `<name>.jpg` collage (plus a
  companion animated GIF stored in `.video-archive/previews/`, user request)
  for every supported video under the subtree (skip-processed rule, always
  excluding test-mode artifacts), then refreshes `folder-preview.gif` for
  the target directory and every descendant directory that contains at
  least one supported video (Specification §9.5) — an animated GIF cycling
  through frames drawn from different videos/subfolders for diversity
  (`preview.diverse_video_frame_plan()`, user request), not a static
  collage.
- **file**: generates a `<name>.jpg` collage plus GIF for one video; always
  regenerates (no skip-processed toggle — this is an explicit single-file
  action, not a bulk job).

The layout preset and global settings (aspect ratio, folder-preview frame
count, GIF max width/color count, animated-preview source mode/segment
duration/transition — user request) are resolved once at launch and reused
for the whole job (Job Model "Preview Jobs" — "use preview settings
snapshot at launch time").
"""

from __future__ import annotations

import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import datetime, timezone

from sqlalchemy import text

from app import performance_settings, preview, preview_layouts, preview_settings, similarity
from app.jobs import service
from app.media import is_test_artifact, preview_gif_relative_path, sibling_relative_path
from app.sources import SourceAccess, get_source_access


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_layout(engine, preset_id: str | None) -> dict:
    preset = preview_layouts.get_preset(engine, preset_id) if preset_id else None
    if preset is None:
        preset = preview_layouts.get_default_preset(engine)
    if preset is None:
        raise RuntimeError("No preview layout preset is available.")
    return preset


def _mark_file_previewed(engine, file_id: str, duration_seconds: float | None) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE files SET has_preview_asset = 1, preview_generated_at = :now, "
                "duration_seconds = COALESCE(:duration, duration_seconds), updated_at = :now "
                "WHERE id = :id"
            ),
            {"now": _now(), "id": file_id, "duration": duration_seconds},
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


def _try_store_similarity_signature(engine, job_id: str, file_id: str, video_path) -> None:
    """Similarity detection is optional and secondary (Specification §13): a
    failure here must never fail the preview job item it piggybacks on."""
    try:
        signature = similarity.compute_signature(video_path)
        if signature is not None:
            similarity.store_signature(engine, file_id, signature, job_id=job_id)
    except Exception:  # noqa: BLE001 - best-effort only, see docstring
        pass


def _generate_one_file(
    engine,
    job_id: str,
    access: SourceAccess,
    file_row,
    layout: dict,
    aspect_ratio: float,
    settings: dict,
    max_workers: int = 1,
) -> tuple[str, float | None]:
    if not access.exists(file_row.relative_path):
        raise RuntimeError("Source file no longer exists on the source.")

    def on_stage(message: str) -> None:
        service.log_event(engine, job_id, file_row.id, "info", "job_item_progress", message)

    with access.local_copy(file_row.relative_path) as video_path:
        local_dest = video_path.with_suffix(".jpg")
        local_gif = video_path.parent / f"{video_path.stem}.preview.gif"
        duration_seconds = preview.generate_file_preview(
            video_path, local_dest, layout=layout, aspect_ratio=aspect_ratio, gif_dest_path=local_gif,
            gif_max_width=settings["gif_max_width"], gif_colors=settings["gif_colors"],
            animated_source_mode=settings["animated_source_mode"],
            animated_segment_seconds=settings["animated_segment_seconds"],
            animated_transition=settings["animated_transition"],
            max_workers=max_workers,
            on_stage=on_stage,
        )
        dest_rel = sibling_relative_path(file_row.relative_path, local_dest.name)
        access.commit_new_file(local_dest, dest_rel)
        if local_gif.exists():
            access.commit_new_file(local_gif, preview_gif_relative_path(file_row.relative_path))
        _try_store_similarity_signature(engine, job_id, file_row.id, video_path)
    return dest_rel, duration_seconds


def run_preview_job(engine, job: dict) -> tuple[str, str]:
    params = job["parameters"] or {}
    layout = _resolve_layout(engine, params.get("layout_preset_id"))
    settings = preview_settings.get_settings(engine)
    aspect_ratio = preview_settings.effective_aspect_ratio(settings)
    worker_count = max(1, performance_settings.get_settings(engine)["parallel_workers"])

    with engine.connect() as conn:
        source_row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()
    if source_row is None:
        raise RuntimeError("No active source is configured.")
    access = get_source_access(source_row)

    if job["scope_type"] == "file":
        return _run_file_scope(engine, job, access, params, layout, aspect_ratio, settings, worker_count)
    return _run_directory_scope(engine, job, access, params, layout, aspect_ratio, settings, worker_count)


def _run_file_scope(
    engine,
    job: dict,
    access: SourceAccess,
    params: dict,
    layout: dict,
    aspect_ratio: float,
    settings: dict,
    worker_count: int,
) -> tuple[str, str]:
    file_id = params.get("file_id")
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM files WHERE id = :id"), {"id": file_id}).fetchone()
    if row is None:
        raise RuntimeError("File not found.")

    item_id = service.create_job_item(
        engine, job["id"], item_key=row.relative_path, file_id=row.id, step_name="preview_file"
    )
    service.start_job_item(engine, item_id)
    service.log_event(
        engine, job["id"], row.id, "info", "job_item_started", f"Generating preview for {row.relative_path}"
    )
    try:
        # Only one file here: spend the full configured parallelism on this
        # file's own independent frame extractions instead (see
        # `preview.generate_file_preview()`'s `max_workers`).
        output_ref, duration_seconds = _generate_one_file(
            engine, job["id"], access, row, layout, aspect_ratio, settings, max_workers=worker_count
        )
        _mark_file_previewed(engine, row.id, duration_seconds)
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


def _process_preview_file(
    engine, job_id: str, access: SourceAccess, row, layout: dict, aspect_ratio: float, settings: dict
) -> bool:
    """One directory-scope file, run from inside a batch's thread pool.
    Returns whether it succeeded; failures are recorded through the normal
    job-item/event mechanism (thread-safe, see `app/jobs/service.py`) rather
    than raised, so one file's failure can't abort a whole in-flight batch."""
    item_id = service.create_job_item(
        engine, job_id, item_key=row.relative_path, file_id=row.id, step_name="preview_file"
    )
    service.start_job_item(engine, item_id)
    service.log_event(
        engine, job_id, row.id, "info", "job_item_started", f"Generating preview for {row.relative_path}"
    )
    try:
        # Several files already run side by side here, so each one keeps its
        # own frame extraction sequential (max_workers=1, the default) --
        # spending the configured parallelism on both axes at once would
        # spawn `files-in-flight x max_workers` ffmpeg processes together.
        output_ref, duration_seconds = _generate_one_file(engine, job_id, access, row, layout, aspect_ratio, settings)
        _mark_file_previewed(engine, row.id, duration_seconds)
        service.complete_job_item(engine, item_id, output_ref=output_ref, message="Preview generated.")
        service.log_event(
            engine, job_id, row.id, "info", "job_item_completed", f"Preview generated for {row.relative_path}"
        )
        return True
    except Exception as exc:  # noqa: BLE001 - one file's failure must not abort the job
        service.fail_job_item(engine, item_id, message=str(exc))
        service.log_event(
            engine, job_id, row.id, "error", "job_item_failed",
            f"Failed to generate preview for {row.relative_path}: {exc}",
        )
        return False


def _run_directory_scope(
    engine,
    job: dict,
    access: SourceAccess,
    params: dict,
    layout: dict,
    aspect_ratio: float,
    settings: dict,
    worker_count: int,
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
    stop_status: str | None = None
    service.set_job_total_items(engine, job["id"], total)

    # Independent files are processed `worker_count` at a time (post-V1,
    # user request -- a directory-scope job used to run one ffmpeg process
    # at a time regardless of available CPU cores). A batch is flushed (run
    # concurrently, then awaited) once it reaches `worker_count`, or at the
    # end of the loop for a trailing partial batch; the cooperative
    # cancel/pause check runs between batches, same checkpoint granularity
    # idea as the old between-files check, just coarser by up to
    # `worker_count - 1` in-flight files.
    batch: list = []

    def flush(pending: list) -> None:
        nonlocal processed, failed
        if not pending:
            return
        with ThreadPoolExecutor(max_workers=len(pending)) as executor:
            results = list(
                executor.map(
                    lambda r: _process_preview_file(engine, job["id"], access, r, layout, aspect_ratio, settings),
                    pending,
                )
            )
        for ok in results:
            if ok:
                processed += 1
            else:
                failed += 1

    for row in candidates:
        stop = service.check_stop_requested(job["id"])
        if stop:
            stop_status = "cancelled" if stop == "cancel" else "paused"
            break

        if skip_processed and row.has_preview_asset:
            item_id = service.create_job_item(engine, job["id"], file_id=row.id, step_name="preview_file")
            service.skip_job_item(engine, item_id, "Already has a preview; skipped.")
            service.log_event(
                engine, job["id"], row.id, "debug", "job_item_skipped",
                f"Skipped {row.relative_path} (already previewed).",
            )
            skipped += 1
            continue

        batch.append(row)
        if len(batch) >= worker_count:
            flush(batch)
            batch = []

    flush(batch)

    folder_count = 0
    if stop_status is None:
        folder_count, stop_status = _generate_folder_previews(
            engine, job, source_id, access, relative_path, settings
        )

    if stop_status is not None:
        verb = "Cancelled" if stop_status == "cancelled" else "Paused"
        event = "job_cancel_honored" if stop_status == "cancelled" else "job_pause_honored"
        message = f"{verb} after {processed} of {total} file(s)."
        service.log_event(engine, job["id"], None, "info", event, message)
        return stop_status, message

    summary = f"Generated previews for {processed} of {total} file(s)"
    if skipped:
        summary += f", {skipped} skipped"
    if failed:
        summary += f", {failed} failed"
    summary += f"; {folder_count} folder preview(s) updated."

    status = "failed" if failed and processed == 0 and total > 0 else "completed"
    return status, summary


def _generate_folder_previews(
    engine, job: dict, source_id: str, access: SourceAccess, relative_path: str, settings: dict
) -> tuple[int, str | None]:
    """Refresh folder-preview.gif for the target directory and every
    descendant directory that contains at least one supported video
    (Specification §9.5). Returns `(updated_count, stop_status)`, where
    `stop_status` is `None`/`"cancelled"`/`"paused"`."""
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
    animated_source_mode = settings["animated_source_mode"]
    animated_segment_seconds = settings["animated_segment_seconds"]
    animated_transition = settings["animated_transition"]
    updated = 0

    for directory in directories:
        stop = service.check_stop_requested(job["id"])
        if stop:
            return updated, ("cancelled" if stop == "cancel" else "paused")

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

        candidate_rels = [
            row.relative_path for row in video_rows if not is_test_artifact(row.file_name)
        ]
        if not candidate_rels:
            continue

        # Frame plan is computed on paths relative to *this* directory (not
        # the source root) so `diverse_video_frame_plan()` groups by the
        # directory's own immediate subfolders rather than collapsing every
        # candidate into one "group" sharing the directory's own ancestry.
        prefix = f"{directory.relative_path}/" if directory.relative_path else ""
        local_rels = [rel[len(prefix):] for rel in candidate_rels]
        plan = [f"{prefix}{rel}" for rel in preview.diverse_video_frame_plan(local_rels, frame_count)]
        if not plan:
            continue

        # Only materialize the videos actually used by the GIF (Specification
        # §9.1 "representative frames", default 4) — matters for SMB sources,
        # where materializing means a network download per video.
        path_counts = Counter(plan)
        dest_name = "folder-preview.gif"
        dest_rel = f"{directory.relative_path}/{dest_name}" if directory.relative_path else dest_name
        dir_label = directory.relative_path or "(root)"

        service.log_event(
            engine, job["id"], None, "info", "job_item_progress",
            f"Building folder preview for {dir_label}: {len(plan)} segment(s) from {len(path_counts)} video(s)",
        )
        try:
            with ExitStack() as stack:
                t0 = time.monotonic()
                local_paths = {rel: stack.enter_context(access.local_copy(rel)) for rel in path_counts}
                segments_by_rel = {
                    rel: preview.pick_representative_segments(
                        local_paths[rel], count, mode=animated_source_mode,
                        segment_seconds=animated_segment_seconds,
                    )
                    for rel, count in path_counts.items()
                }
                cursors: dict[str, int] = {rel: 0 for rel in path_counts}
                images = []
                segment_sizes = []
                for rel in plan:
                    segments = segments_by_rel[rel]
                    idx = cursors[rel]
                    cursors[rel] += 1
                    if idx < len(segments):
                        images.extend(segments[idx])
                        segment_sizes.append(len(segments[idx]))
                service.log_event(
                    engine, job["id"], None, "info", "job_item_progress",
                    f"Extracted {len(images)} frame(s) for {dir_label} in {time.monotonic() - t0:.2f}s",
                )

                t0 = time.monotonic()
                stage_dir = stack.enter_context(access.stage_output_dir(directory.relative_path))
                local_dest = stage_dir / dest_name
                preview.render_gif(
                    images, local_dest, aspect_ratio,
                    max_width=settings["gif_max_width"], colors=settings["gif_colors"],
                    segment_seconds=animated_segment_seconds, transition=animated_transition,
                    segment_sizes=segment_sizes,
                )
                if not local_dest.exists():
                    raise preview.PreviewError("Could not extract any frames for the folder preview.")
                access.commit_new_file(local_dest, dest_rel)
                service.log_event(
                    engine, job["id"], None, "info", "job_item_progress",
                    f"Rendered folder preview GIF for {dir_label} in {time.monotonic() - t0:.2f}s",
                )
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

    return updated, None
