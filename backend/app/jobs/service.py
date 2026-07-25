"""Job/job-item CRUD, state machine transitions, and the event log (Job Model,
Data Model §6-7, §11). Called both from request handlers (create/list/cancel/
etc.) and from the background worker thread (`app/jobs/worker.py`), so every
write here is its own short transaction rather than one held across a
request's whole lifetime.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath

from sqlalchemy import bindparam, text

logger = logging.getLogger(__name__)

FINISHED_STATUSES = ("completed", "failed", "cancelled")

_FINISH_EVENT_TYPES = {
    "completed": "job_completed",
    "failed": "job_failed",
    "cancelled": "job_cancelled",
}

# See `log_event()`'s console-mirroring note below.
_CONSOLE_INFO_EVENT_TYPES = frozenset(
    {
        "job_item_started", "job_item_progress", "job_force_cancelled", "job_force_abandoned", "job_item_tags",
        "batch_poll_check", "job_parameters",
    }
)


class JobConflictError(Exception):
    """Raised when a requested transition isn't valid for the job's current status."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- per-job file numbering (user request) ----------------------------------
# Assigns each file a small, stable, per-job sequential number the first time
# it appears in that job's event log -- in-memory only, like the cancel/pause
# registries below, so it doesn't need to survive a restart. Lets a fast
# multi-file job's console/Log Viewer output stay readable ("[#3] ..."
# instead of a bare file UUID) and lets the Log Viewer filter by clicking
# that number instead of typing a file id by hand (`payload.file_index`,
# read by `LogViewerModal.tsx`).

_file_index_lock = threading.Lock()
_file_index_by_job: dict[str, dict[str, int]] = {}


def _next_file_index(job_id: str, file_id: str) -> int:
    with _file_index_lock:
        indices = _file_index_by_job.setdefault(job_id, {})
        if file_id not in indices:
            indices[file_id] = len(indices) + 1
        return indices[file_id]


def _forget_file_indices(job_id: str) -> None:
    with _file_index_lock:
        _file_index_by_job.pop(job_id, None)


# Purely cosmetic (user request): makes the event type visible at a glance in
# the console and Log Viewer without reading the bracketed event name.
_EVENT_EMOJI = {
    "job_queued": "🕒",
    "job_started": "▶️",
    "job_parameters": "⚙️",
    "job_completed": "✅",
    "job_failed": "❌",
    "job_cancelled": "🛑",
    "job_cancel_requested": "🛑",
    "job_cancel_honored": "🛑",
    "job_force_cancelled": "🔨",
    "job_force_abandoned": "🔨",
    "job_paused": "⏸️",
    "job_pause_requested": "⏸️",
    "job_pause_honored": "⏸️",
    "job_resumed": "▶️",
    "job_item_started": "▶️",
    "job_item_progress": "⏳",
    "job_item_completed": "✅",
    "job_item_failed": "❌",
    "job_item_skipped": "⏭️",
    "job_item_tags": "🏷️",
    "job_item_batch_prep_failed": "⚠️",
    "batch_submitted": "📦",
    "batch_failed": "⚠️",
    "batch_poll_check": "🔄",
    "batch_usage": "🔢",
    "job_item_raw_response": "📄",
}


# --- cooperative cancellation registry -------------------------------------
# Cancelling a *running* job can't just flip a DB column: the worker thread
# owns the job while it executes and must notice the request between items
# (Job Model "Cancellation Rules"). A queued job has no worker attached yet,
# so it can be cancelled directly (see cancel_job below).

_cancel_requested: set[str] = set()
_cancel_lock = threading.Lock()


def request_cancel(job_id: str) -> None:
    with _cancel_lock:
        _cancel_requested.add(job_id)


def is_cancel_requested(job_id: str) -> bool:
    with _cancel_lock:
        return job_id in _cancel_requested


def clear_cancel_request(job_id: str) -> None:
    with _cancel_lock:
        _cancel_requested.discard(job_id)


# --- cooperative pause registry ---------------------------------------------
# Same pattern as cancellation above, but resumable: pausing a *running* job
# is a cooperative request the worker notices between items (job handlers
# check both at every checkpoint via `check_stop_requested`); pausing a
# *queued* job (not picked up by a worker yet) can just flip its status
# directly, same as cancel_job's queued branch.

_pause_requested: set[str] = set()
_pause_lock = threading.Lock()

# Job types whose handlers process a list of items with cooperative
# checkpoints between them (see `check_stop_requested` call sites in
# `app/jobs/*.py`). `optimize_db`/`backup`/`restore` run one atomic action
# with no per-item loop, so pausing them wouldn't do anything until that
# single action finishes anyway -- excluded here so `pause_job` rejects them
# with a clear error instead of silently no-op'ing.
PAUSABLE_JOB_TYPES = frozenset(
    {"rescan", "rescan_with_media_info", "convert", "preview", "tag", "cleanup", "migrate_legacy_previews"}
)


def request_pause(job_id: str) -> None:
    with _pause_lock:
        _pause_requested.add(job_id)


def is_pause_requested(job_id: str) -> bool:
    with _pause_lock:
        return job_id in _pause_requested


def clear_pause_request(job_id: str) -> None:
    with _pause_lock:
        _pause_requested.discard(job_id)


def check_stop_requested(job_id: str) -> str | None:
    """Returns `"cancel"`/`"pause"` if either was requested for this job, or
    `None` -- the single check every job-handler loop checkpoint uses instead
    of calling `is_cancel_requested`/`is_pause_requested` separately. Cancel
    wins if somehow both are set, since it's the more final of the two."""
    if is_cancel_requested(job_id):
        return "cancel"
    if is_pause_requested(job_id):
        return "pause"
    return None


# --- sliding-window concurrent item processing ------------------------------


def run_sliding_window(
    job_id: str,
    worker_count: int,
    next_item: Callable[[], object | None],
    process_one: Callable[[object], object],
) -> tuple[list, str | None]:
    """Run `process_one(item)` for a stream of items on a thread pool capped
    at `worker_count` concurrent in-flight tasks, submitting the next item as
    soon as a slot frees up (post-V1, user request) instead of the previous
    "collect a batch of `worker_count`, run it, wait for all of it to finish,
    collect the next batch" approach used by `app/jobs/preview.py` and
    `app/jobs/convert.py`'s directory-scope loops -- that left up to
    `worker_count - 1` threads idle at the tail of every batch on a directory
    with a mix of short and long files.

    `next_item()` is called from the calling thread (never from a worker)
    each time a submission slot is free, and returns the next item to submit
    or `None` when there is nothing left to submit right now (permanently
    ending the run -- there is no "try again later"). Since it always runs
    synchronously between submissions rather than inside a worker thread, a
    caller can fold "skip already-processed items" bookkeeping into it (log
    the skip, then continue its own internal loop to the next candidate)
    without consuming a worker slot for skipped items.

    Cooperative cancel/pause (`check_stop_requested`) is checked before every
    submission -- finer-grained than the old between-batches check, though
    coarser than per-completion when several slots free up in a burst.
    Items already in flight when a stop is requested are always allowed to
    finish rather than being interrupted.

    Returns `(results, stop_status)`: `results` holds every `process_one`
    return value for items that were actually submitted, in completion order
    (not submission order -- callers here only ever aggregate counts/bytes
    from it, order doesn't matter); `stop_status` is `"cancel"`/`"pause"`/
    `None`.
    """
    results: list = []
    stop_status: str | None = None

    with ThreadPoolExecutor(max_workers=max(1, worker_count)) as executor:
        in_flight: set = set()

        def try_submit() -> bool:
            nonlocal stop_status
            if stop_status is not None:
                return False
            stop = check_stop_requested(job_id)
            if stop:
                stop_status = stop
                return False
            item = next_item()
            if item is None:
                return False
            in_flight.add(executor.submit(process_one, item))
            return True

        for _ in range(max(1, worker_count)):
            if not try_submit():
                break

        while in_flight:
            done, in_flight = wait(in_flight, return_when=FIRST_COMPLETED)
            for future in done:
                results.append(future.result())
            for _ in range(len(done)):
                if not try_submit():
                    break

    return results, stop_status


# --- row <-> dict mapping ----------------------------------------------------


def _job_row_to_dict(row, failed_item_count: int = 0) -> dict:
    return {
        "id": row.id,
        "job_type": row.job_type,
        "scope_type": row.scope_type,
        "scope_ref": row.scope_ref,
        "scope_label": None,
        "status": row.status,
        "parameters": json.loads(row.parameters) if row.parameters else {},
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "summary_message": row.summary_message,
        "total_items": row.total_items,
        "failed_item_count": failed_item_count,
        "interrupted": bool(row.interrupted),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _count_failed_items(engine, job_ids: list[str]) -> dict[str, int]:
    """Per-job count of failed `job_items` (user-requested visibility into
    how many items errored during a job), batched for `list_jobs` so
    rendering the jobs list doesn't issue one query per job."""
    if not job_ids:
        return {}
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT job_id, COUNT(*) AS failed_count FROM job_items "
                "WHERE job_id IN :ids AND status = 'failed' GROUP BY job_id"
            ).bindparams(bindparam("ids", expanding=True)),
            {"ids": job_ids},
        ).all()
    return {row.job_id: row.failed_count for row in rows}


def _resolve_scope_labels(engine, jobs: list[dict]) -> dict[str, str]:
    """Post-V1, user request: a file-scope job's `scope_ref` is the file's
    id, which the Jobs modal would otherwise have no choice but to show
    verbatim (a raw UUID) -- this resolves it to the file's current
    `relative_path` so the card can show a name/path instead, batched here
    (like `_count_failed_items`) so rendering the jobs list doesn't issue one
    query per job. Directory-scope jobs need no resolution: `scope_ref` is
    already the directory's relative path."""
    file_ids = [job["scope_ref"] for job in jobs if job["scope_type"] == "file" and job["scope_ref"]]
    if not file_ids:
        return {}
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, relative_path FROM files WHERE id IN :ids").bindparams(
                bindparam("ids", expanding=True)
            ),
            {"ids": file_ids},
        ).all()
    path_by_file_id = {row.id: row.relative_path for row in rows}
    return {
        job["id"]: path_by_file_id[job["scope_ref"]]
        for job in jobs
        if job["scope_type"] == "file" and job["scope_ref"] in path_by_file_id
    }


def _job_item_row_to_dict(row) -> dict:
    return {
        "id": row.id,
        "job_id": row.job_id,
        "file_id": row.file_id,
        "item_key": row.item_key,
        "status": row.status,
        "step_name": row.step_name,
        "message": row.message,
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "output_ref": row.output_ref,
        "progress_pct": row.progress_pct,
    }


# --- events -------------------------------------------------------------

# Console/file-log lines only need a human-readable name, not the raw file
# id or a full path (user request) -- `PurePosixPath(...).name` is the same
# idiom used elsewhere for `relative_path` -> basename (e.g.
# `app.routers.directories`). Cached per file id since one file gets many
# `job_item_progress` lines (one per pipeline stage) during a single
# conversion, and a DB lookup on every line would be wasteful.
_file_name_cache_lock = threading.Lock()
_file_name_cache: dict[str, str] = {}


def _resolve_file_name(engine, file_id: str | None) -> str | None:
    if not file_id:
        return None
    with _file_name_cache_lock:
        cached = _file_name_cache.get(file_id)
    if cached is not None:
        return cached
    with engine.connect() as conn:
        row = conn.execute(text("SELECT relative_path FROM files WHERE id = :id"), {"id": file_id}).first()
    name = PurePosixPath(row.relative_path).name if row and row.relative_path else file_id
    with _file_name_cache_lock:
        _file_name_cache[file_id] = name
    return name


def log_event(
    engine,
    job_id: str | None,
    file_id: str | None,
    level: str,
    event_type: str,
    message: str,
    payload: dict | None = None,
) -> None:
    file_index = _next_file_index(job_id, file_id) if job_id and file_id else None
    if file_index is not None:
        message = f"[#{file_index}] {message}"
        payload = {**(payload or {}), "file_index": file_index}
    emoji = _EVENT_EMOJI.get(event_type)
    if emoji:
        message = f"{emoji} {message}"

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO app_events (id, job_id, file_id, level, event_type, message, payload, created_at)
                VALUES (:id, :job_id, :file_id, :level, :event_type, :message, :payload, :now)
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "job_id": job_id,
                "file_id": file_id,
                "level": level,
                "event_type": event_type,
                "message": message,
                "payload": json.dumps(payload) if payload is not None else None,
                "now": _now(),
            },
        )
    # Every job/job-item failure funnels through this function (paired with
    # `fail_job_item`/`finish_job` at every call site), so logging error and
    # warning events here -- rather than at each individual job handler --
    # is what makes background-job failures visible in the terminal running
    # the backend, not just in the DB-backed event log / Log Viewer.
    # `_CONSOLE_INFO_EVENT_TYPES` is a narrow exception (user request): these
    # are exactly the "what is it doing right now" signal needed to diagnose
    # a stuck or slow job from the terminal (`job_item_progress` in
    # particular is the per-stage breakdown -- probing, frame extraction,
    # encoding, rendering -- used to see where a preview/conversion job is
    # actually spending its time), without flooding the console the way
    # printing every `info` event would (e.g. every skipped file in a large
    # rescan).
    # The job id is dropped entirely and the file id resolved to its name
    # (user request: the raw uuids added noise without adding information at
    # a glance).
    should_log_console = level in ("error", "warning") or event_type in _CONSOLE_INFO_EVENT_TYPES
    if should_log_console:
        file_name = _resolve_file_name(engine, file_id)
        line = f"[{event_type}]" + (f" file={file_name}" if file_name else "") + f": {message}"
        if level == "error":
            logger.error(line)
        elif level == "warning":
            logger.warning(line)
        else:
            logger.info(line)


# --- jobs -----------------------------------------------------------------


def create_job(engine, job_type: str, scope_type: str, scope_ref: str | None, parameters: dict) -> dict:
    job_id = str(uuid.uuid4())
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO jobs (id, job_type, scope_type, scope_ref, status, parameters, created_at, updated_at)
                VALUES (:id, :job_type, :scope_type, :scope_ref, 'queued', :parameters, :now, :now)
                """
            ),
            {
                "id": job_id,
                "job_type": job_type,
                "scope_type": scope_type,
                "scope_ref": scope_ref,
                "parameters": json.dumps(parameters),
                "now": now,
            },
        )
    log_event(engine, job_id, None, "info", "job_queued", f"Job queued: {job_type}")
    return get_job(engine, job_id)


def get_job(engine, job_id: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM jobs WHERE id = :id"), {"id": job_id}).fetchone()
    if row is None:
        return None
    failed_count = _count_failed_items(engine, [job_id]).get(job_id, 0)
    job = _job_row_to_dict(row, failed_count)
    job["scope_label"] = _resolve_scope_labels(engine, [job]).get(job_id)
    return job


def list_jobs(
    engine,
    status: str | None = None,
    job_type: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    clauses = []
    params: dict = {"limit": limit, "offset": offset}
    if status:
        clauses.append("status = :status")
        params["status"] = status
    if job_type:
        clauses.append("job_type = :job_type")
        params["job_type"] = job_type
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT * FROM jobs {where_sql} ORDER BY created_at DESC LIMIT :limit OFFSET :offset"
            ),
            params,
        ).all()
    failed_counts = _count_failed_items(engine, [row.id for row in rows])
    jobs = [_job_row_to_dict(row, failed_counts.get(row.id, 0)) for row in rows]
    scope_labels = _resolve_scope_labels(engine, jobs)
    for job in jobs:
        job["scope_label"] = scope_labels.get(job["id"])
    return jobs


def get_current_job_summary(engine) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT * FROM jobs WHERE status IN ('queued', 'running')
                ORDER BY CASE status WHEN 'running' THEN 0 ELSE 1 END, created_at
                LIMIT 1
                """
            )
        ).fetchone()
    if row is None:
        return None
    job = _job_row_to_dict(row)
    job["scope_label"] = _resolve_scope_labels(engine, [job]).get(job["id"])
    return job


def claim_next_queued_job(engine, job_types: frozenset[str] | None = None) -> dict | None:
    """`job_types`, when given, restricts the claim to that set (the
    concurrency-lane worker calls this once per lane, each with its own
    fixed set of job types, so at most one job per lane runs at a time).

    Selects the oldest matching row and marks it 'running' in the same
    UPDATE (guarded by a `WHERE status = 'queued'` re-check on the write
    itself), rather than a plain `SELECT` followed by a separate write --
    two callers racing this (two lanes, or a stray second backend process
    sharing the same database) could otherwise both read the same 'queued'
    row before either wrote to it, and both start running it."""
    params: dict = {}
    where = "status = 'queued'"
    if job_types is not None:
        placeholders = ", ".join(f":jt{i}" for i in range(len(job_types)))
        where += f" AND job_type IN ({placeholders})"
        params.update({f"jt{i}": jt for i, jt in enumerate(job_types)})
    params["now"] = _now()
    with engine.begin() as conn:
        row = conn.execute(
            text(
                f"""
                UPDATE jobs
                SET status = 'running', started_at = :now, updated_at = :now
                WHERE id = (SELECT id FROM jobs WHERE {where} ORDER BY created_at LIMIT 1)
                  AND status = 'queued'
                RETURNING *
                """
            ),
            params,
        ).fetchone()
    if row is None:
        return None
    job = _job_row_to_dict(row)
    job["scope_label"] = _resolve_scope_labels(engine, [job]).get(job["id"])
    return job


def start_job(engine, job_id: str) -> None:
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE jobs SET status = 'running', started_at = :now, updated_at = :now WHERE id = :id"),
            {"now": now, "id": job_id},
        )
    log_event(engine, job_id, None, "info", "job_started", "Job started.")


def finish_job(
    engine, job_id: str, status: str, summary_message: str | None = None, *, interrupted: bool = False
) -> None:
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE jobs
                SET status = :status, finished_at = :now, updated_at = :now, summary_message = :msg,
                    interrupted = :interrupted
                WHERE id = :id
                """
            ),
            {"status": status, "now": now, "msg": summary_message, "interrupted": int(interrupted), "id": job_id},
        )
    level = "error" if status == "failed" else "info"
    log_event(engine, job_id, None, level, _FINISH_EVENT_TYPES[status], summary_message or status)
    _forget_file_indices(job_id)


def reap_orphaned_jobs(engine) -> int:
    """Called once at startup (`app/main.py`'s lifespan), after
    `batch_submissions.requeue_stalled_jobs()` has already put any `tag` job
    with a still-polling batch submission back on the queue. Any job still
    `status = 'running'` at this point was left running by a backend process
    that stopped/crashed mid-job -- the worker thread that owned it is gone
    (this is a single-process app: nothing else could still be driving it
    forward), and nothing would otherwise ever move it out of `running`
    (user report: a job stayed stuck in the Jobs modal, un-cancellable and
    un-restartable, after a backend restart -- `restart_job` only accepts
    `failed`/`cancelled` jobs).

    Marks each one `failed` with a clear summary instead of a bespoke
    "requeue" mechanism, so the existing Restart button (which already
    re-submits a failed/cancelled job's exact `parameters` unchanged) simply
    becomes available for it. Returns how many jobs were reaped."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id FROM jobs WHERE status = 'running'")).all()
    for row in rows:
        finish_job(
            engine,
            row.id,
            "failed",
            "Interrupted: the backend restarted while this job was running.",
            interrupted=True,
        )
    return len(rows)


def set_job_total_items(engine, job_id: str, total: int) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE jobs SET total_items = :total, updated_at = :now WHERE id = :id"),
            {"total": total, "now": _now(), "id": job_id},
        )


def cancel_job(engine, job_id: str) -> dict | None:
    job = get_job(engine, job_id)
    if job is None:
        return None

    if job["status"] == "queued":
        finish_job(engine, job_id, "cancelled", "Cancelled before starting.")
    elif job["status"] == "paused":
        # No worker owns a paused job (it already released its lane), so it
        # can be finished directly, same as a not-yet-started queued job.
        finish_job(engine, job_id, "cancelled", "Cancelled while paused.")
    elif job["status"] == "running":
        if is_cancel_requested(job_id):
            # A second cancel request for a job that hasn't honored the
            # first one yet (user request): the handler's per-item
            # checkpoint (`check_stop_requested`) never runs if the item
            # it's currently on is stuck in an unbounded blocking call (a
            # network read with no timeout, an unresponsive subprocess) --
            # cooperative cancellation alone can wait forever in that case.
            # Force it: mark the job finished right away rather than waiting
            # on the worker thread. `JobWorker`'s lane (`app/jobs/worker.py`)
            # notices this out-of-band status change and abandons the still
            # -running handler thread instead of blocking on it forever.
            log_event(
                engine, job_id, None, "warning", "job_force_cancelled",
                "Force-cancelled: job did not respond to the first cancellation request.",
            )
            finish_job(engine, job_id, "cancelled", "Force-cancelled (unresponsive).")
        else:
            # Log before flagging: once the worker can see the cancel request
            # it may finish and log job_cancel_honored/job_cancelled within
            # microseconds, so logging after would risk this event landing
            # after them in the event stream.
            log_event(engine, job_id, None, "info", "job_cancel_requested", "Cancellation requested.")
            request_cancel(job_id)
    else:
        raise JobConflictError("job_not_cancellable", f"Job is already {job['status']}.")

    return get_job(engine, job_id)


def mark_job_paused(engine, job_id: str, message: str | None = None) -> None:
    """Called by the worker once a running job's handler honors a pause
    request and returns the `"paused"` status -- unlike `finish_job`, this
    leaves `finished_at` unset since a paused job isn't done, just parked."""
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE jobs SET status = 'paused', updated_at = :now, summary_message = :msg WHERE id = :id"),
            {"now": now, "msg": message, "id": job_id},
        )
    log_event(engine, job_id, None, "info", "job_paused", message or "Job paused.")


def pause_job(engine, job_id: str) -> dict | None:
    job = get_job(engine, job_id)
    if job is None:
        return None

    if job["job_type"] not in PAUSABLE_JOB_TYPES:
        raise JobConflictError(
            "job_not_pausable", f"Jobs of type '{job['job_type']}' cannot be paused."
        )

    if job["status"] == "queued":
        mark_job_paused(engine, job_id, "Paused before starting.")
    elif job["status"] == "running":
        # Same before/after-request logging order concern as cancel_job.
        log_event(engine, job_id, None, "info", "job_pause_requested", "Pause requested.")
        request_pause(job_id)
    else:
        raise JobConflictError("job_not_pausable", f"Job is already {job['status']}.")

    return get_job(engine, job_id)


def resume_job(engine, job_id: str) -> dict | None:
    job = get_job(engine, job_id)
    if job is None:
        return None

    if job["status"] != "paused":
        raise JobConflictError(
            "job_not_resumable", f"Only paused jobs can be resumed (status: {job['status']})."
        )

    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE jobs SET status = 'queued', updated_at = :now WHERE id = :id"),
            {"now": now, "id": job_id},
        )
    log_event(engine, job_id, None, "info", "job_resumed", "Job resumed.")
    return get_job(engine, job_id)


def restart_job(engine, job_id: str) -> dict | None:
    job = get_job(engine, job_id)
    if job is None:
        return None

    if job["status"] not in ("failed", "cancelled"):
        raise JobConflictError(
            "job_not_restartable",
            f"Only failed or cancelled jobs can be restarted (status: {job['status']}).",
        )

    return create_job(engine, job["job_type"], job["scope_type"], job["scope_ref"], job["parameters"])


def delete_job(engine, job_id: str) -> bool:
    job = get_job(engine, job_id)
    if job is None:
        return False

    if job["status"] not in FINISHED_STATUSES:
        raise JobConflictError("job_not_deletable", "Only finished jobs can be deleted.")

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM app_events WHERE job_id = :id"), {"id": job_id})
        conn.execute(text("DELETE FROM job_items WHERE job_id = :id"), {"id": job_id})
        conn.execute(text("DELETE FROM jobs WHERE id = :id"), {"id": job_id})
    return True


def delete_finished_jobs(engine) -> int:
    with engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id FROM jobs WHERE status IN ('completed', 'failed', 'cancelled')")
        ).all()
        ids = [{"id": row.id} for row in rows]
        if ids:
            conn.execute(text("DELETE FROM app_events WHERE job_id = :id"), ids)
            conn.execute(text("DELETE FROM job_items WHERE job_id = :id"), ids)
            conn.execute(text("DELETE FROM jobs WHERE id = :id"), ids)
    return len(ids)


def run_retention_sweep(engine, older_than_hours: int = 24) -> int:
    """Delete finished jobs (and their items/events) older than the retention
    window (Job Model "Retention")."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=older_than_hours)).isoformat()
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id FROM jobs
                WHERE status IN ('completed', 'failed', 'cancelled')
                  AND finished_at IS NOT NULL AND finished_at < :cutoff
                """
            ),
            {"cutoff": cutoff},
        ).all()
        ids = [{"id": row.id} for row in rows]
        if ids:
            conn.execute(text("DELETE FROM app_events WHERE job_id = :id"), ids)
            conn.execute(text("DELETE FROM job_items WHERE job_id = :id"), ids)
            conn.execute(text("DELETE FROM jobs WHERE id = :id"), ids)
    return len(ids)


# --- job items --------------------------------------------------------------


def create_job_item(
    engine,
    job_id: str,
    item_key: str | None = None,
    file_id: str | None = None,
    step_name: str | None = None,
) -> str:
    item_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO job_items (id, job_id, file_id, item_key, status, step_name)
                VALUES (:id, :job_id, :file_id, :item_key, 'queued', :step_name)
                """
            ),
            {"id": item_id, "job_id": job_id, "file_id": file_id, "item_key": item_key, "step_name": step_name},
        )
    return item_id


def start_job_item(engine, item_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE job_items SET status = 'running', started_at = :now WHERE id = :id"),
            {"now": _now(), "id": item_id},
        )


def update_job_item_progress(engine, item_id: str, progress_pct: float) -> None:
    """Live within-file encode progress (post-V1, user request), parsed from
    ffmpeg's own `-progress` output (`app/conversion.py::run_ffmpeg`) and
    throttled by the caller -- a plain column write with no `app_events` row,
    so a slow encode reporting progress every second or so doesn't flood the
    event log/Log Viewer the way a `log_event` call for each update would."""
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE job_items SET progress_pct = :pct WHERE id = :id"),
            {"pct": max(0.0, min(100.0, progress_pct)), "id": item_id},
        )


def complete_job_item(
    engine,
    item_id: str,
    file_id: str | None = None,
    output_ref: str | None = None,
    message: str | None = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE job_items
                SET status = 'completed', finished_at = :now,
                    file_id = COALESCE(:file_id, file_id), output_ref = :output_ref, message = :message
                WHERE id = :id
                """
            ),
            {"now": _now(), "file_id": file_id, "output_ref": output_ref, "message": message, "id": item_id},
        )


def skip_job_item(engine, item_id: str, message: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE job_items SET status = 'skipped', finished_at = :now, message = :message WHERE id = :id"
            ),
            {"now": _now(), "message": message, "id": item_id},
        )


def fail_job_item(engine, item_id: str, message: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE job_items SET status = 'failed', finished_at = :now, message = :message WHERE id = :id"
            ),
            {"now": _now(), "message": message, "id": item_id},
        )


def get_job_items(engine, job_id: str) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM job_items WHERE job_id = :id ORDER BY rowid"), {"id": job_id}
        ).all()
    return [_job_item_row_to_dict(row) for row in rows]
