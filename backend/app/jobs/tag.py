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
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app import provider_entries, tagging, tagging_settings, tags as tags_service
from app.jobs import service
from app.media import is_test_artifact
from app.providers import registry
from app.sources import SourceAccess, get_source_access


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assign_tags(engine, file_id: str, scored_tags: list[dict], provider_type: str, model_name: str | None) -> None:
    now = _now()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM file_tags WHERE file_id = :file_id"), {"file_id": file_id})
        for entry in scored_tags:
            conn.execute(
                text(
                    """
                    INSERT INTO file_tags (id, file_id, tag_id, score, provider_name, model_name, assigned_at)
                    VALUES (:id, :file_id, :tag_id, :score, :provider_name, :model_name, :now)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "file_id": file_id,
                    "tag_id": entry["id"],
                    "score": entry["score"],
                    "provider_name": provider_type,
                    "model_name": model_name,
                    "now": now,
                },
            )
        conn.execute(
            text("UPDATE files SET tagged_at = :now, updated_at = :now WHERE id = :id"),
            {"now": now, "id": file_id},
        )


def _tag_one_file(
    engine, access: SourceAccess, file_row, vocabulary: list[dict], settings: dict,
    entries: list[dict], dead_entries: set[str],
) -> str:
    if not access.exists(file_row.relative_path):
        raise RuntimeError("Source file no longer exists on the source.")

    with access.local_copy(file_row.relative_path) as video_path:
        images = tagging.build_tagging_images(
            video_path, settings["sample_frame_count"], settings["combine_into_collage"]
        )
    display_names = [tag["display_name"] for tag in vocabulary]
    scores, used_entry = registry.score_tags_with_fallback(engine, entries, images, display_names, dead_entries)

    ranked = sorted(zip(vocabulary, scores), key=lambda pair: pair[1], reverse=True)
    top = ranked[: settings["top_tag_count"]]
    scored_tags = [{"id": tag["id"], "score": score} for tag, score in top]

    _assign_tags(engine, file_row.id, scored_tags, used_entry["provider_type"], used_entry["vision_model"])
    return f"{len(scored_tags)} tag(s) assigned"


def run_tag_job(engine, job: dict) -> tuple[str, str]:
    entries = [entry for entry in provider_entries.list_entries(engine) if entry["enabled"]]
    if not entries:
        raise RuntimeError("No AI provider is enabled. Configure one in Settings first.")
    dead_entries: set[str] = set()

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
        message = _tag_one_file(engine, access, row, vocabulary, settings, entries, dead_entries)
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
        message = _tag_one_file(engine, access, row, vocabulary, settings, entries, dead_entries)
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
    service.set_job_total_items(engine, job["id"], total)

    # Batch tagging (Specification §12.3, Stage 9) needs the whole pending
    # set up front (one provider request for many files), unlike the
    # lazy create-then-process loop below. Batch mode only ever tries the
    # single highest-priority entry that is enabled, `batch_enabled`, and
    # whose provider type actually supports batch -- everything the batch
    # pass doesn't resolve (submission failure, missing/unparseable
    # per-file result, or no batch-capable entry at all) falls through to
    # the ordinary per-file loop below, which runs the *full* fallback
    # chain over every enabled entry, so a wrong assumption about the batch
    # API never loses a file's tags -- it just costs what a non-batch run
    # would have cost anyway.
    remaining: list[tuple] | None = None
    batch_entry = next(
        (e for e in entries if e["batch_enabled"] and registry.entry_supports_batch(e)), None
    )
    if batch_entry is not None:
        pending: list[tuple] = []
        for row in candidates:
            if service.is_cancel_requested(job["id"]):
                cancelled = True
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

        if not cancelled and pending:
            batch_processed, pending = _run_batch(
                engine, job, access, pending, vocabulary, settings, batch_entry, dead_entries
            )
            processed += batch_processed

        remaining = pending

    if remaining is not None:
        for row, item_id in remaining:
            if service.is_cancel_requested(job["id"]):
                cancelled = True
                break
            if _process_pending_file(engine, job, access, row, item_id, vocabulary, settings, entries, dead_entries):
                processed += 1
            else:
                failed += 1
    else:
        for row in candidates:
            if service.is_cancel_requested(job["id"]):
                cancelled = True
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

    if cancelled:
        message = f"Cancelled after {processed} of {total} file(s)."
        service.log_event(engine, job["id"], None, "info", "job_cancel_honored", message)
        return "cancelled", message

    summary = f"Tagged {processed} of {total} file(s)"
    if skipped:
        summary += f", {skipped} skipped"
    if failed:
        summary += f", {failed} failed"

    status = "failed" if failed and processed == 0 and total > 0 else "completed"
    return status, summary


def _run_batch(
    engine, job: dict, access: SourceAccess, pending: list[tuple], vocabulary: list[dict], settings: dict,
    batch_entry: dict, dead_entries: set[str],
) -> tuple[int, list[tuple]]:
    """Attempts to score every `(row, item_id)` in `pending` via one
    `batch_entry` batch request. Returns `(processed_count,
    fallback_pending)`: files the batch pass didn't resolve are returned
    untouched (item still `queued`) so the caller's per-file fallback loop
    picks them up next."""
    display_names = [tag["display_name"] for tag in vocabulary]
    items: list[tuple[str, list[bytes]]] = []
    keyed_rows: dict[str, tuple] = {}
    # Rows not (yet) turned into a batch `items` entry -- unprepped because of
    # a cancel request or a per-file prep failure -- always end up back here,
    # so the caller's per-file loop (which itself checks cancellation first)
    # is the single place that ever "loses track" of a pending row.
    unresolved: list[tuple] = []

    for row, item_id in pending:
        if service.is_cancel_requested(job["id"]):
            unresolved.append((row, item_id))
            continue

        service.start_job_item(engine, item_id)
        try:
            if not access.exists(row.relative_path):
                raise RuntimeError("Source file no longer exists on the source.")
            with access.local_copy(row.relative_path) as video_path:
                images = tagging.build_tagging_images(
                    video_path, settings["sample_frame_count"], settings["combine_into_collage"]
                )
            items.append((row.id, images))
            keyed_rows[row.id] = (row, item_id)
        except Exception as exc:  # noqa: BLE001 - this file just falls back to the per-file loop
            service.log_event(
                engine, job["id"], row.id, "warning", "job_item_batch_prep_failed",
                f"Could not prepare {row.relative_path} for batch tagging, will retry per-file: {exc}",
            )
            unresolved.append((row, item_id))

    if not items:
        return 0, unresolved

    try:
        service.log_event(
            engine, job["id"], None, "info", "batch_submitted",
            f"Submitting {len(items)} file(s) to {batch_entry['display_name']} for batch tagging.",
        )
        results = registry.score_tags_batch_with_entry(engine, batch_entry, items, display_names)
    except Exception as exc:  # noqa: BLE001 - batch failure falls back to the per-file loop for every file
        dead_entries.add(batch_entry["id"])
        service.log_event(
            engine, job["id"], None, "warning", "batch_failed",
            f"Batch submission to {batch_entry['display_name']} failed, falling back to per-file tagging: {exc}",
        )
        return 0, unresolved + [keyed_rows[key] for key, _images in items]

    processed = 0
    fallback_pending: list[tuple] = list(unresolved)
    for key, _images in items:
        row, item_id = keyed_rows[key]
        scores = results.get(key)
        if scores is None:
            fallback_pending.append((row, item_id))
            continue
        try:
            ranked = sorted(zip(vocabulary, scores), key=lambda pair: pair[1], reverse=True)
            top = ranked[: settings["top_tag_count"]]
            scored_tags = [{"id": tag["id"], "score": score} for tag, score in top]
            _assign_tags(engine, row.id, scored_tags, batch_entry["provider_type"], batch_entry["vision_model"])
            message = f"{len(scored_tags)} tag(s) assigned (batch)"
            service.complete_job_item(engine, item_id, output_ref=None, message=message)
            service.log_event(
                engine, job["id"], row.id, "info", "job_item_completed", f"Tagged {row.relative_path}: {message}"
            )
            processed += 1
        except Exception:  # noqa: BLE001 - fall back to a per-file attempt for this one file
            fallback_pending.append((row, item_id))

    return processed, fallback_pending
