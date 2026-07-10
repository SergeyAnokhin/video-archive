"""Batch-tagging orchestration (Specification §12.3, Stage 9): submits a
directory scope's still-pending files to a single batch-capable provider
entry in one request, persists the submission (`app/batch_submissions.py`)
before polling starts, and polls every `BATCH_POLL_INTERVAL_SECONDS` (user
request -- "the batch task should survive a service restart") rather than
blocking in a single provider call.

If the process restarts mid-poll, `app/main.py`'s startup calls
`batch_submissions.requeue_stalled_jobs()`, which puts the job back on the
queue; `app.jobs.tag.run_tag_job()`'s very first check is whether a pending
submission already exists for it, in which case it routes here
(`resume_directory_scope()`) instead of re-scanning the directory and
submitting a new batch.

Everything the batch pass doesn't resolve (submission failure, missing/
unparseable per-file result, or no batch-capable entry at all) falls back to
`app.jobs.tag`'s ordinary per-file loop, which runs the *full* fallback
chain over every enabled entry, so a wrong assumption about the batch API
never loses a file's tags -- it just costs what a non-batch run would have
cost anyway.
"""

from __future__ import annotations

import json
import time

from sqlalchemy import text

from app import batch_submissions, provider_entries, tagging, tagging_settings, tags as tags_service
from app.jobs import service
from app.jobs.tag import _assign_tags, _log_tag_scores, _process_pending_file
from app.providers import registry
from app.providers.base import BatchPollResult, ProviderError
from app.sources import SourceAccess

# How often a batch submission is re-checked, and how long it may stay
# unresolved before this app gives up on it entirely (a safety net -- a
# real provider batch is expected to finish in minutes, not days). Both are
# orchestration-level concerns now, not the provider client's, since the
# client only does one status check per call (`registry.poll_batch_with_entry`).
BATCH_POLL_INTERVAL_SECONDS = 30
BATCH_POLL_TIMEOUT_SECONDS = 24 * 60 * 60


def run_batch(
    engine, job: dict, access: SourceAccess, pending: list[tuple], vocabulary: list[dict], settings: dict,
    batch_entry: dict, dead_entries: set[str],
) -> tuple[int, list[tuple], str | None]:
    """Prepares every `(row, item_id)` in `pending` and submits them as one
    `batch_entry` batch request, persisting it (`app/batch_submissions.py`)
    before polling so it survives a restart, then polls until resolved.
    Returns `(processed_count, fallback_pending, stop_status)`:
    `fallback_pending` covers both files the batch pass didn't resolve and,
    on a submission-wide failure, every file that was in the batch;
    `stop_status` is `'cancelled'`/`'paused'`/`None` (the job was
    paused/cancelled while polling -- the submission is left `polling` for
    a future resume, see `_poll_until_resolved()`)."""
    display_names = [tag["display_name"] for tag in vocabulary]
    items: list[tuple[str, list[bytes]]] = []
    keyed_rows: dict[str, tuple] = {}
    # Rows not (yet) turned into a batch `items` entry -- unprepped because of
    # a cancel request or a per-file prep failure -- always end up back here,
    # so the caller's per-file loop (which itself checks cancellation first)
    # is the single place that ever "loses track" of a pending row.
    unresolved: list[tuple] = []

    for row, item_id in pending:
        if service.check_stop_requested(job["id"]):
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
        return 0, unresolved, None

    try:
        service.log_event(
            engine, job["id"], None, "info", "batch_submitted",
            f"Submitting {len(items)} file(s) to {batch_entry['display_name']} for batch tagging.",
        )
        external_batch_id = registry.create_batch_with_entry(engine, batch_entry, items, display_names)
    except Exception as exc:  # noqa: BLE001 - submission failure falls back to the per-file loop for every file
        dead_entries.add(batch_entry["id"])
        service.log_event(
            engine, job["id"], None, "warning", "batch_failed",
            f"Batch submission to {batch_entry['display_name']} failed, falling back to per-file tagging: {exc}",
        )
        return 0, unresolved + list(keyed_rows.values()), None

    submission = batch_submissions.create_submission(
        engine,
        job_id=job["id"],
        provider_entry_id=batch_entry["id"],
        provider_type=batch_entry["provider_type"],
        model_name=batch_entry["vision_model"],
        external_batch_id=external_batch_id,
        tag_ids=[tag["id"] for tag in vocabulary],
        top_tag_count=settings["top_tag_count"],
        items=[
            {"file_id": row.id, "item_id": item_id, "relative_path": row.relative_path}
            for row, item_id in keyed_rows.values()
        ],
    )

    item_map = {row.id: item_id for row, item_id in keyed_rows.values()}
    processed, fallback_pending, stop_status = _poll_and_apply(engine, job, submission, vocabulary, item_map, dead_entries)
    return processed, unresolved + fallback_pending, stop_status


def resume_directory_scope(
    engine, job: dict, access: SourceAccess, entries: list[dict], dead_entries: set[str], submission: dict,
) -> tuple[str, str]:
    """Continues a directory-scope tag job whose batch submission was still
    `polling` when this process last stopped (`batch_submissions.
    requeue_stalled_jobs()` put the job back on the queue for this;
    `app.jobs.tag.run_tag_job()` routes here instead of re-scanning the
    directory). Vocabulary and top-tag-count come back from the
    submission's own snapshot rather than the live settings, so scores
    realign correctly even if the vocabulary changed while the batch was in
    flight."""
    tag_ids = json.loads(submission["tag_ids_json"])
    vocabulary = tags_service.list_tags_by_ids(engine, tag_ids)
    settings = tagging_settings.get_settings(engine)
    item_map = {item["file_id"]: item["item_id"] for item in json.loads(submission["items_json"])}

    _processed, fallback_pending, stop_status = _poll_and_apply(
        engine, job, submission, vocabulary, item_map, dead_entries
    )

    if stop_status is None:
        for row, item_id in fallback_pending:
            stop = service.check_stop_requested(job["id"])
            if stop:
                stop_status = "cancelled" if stop == "cancel" else "paused"
                break
            _process_pending_file(engine, job, access, row, item_id, vocabulary, settings, entries, dead_entries)

    return _finalize_from_job_items(engine, job["id"], stop_status)


def _job_item_status_counts(engine, job_id: str) -> dict[str, int]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT status, COUNT(*) AS c FROM job_items WHERE job_id = :jid GROUP BY status"),
            {"jid": job_id},
        ).all()
    return {row.status: row.c for row in rows}


def _finalize_from_job_items(engine, job_id: str, stop_status: str | None) -> tuple[str, str]:
    """Same summary format `app.jobs.tag._run_directory_scope()`'s tail
    produces, but computed from persisted `job_items` rather than in-memory
    counters -- only the resume path needs this, since its counters
    (skipped/processed from *before* the restart) no longer exist in Python
    state, only in the database."""
    counts = _job_item_status_counts(engine, job_id)
    job = service.get_job(engine, job_id) or {}
    total = job.get("total_items") or 0
    processed = counts.get("completed", 0)
    skipped = counts.get("skipped", 0)
    failed = counts.get("failed", 0)

    if stop_status is not None:
        verb = "Cancelled" if stop_status == "cancelled" else "Paused"
        event = "job_cancel_honored" if stop_status == "cancelled" else "job_pause_honored"
        message = f"{verb} after {processed} of {total} file(s)."
        service.log_event(engine, job_id, None, "info", event, message)
        return stop_status, message

    summary = f"Tagged {processed} of {total} file(s)"
    if skipped:
        summary += f", {skipped} skipped"
    if failed:
        summary += f", {failed} failed"
    status = "failed" if failed and processed == 0 and total > 0 else "completed"
    return status, summary


def _fetch_file_rows(engine, file_ids: list[str]) -> dict[str, object]:
    if not file_ids:
        return {}
    placeholders = ", ".join(f":id_{i}" for i in range(len(file_ids)))
    params = {f"id_{i}": file_id for i, file_id in enumerate(file_ids)}
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT * FROM files WHERE id IN ({placeholders})"), params).all()
    return {row.id: row for row in rows}


def _poll_and_apply(
    engine, job: dict, submission: dict, vocabulary: list[dict | None], item_map: dict[str, str],
    dead_entries: set[str],
) -> tuple[int, list[tuple], str | None]:
    """Polls `submission` until it resolves or this job is paused/cancelled
    (`_poll_until_resolved()`), then applies `_assign_tags()` for every file
    the batch actually scored. `vocabulary` may contain `None` entries (a
    tag deleted since submission, only possible on the resume path, which
    rebuilds it from an id snapshot) -- those are filtered out of the
    per-file ranking, keeping the rest positionally aligned with `scores`
    rather than raising. Returns `(processed_count, fallback_pending,
    stop_status)`, the same shape `run_batch()` returns."""
    display_names = [tag["display_name"] if tag else None for tag in vocabulary]
    stop_type, poll_result = _poll_until_resolved(engine, job, submission, display_names)
    if stop_type in ("cancel", "pause"):
        return 0, [], ("cancelled" if stop_type == "cancel" else "paused")

    assert poll_result is not None  # only None alongside a cancel/pause stop_type, handled above
    file_rows = _fetch_file_rows(engine, list(item_map.keys()))
    fallback_pending: list[tuple] = []
    processed = 0

    if poll_result.error:
        dead_entries.add(submission["provider_entry_id"])
        service.log_event(
            engine, job["id"], None, "warning", "batch_failed",
            f"Batch tagging failed, falling back to per-file tagging: {poll_result.error}",
        )
        for file_id, item_id in item_map.items():
            row = file_rows.get(file_id)
            if row is not None:
                fallback_pending.append((row, item_id))
            else:
                service.fail_job_item(engine, item_id, message="File no longer exists.")
        return 0, fallback_pending, None

    for file_id, item_id in item_map.items():
        row = file_rows.get(file_id)
        if row is None:
            service.fail_job_item(engine, item_id, message="File no longer exists.")
            continue
        scores = poll_result.results.get(file_id) if poll_result.results else None
        if scores is None:
            fallback_pending.append((row, item_id))
            continue
        try:
            ranked = sorted(
                ((tag, score) for tag, score in zip(vocabulary, scores) if tag is not None),
                key=lambda pair: pair[1], reverse=True,
            )
            top = ranked[: submission["top_tag_count"]]
            scored_tags = [{"id": tag["id"], "score": score} for tag, score in top]
            _log_tag_scores(engine, job["id"], row, top)
            _assign_tags(engine, row.id, scored_tags, submission["provider_type"], submission["model_name"])
            message = f"{len(scored_tags)} tag(s) assigned (batch)"
            service.complete_job_item(engine, item_id, output_ref=None, message=message)
            service.log_event(
                engine, job["id"], row.id, "info", "job_item_completed", f"Tagged {row.relative_path}: {message}"
            )
            processed += 1
        except Exception:  # noqa: BLE001 - fall back to a per-file attempt for this one file
            fallback_pending.append((row, item_id))

    return processed, fallback_pending, None


def _interruptible_sleep(job_id: str, total_seconds: float) -> None:
    """Sleeps up to `total_seconds`, but wakes early (in <=1s granularity)
    if a pause/cancel gets requested, so a 30-second poll interval doesn't
    make cancel/pause feel unresponsive."""
    remaining = total_seconds
    while remaining > 0:
        if service.check_stop_requested(job_id):
            return
        step = min(1.0, remaining)
        time.sleep(step)
        remaining -= step


def _poll_until_resolved(
    engine, job: dict, submission: dict, tags: list[str | None],
) -> tuple[str, BatchPollResult | None]:
    """Polls the persisted `submission` every `BATCH_POLL_INTERVAL_SECONDS`
    until it resolves (succeeds or fails at the provider) or this job is
    paused/cancelled -- checked every second in between so a stop request
    doesn't wait out the whole interval. Returns `("resolved",
    BatchPollResult)` -- also for a "forgotten" submission (user request,
    the batch-jobs modal's "forget locally" button), reported as a resolved
    error so the caller falls back to per-file tagging, the same as any
    other batch failure -- or `("cancel"|"pause", None)` with the
    submission left exactly as it was (still `polling`) for a future
    resume."""
    entry = provider_entries.get_entry(engine, submission["provider_entry_id"])
    if entry is None:
        batch_submissions.mark_resolved(
            engine, submission["id"], batch_submissions.STATUS_FAILED, "Provider entry no longer exists."
        )
        return "resolved", BatchPollResult(done=True, error="Provider entry no longer exists.")

    ordered_keys = [item["file_id"] for item in json.loads(submission["items_json"])]
    deadline = time.monotonic() + BATCH_POLL_TIMEOUT_SECONDS

    while True:
        stop = service.check_stop_requested(job["id"])
        if stop:
            return stop, None

        current = batch_submissions.get_submission(engine, submission["id"])
        if current is None or current["status"] != batch_submissions.STATUS_POLLING:
            return "resolved", BatchPollResult(done=True, error="Batch submission was forgotten locally.")

        try:
            result = registry.poll_batch_with_entry(
                engine, entry, submission["external_batch_id"], ordered_keys, tags, job_id=job["id"]
            )
        except ProviderError as exc:
            batch_submissions.mark_resolved(engine, submission["id"], batch_submissions.STATUS_FAILED, str(exc))
            return "resolved", BatchPollResult(done=True, error=str(exc))

        if result.done:
            status = batch_submissions.STATUS_FAILED if result.error else batch_submissions.STATUS_SUCCEEDED
            batch_submissions.mark_resolved(engine, submission["id"], status, result.error)
            return "resolved", result

        if time.monotonic() > deadline:
            timeout_message = "Batch polling safety timeout elapsed."
            batch_submissions.mark_resolved(engine, submission["id"], batch_submissions.STATUS_FAILED, timeout_message)
            return "resolved", BatchPollResult(done=True, error=timeout_message)

        _interruptible_sleep(job["id"], BATCH_POLL_INTERVAL_SECONDS)
