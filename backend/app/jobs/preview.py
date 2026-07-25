"""`preview` job execution (Job Model "Preview Jobs", Specification §9).

Handles both scopes:

- **directory** (recursive): generates a `<name>.jpg` collage next to the
  video (plus a companion animated GIF stored in the source's own technical
  folder, `app/media.py`'s `PREVIEW_GIF_DIR`, user request) for every
  supported video under the subtree (skip-processed rule, always excluding
  test-mode artifacts), then
  refreshes `folder-preview.gif` for the target directory and every
  descendant directory that contains at least one supported video
  (Specification §9.5) — an animated GIF cycling
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

import tempfile
import time
from collections import Counter
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

from app import hardware_decode, performance_settings, preview, preview_layouts, preview_settings, similarity
from app.jobs import service
from app.media import folder_gif_relative_path, is_test_artifact, preview_gif_relative_path, sibling_relative_path
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


def _mark_file_previewed(engine, file_id: str, info: dict | None) -> None:
    """`info` is the `conversion.probe_media()` dict from this generation's
    own probe, or `None` when a file is merely adopted/backfilled without
    actually being (re)generated (see the `skip_processed` backfill branch
    below) -- in that case every technical-data column is left exactly as
    it was via `COALESCE`, including `media_probed_at` itself, since no
    fresh probe happened to justify updating it."""
    now = _now()
    probed_at = now if info else None
    info = info or {}
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE files SET has_preview_asset = 1, preview_generated_at = :now, "
                "duration_seconds = COALESCE(:duration, duration_seconds), "
                "width = COALESCE(:width, width), height = COALESCE(:height, height), "
                "video_codec = COALESCE(:video_codec, video_codec), "
                "format_name = COALESCE(:format_name, format_name), "
                "bit_rate = COALESCE(:bit_rate, bit_rate), "
                "media_probed_at = COALESCE(:probed_at, media_probed_at), "
                "updated_at = :now "
                "WHERE id = :id"
            ),
            {
                "now": now,
                "id": file_id,
                "probed_at": probed_at,
                "duration": info.get("duration"),
                "width": info.get("width"),
                "height": info.get("height"),
                "video_codec": info.get("video_codec_name"),
                "format_name": info.get("format_name"),
                "bit_rate": info.get("bit_rate"),
            },
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


def _try_store_similarity_signature(engine, job_id: str, file_id: str, images: list) -> None:
    """Similarity detection is optional and secondary (Specification §13): a
    failure here must never fail the preview job item it piggybacks on.

    `images` are the collage frames `generate_file_preview()` already
    extracted for this same file (post-V1, user request) -- hashed directly
    via `similarity.signature_from_images()` instead of the previous
    `compute_signature(video_path)`, which re-probed and re-extracted the
    file with its own separate ffmpeg calls despite sampling essentially the
    same interior timestamps a second time."""
    try:
        signature = similarity.signature_from_images(images)
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
) -> tuple[str, dict]:
    if not access.exists(file_row.relative_path):
        raise RuntimeError("Source file no longer exists on the source.")

    def on_stage(message: str) -> None:
        service.log_event(engine, job_id, file_row.id, "info", "job_item_progress", message)

    copy_state: dict[str, float | None] = {"t0": None}

    def _on_copy_start() -> None:
        copy_state["t0"] = time.monotonic()
        on_stage("Copying source file locally (no direct/UNC access)…")

    with access.local_copy(file_row.relative_path, on_copy_start=_on_copy_start) as video_path:
        if copy_state["t0"] is not None:
            on_stage(f"Copy finished in {time.monotonic() - copy_state['t0']:.2f}s")
        # The JPEG collage is written next to the video itself (via
        # `commit_new_file`, a no-op move for `local` sources since
        # `local_copy()` already yields the real on-disk path there, an
        # upload for `smb`) -- it's a static asset meant to persist on the
        # source. The GIF goes through the same `commit_new_file` into the
        # source's technical folder instead (`app/media.py`'s
        # `preview_gif_relative_path()`), off to the side since it's a UI
        # asset rather than archived library content.
        local_dest = video_path.with_suffix(".jpg")
        with tempfile.TemporaryDirectory(prefix="va_preview_out_") as gif_stage_dir:
            local_gif = Path(gif_stage_dir) / f"{video_path.stem}.preview.gif"
            info, images = preview.generate_file_preview(
                video_path, local_dest, layout=layout, aspect_ratio=aspect_ratio, gif_dest_path=local_gif,
                gif_max_width=settings["gif_max_width"], gif_colors=settings["gif_colors"],
                animated_source_mode=settings["animated_source_mode"],
                animated_segment_seconds=settings["animated_segment_seconds"],
                animated_transition=settings["animated_transition"],
                frame_seek_mode=settings["frame_seek_mode"],
                max_workers=max_workers,
                on_stage=on_stage,
            )
            dest_rel = sibling_relative_path(file_row.relative_path, local_dest.name)
            access.commit_new_file(local_dest, dest_rel)
            if local_gif.exists():
                access.commit_new_file(local_gif, preview_gif_relative_path(file_row.relative_path))
        _try_store_similarity_signature(engine, job_id, file_row.id, images)
    return dest_rel, info


def run_preview_job(engine, job: dict) -> tuple[str, str]:
    params = job["parameters"] or {}
    layout = _resolve_layout(engine, params.get("layout_preset_id"))
    settings = preview_settings.get_settings(engine)
    aspect_ratio = preview_settings.effective_aspect_ratio(settings)
    worker_count = max(1, performance_settings.get_settings(engine)["parallel_workers"])

    scope_desc = (
        "single file" if job["scope_type"] == "file" else f"directory '{params.get('path') or '(whole source)'}'"
    )
    service.log_event(
        engine, job["id"], None, "info", "job_parameters",
        f"Parameters: scope={scope_desc}, layout='{layout['name']}' ({layout['grid_rows']}x{layout['grid_cols']}), "
        f"workers={worker_count}, frame_seek={settings['frame_seek_mode']}",
    )

    with engine.connect() as conn:
        source_row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()
    if source_row is None:
        raise RuntimeError("No active source is configured.")
    access = get_source_access(source_row)

    if job["scope_type"] == "file":
        return _run_file_scope(engine, job, access, params, layout, aspect_ratio, settings, worker_count)
    return _run_directory_scope(engine, job, access, params, layout, aspect_ratio, settings, worker_count)


def _format_duration(seconds: float) -> str:
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"


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
    started_at = time.monotonic()
    try:
        # Only one file here: spend the full configured parallelism on this
        # file's own independent frame extractions instead (see
        # `preview.generate_file_preview()`'s `max_workers`).
        output_ref, info = _generate_one_file(
            engine, job["id"], access, row, layout, aspect_ratio, settings, max_workers=worker_count
        )
        _mark_file_previewed(engine, row.id, info)
        service.complete_job_item(engine, item_id, output_ref=output_ref, message="Preview generated.")
        service.log_event(
            engine, job["id"], row.id, "info", "job_item_completed",
            f"Preview generated for {row.relative_path} ({_format_duration(time.monotonic() - started_at)})",
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
    started_at = time.monotonic()
    try:
        # Several files already run side by side here, so each one keeps its
        # own frame extraction sequential (max_workers=1, the default) --
        # spending the configured parallelism on both axes at once would
        # spawn `files-in-flight x max_workers` ffmpeg processes together.
        output_ref, info = _generate_one_file(
            engine, job_id, access, row, layout, aspect_ratio, settings
        )
        _mark_file_previewed(engine, row.id, info)
        service.complete_job_item(engine, item_id, output_ref=output_ref, message="Preview generated.")
        service.log_event(
            engine, job_id, row.id, "info", "job_item_completed",
            f"Preview generated for {row.relative_path} ({_format_duration(time.monotonic() - started_at)})",
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

    skipped = 0
    total = len(candidates)
    service.set_job_total_items(engine, job["id"], total)

    # Independent files are processed `worker_count` at a time, submitting
    # the next file as soon as a slot frees up rather than waiting for a
    # whole batch to finish (post-V1, user request -- see
    # `service.run_sliding_window()`'s docstring for why). `next_item()` also
    # performs the skip-processed check inline: it runs on the calling
    # thread, so a skipped file never consumes a worker slot.
    candidates_iter = iter(candidates)

    def next_item():
        nonlocal skipped
        for row in candidates_iter:
            # Checks the collage and GIF files themselves, not just the DB
            # flag, in both directions: a missing on-source file makes
            # regeneration self-healing instead of permanently skipping a
            # file whose preview is actually gone (it can be deleted
            # directly on the source, a later-restored metadata snapshot may
            # predate it, or -- as with the flat-to-hierarchical GIF path
            # migration -- the naming scheme changed under it), while a
            # present on-source file that the DB doesn't know about yet
            # (e.g. an interrupted prior run, or files copied in alongside
            # their already generated previews) is adopted by backfilling
            # the DB flag instead of paying to regenerate an asset that
            # already exists (user report). Both assets are required to
            # skip, since `_process_preview_file()` always (re)generates the
            # collage and GIF together -- a file missing either one gets
            # both regenerated.
            collage_rel = sibling_relative_path(row.relative_path, f"{Path(row.file_name).stem}.jpg")
            gif_rel = preview_gif_relative_path(row.relative_path)
            if skip_processed and access.exists(collage_rel) and access.exists(gif_rel):
                if not row.has_preview_asset:
                    _mark_file_previewed(engine, row.id, None)
                item_id = service.create_job_item(engine, job["id"], file_id=row.id, step_name="preview_file")
                service.skip_job_item(engine, item_id, "Already has a preview; skipped.")
                service.log_event(
                    engine, job["id"], row.id, "debug", "job_item_skipped",
                    f"Skipped {row.relative_path} (already previewed).",
                )
                skipped += 1
                continue
            return row
        return None

    results, stop = service.run_sliding_window(
        job["id"],
        worker_count,
        next_item,
        lambda row: _process_preview_file(engine, job["id"], access, row, layout, aspect_ratio, settings),
    )
    processed = sum(1 for ok in results if ok)
    failed = sum(1 for ok in results if not ok)
    stop_status = "cancelled" if stop == "cancel" else "paused" if stop == "pause" else None

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
    gif_max_width = settings["gif_max_width"]
    frame_seek_mode = settings["frame_seek_mode"]
    updated = 0

    # Once per sweep, not once per directory (post-V1, user request "make it
    # visible when hardware acceleration is actually used").
    hw_backend = hardware_decode.decode_backend()
    if hw_backend:
        service.log_event(
            engine, job["id"], None, "info", "job_item_progress",
            f"🚀 Hardware decode active ({hw_backend.upper()}) for folder-preview frame extraction",
        )

    # A video nested several levels deep is a candidate for every ancestor
    # directory's own folder-preview.gif, so materialized local copies and
    # extracted segments are cached across the whole sweep (post-V1, user
    # request) instead of being re-downloaded (SMB: a full network transfer
    # per ancestor level) and re-decoded from scratch at every level. Cached
    # frames are shrunk to the GIF's own target width before caching
    # (`preview.shrink_frame()`) so the in-memory cache stays roughly
    # GIF-sized per frame instead of holding full source-resolution frames
    # for the whole sweep's duration. `job_stack` -- not a per-directory one
    # -- keeps materialized local copies alive (SMB: on local disk) for the
    # whole sweep too, the deliberate memory/disk-for-time trade-off here.
    with ExitStack() as job_stack:
        local_paths: dict[str, Path] = {}
        segments_cache: dict[tuple[str, int], list] = {}

        def get_local_path(rel: str) -> Path:
            if rel not in local_paths:
                copy_state: dict[str, float | None] = {"t0": None}

                def _on_copy_start() -> None:
                    copy_state["t0"] = time.monotonic()
                    service.log_event(
                        engine, job["id"], None, "info", "job_item_progress",
                        f"Copying '{rel}' locally (no direct/UNC access)…",
                    )

                path = job_stack.enter_context(access.local_copy(rel, on_copy_start=_on_copy_start))
                if copy_state["t0"] is not None:
                    service.log_event(
                        engine, job["id"], None, "info", "job_item_progress",
                        f"Copy of '{rel}' finished in {time.monotonic() - copy_state['t0']:.2f}s",
                    )
                local_paths[rel] = path
            return local_paths[rel]

        def get_segments(rel: str, count: int) -> list:
            key = (rel, count)
            if key not in segments_cache:
                raw_segments = preview.pick_representative_segments(
                    get_local_path(rel), count, mode=animated_source_mode,
                    segment_seconds=animated_segment_seconds, seek_mode=frame_seek_mode,
                )
                segments_cache[key] = [
                    [preview.shrink_frame(frame, gif_max_width) for frame in segment]
                    for segment in raw_segments
                ]
            return segments_cache[key]

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

            path_counts = Counter(plan)
            dest_name = "folder-preview.gif"
            dir_label = directory.relative_path or "(root)"

            service.log_event(
                engine, job["id"], None, "info", "job_item_progress",
                f"Building folder preview for {dir_label}: {len(plan)} segment(s) from {len(path_counts)} video(s)",
            )
            try:
                t0 = time.monotonic()
                segments_by_rel = {rel: get_segments(rel, count) for rel, count in path_counts.items()}
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
                with tempfile.TemporaryDirectory(prefix="va_preview_out_") as gif_stage_dir:
                    local_dest = Path(gif_stage_dir) / dest_name
                    preview.render_gif(
                        images, local_dest, aspect_ratio,
                        max_width=gif_max_width, colors=settings["gif_colors"],
                        segment_seconds=animated_segment_seconds, transition=animated_transition,
                        segment_sizes=segment_sizes,
                    )
                    if not local_dest.exists():
                        raise preview.PreviewError("Could not extract any frames for the folder preview.")
                    access.commit_new_file(local_dest, folder_gif_relative_path(directory.relative_path))
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
