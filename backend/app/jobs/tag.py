"""`tag` job execution (Specification §12): resolves the active tag
vocabulary and tagging settings once at launch (same "settings snapshot at
launch time" convention as the `preview` job), then for each video builds
sampled-frame images (`app/tagging.py`) and sends them to a provider
(`app/providers/registry.py`), trying enabled `app/provider_entries.py`
entries in priority order until one succeeds -- replacing the file's
`file_tags` with the top-N scoring tags (Data Model §9 "Re-tagging replaces
the file's previous tag set").

The list of enabled entries and which ones have already failed
(`dead_entries`) are read/tracked fresh per job run rather than frozen at
job-creation time, so the fallback chain reflects the live provider
priority list and a broken entry is skipped for the rest of the run once it
fails once.

Persistent batch tagging (submit/poll/resume across a directory scope,
Specification §12.3 Stage 9) lives in `app/jobs/tag_batch.py`; this module
only decides whether a batch attempt is worth making (`_run_directory_scope`)
or whether a job is resuming one (`run_tag_job`) and otherwise owns the
synchronous per-file path (`_tag_one_file`) that batch tagging itself falls
back to for anything it can't resolve.
"""

from __future__ import annotations

from sqlalchemy import text

from app import batch_submissions, provider_entries, similarity, tagging, tagging_settings, tags as tags_service
from app.jobs import service
from app.media import is_test_artifact
from app.providers import registry
from app.sources import SourceAccess, get_source_access


def _try_store_similarity_signature_for_image(engine, job_id: str | None, file_id: str, image_path) -> None:
    """Similarity detection for a standalone image piggybacks on the tag job
    (post-V1, user request -- "similar images", image-vs-image only), the
    same way `jobs/preview.py`'s `_try_store_similarity_signature()` does for
    video off the preview job: optional and secondary, so a failure here
    must never fail the tag job item it rides along with."""
    try:
        signature = similarity.compute_image_signature(image_path)
        if signature is not None:
            similarity.store_signature(engine, file_id, signature, job_id=job_id)
    except Exception:  # noqa: BLE001 - best-effort only, see docstring
        pass


def _tag_one_file(
    engine, access: SourceAccess, file_row, vocabulary: list[dict], settings: dict,
    entries: list[dict], dead_entries: set[str], job_id: str | None = None,
) -> str:
    if not access.exists(file_row.relative_path):
        raise RuntimeError("Source file no longer exists on the source.")

    is_video = bool(file_row.is_video_supported)
    with access.local_copy(file_row.relative_path) as local_path:
        images = tagging.build_tagging_images_for_file(
            local_path, is_video,
            settings["sample_frame_count"], settings["combine_into_collage"], settings["image_resolution"],
        )
        if not is_video:
            _try_store_similarity_signature_for_image(engine, job_id, file_row.id, local_path)
    display_names = [tag["display_name"] for tag in vocabulary]
    scores, used_entry = registry.score_tags_with_fallback(
        engine, entries, images, display_names, dead_entries, job_id=job_id
    )

    ranked = sorted(zip(vocabulary, scores), key=lambda pair: pair[1], reverse=True)
    top = [pair for pair in ranked if pair[1] > 0][: settings["top_tag_count"]]
    scored_tags = [
        {
            "id": tag["id"],
            "score": score,
            "provider_name": used_entry["provider_type"],
            "model_name": used_entry["vision_model"],
        }
        for tag, score in top
    ]

    if job_id is not None:
        _log_tag_scores(engine, job_id, file_row, top, used_entry["provider_type"], used_entry["vision_model"])
    tags_service.replace_scored_tags(engine, file_row.id, scored_tags)
    return f"{len(scored_tags)} tag(s) assigned"


def _log_tag_scores(
    engine, job_id: str, file_row, ranked_top: list[tuple[dict, int]],
    provider_type: str | None = None, model_name: str | None = None,
) -> None:
    """Logs each assigned tag with its match weight (user request -- make it
    visible in the log how well the model thought each tag fit), as a
    percentage the same way `FileInfoPanel.tsx`/`LibraryCards.tsx` already
    display `file_tags.score` in the UI. Also names the provider/model that
    produced the scores (user request -- make it clear in the job log which
    provider/model a tagging request went to)."""
    summary = ", ".join(f"{tag['display_name']} {score}%" for tag, score in ranked_top) or "no tags matched"
    via = f" via {provider_type}/{model_name}" if provider_type else ""
    service.log_event(
        engine, job_id, file_row.id, "info", "job_item_tags",
        f"Tags for {file_row.relative_path}{via}: {summary}",
    )


def run_tag_job(engine, job: dict) -> tuple[str, str]:
    from app.jobs import tag_batch

    pending_submission = batch_submissions.get_pending_for_job(engine, job["id"])
    if pending_submission is not None:
        entries = [entry for entry in provider_entries.list_entries(engine) if entry["enabled"]]
        dead_entries: set[str] = set()
        with engine.connect() as conn:
            source_row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()
        if source_row is None:
            raise RuntimeError("No active source is configured.")
        access = get_source_access(source_row)
        return tag_batch.resume_directory_scope(engine, job, access, entries, dead_entries, pending_submission)

    entries = [entry for entry in provider_entries.list_entries(engine) if entry["enabled"]]
    if not entries:
        raise RuntimeError("No AI provider is enabled. Configure one in Settings first.")
    dead_entries = set()

    vocabulary = tags_service.list_tags(engine, active_only=True)
    if not vocabulary:
        raise RuntimeError("Tag vocabulary is empty; add tags in settings before tagging.")

    settings = tagging_settings.get_settings(engine)

    with engine.connect() as conn:
        source_row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()
    if source_row is None:
        raise RuntimeError("No active source is configured.")
    access = get_source_access(source_row)

    params = job["parameters"] or {}
    if job["scope_type"] == "file":
        return _run_file_scope(engine, job, access, params, vocabulary, settings, entries, dead_entries)
    return _run_directory_scope(engine, job, access, params, vocabulary, settings, entries, dead_entries)


def _run_file_scope(
    engine, job: dict, access: SourceAccess, params: dict, vocabulary: list[dict], settings: dict,
    entries: list[dict], dead_entries: set[str],
) -> tuple[str, str]:
    file_id = params.get("file_id")
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM files WHERE id = :id"), {"id": file_id}).fetchone()
    if row is None:
        raise RuntimeError("File not found.")

    item_id = service.create_job_item(engine, job["id"], file_id=row.id, step_name="tag_file")
    service.start_job_item(engine, item_id)
    try:
        message = _tag_one_file(engine, access, row, vocabulary, settings, entries, dead_entries, job["id"])
        service.complete_job_item(engine, item_id, output_ref=None, message=message)
        service.log_event(engine, job["id"], row.id, "info", "job_item_completed", f"Tagged {row.relative_path}: {message}")
        return "completed", message
    except Exception as exc:  # noqa: BLE001 - failure is reported through the job, not raised further
        service.fail_job_item(engine, item_id, message=str(exc))
        service.log_event(
            engine, job["id"], row.id, "error", "job_item_failed", f"Failed to tag {row.relative_path}: {exc}"
        )
        return "failed", str(exc)


def _process_pending_file(
    engine, job: dict, access: SourceAccess, row, item_id: str, vocabulary: list[dict], settings: dict,
    entries: list[dict], dead_entries: set[str],
) -> bool:
    """Runs the synchronous per-file tagging path (full fallback chain over
    `entries`) for one already-created job item. Returns whether it
    succeeded, so callers can update their own processed/failed counters."""
    service.start_job_item(engine, item_id)
    try:
        message = _tag_one_file(engine, access, row, vocabulary, settings, entries, dead_entries, job["id"])
        service.complete_job_item(engine, item_id, output_ref=None, message=message)
        service.log_event(
            engine, job["id"], row.id, "info", "job_item_completed", f"Tagged {row.relative_path}: {message}"
        )
        return True
    except Exception as exc:  # noqa: BLE001 - one file's failure must not abort the job
        service.fail_job_item(engine, item_id, message=str(exc))
        service.log_event(
            engine, job["id"], row.id, "error", "job_item_failed", f"Failed to tag {row.relative_path}: {exc}"
        )
        return False


def _run_directory_scope(
    engine, job: dict, access: SourceAccess, params: dict, vocabulary: list[dict], settings: dict,
    entries: list[dict], dead_entries: set[str],
) -> tuple[str, str]:
    from app.jobs import tag_batch

    relative_path = params.get("path", "") or ""
    skip_processed = params.get("skip_processed", True)

    with engine.connect() as conn:
        source_id = conn.execute(text("SELECT id FROM sources WHERE is_active = 1 LIMIT 1")).fetchone().id

        clauses = ["source_id = :sid", "(is_video_supported = 1 OR is_image_supported = 1)"]
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

    # Batch tagging (Specification §12.3, Stage 9, `app/jobs/tag_batch.py`)
    # needs the whole pending set up front (one provider request for many
    # files), unlike the lazy create-then-process loop below. Batch mode
    # only ever tries the single highest-priority entry that is enabled,
    # `batch_enabled`, and whose provider type actually supports batch --
    # everything the batch pass doesn't resolve (submission failure,
    # missing/unparseable per-file result, or no batch-capable entry at
    # all) falls through to the ordinary per-file loop below, which runs
    # the *full* fallback chain over every enabled entry, so a wrong
    # assumption about the batch API never loses a file's tags -- it just
    # costs what a non-batch run would have cost anyway.
    remaining: list[tuple] | None = None
    batch_entry = next(
        (e for e in entries if e["batch_enabled"] and registry.entry_supports_batch(e)), None
    )
    if batch_entry is not None:
        pending: list[tuple] = []
        for row in candidates:
            stop = service.check_stop_requested(job["id"])
            if stop:
                stop_status = "cancelled" if stop == "cancel" else "paused"
                break

            item_id = service.create_job_item(engine, job["id"], file_id=row.id, step_name="tag_file")

            if skip_processed and row.tagged_at:
                service.skip_job_item(engine, item_id, "Already tagged; skipped.")
                service.log_event(
                    engine, job["id"], row.id, "debug", "job_item_skipped",
                    f"Skipped {row.relative_path} (already tagged).",
                )
                skipped += 1
                continue

            pending.append((row, item_id))

        if stop_status is None and pending:
            batch_processed, pending, batch_stop_status = tag_batch.run_batch(
                engine, job, access, pending, vocabulary, settings, batch_entry, dead_entries
            )
            processed += batch_processed
            if batch_stop_status is not None:
                stop_status = batch_stop_status

        remaining = pending

    if remaining is not None and stop_status is None:
        for row, item_id in remaining:
            stop = service.check_stop_requested(job["id"])
            if stop:
                stop_status = "cancelled" if stop == "cancel" else "paused"
                break
            if _process_pending_file(engine, job, access, row, item_id, vocabulary, settings, entries, dead_entries):
                processed += 1
            else:
                failed += 1
    elif remaining is None:
        for row in candidates:
            stop = service.check_stop_requested(job["id"])
            if stop:
                stop_status = "cancelled" if stop == "cancel" else "paused"
                break

            item_id = service.create_job_item(engine, job["id"], file_id=row.id, step_name="tag_file")

            if skip_processed and row.tagged_at:
                service.skip_job_item(engine, item_id, "Already tagged; skipped.")
                service.log_event(
                    engine, job["id"], row.id, "debug", "job_item_skipped",
                    f"Skipped {row.relative_path} (already tagged).",
                )
                skipped += 1
                continue

            if _process_pending_file(engine, job, access, row, item_id, vocabulary, settings, entries, dead_entries):
                processed += 1
            else:
                failed += 1

    if stop_status is not None:
        verb = "Cancelled" if stop_status == "cancelled" else "Paused"
        event = "job_cancel_honored" if stop_status == "cancelled" else "job_pause_honored"
        message = f"{verb} after {processed} of {total} file(s)."
        service.log_event(engine, job["id"], None, "info", event, message)
        return stop_status, message

    summary = f"Tagged {processed} of {total} file(s)"
    if skipped:
        summary += f", {skipped} skipped"
    if failed:
        summary += f", {failed} failed"

    status = "failed" if failed and processed == 0 and total > 0 else "completed"
    return status, summary
