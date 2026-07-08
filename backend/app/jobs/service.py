"""Job/job-item CRUD, state machine transitions, and the event log (Job Model,
Data Model §6-7, §11). Called both from request handlers (create/list/cancel/
etc.) and from the background worker thread (`app/jobs/worker.py`), so every
write here is its own short transaction rather than one held across a
request's whole lifetime.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

FINISHED_STATUSES = ("completed", "failed", "cancelled")

_FINISH_EVENT_TYPES = {
    "completed": "job_completed",
    "failed": "job_failed",
    "cancelled": "job_cancelled",
}


class JobConflictError(Exception):
    """Raised when a requested transition isn't valid for the job's current status."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
PAUSABLE_JOB_TYPES = frozenset({"rescan", "convert", "preview", "tag", "cleanup"})


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


# --- row <-> dict mapping ----------------------------------------------------


def _job_row_to_dict(row) -> dict:
    return {
        "id": row.id,
        "job_type": row.job_type,
        "scope_type": row.scope_type,
        "scope_ref": row.scope_ref,
        "status": row.status,
        "parameters": json.loads(row.parameters) if row.parameters else {},
        "started_at": row.started_at,
        "finished_at": row.finished_at,
        "summary_message": row.summary_message,
        "total_items": row.total_items,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
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
    }


# --- events -------------------------------------------------------------


def log_event(
    engine,
    job_id: str | None,
    file_id: str | None,
    level: str,
    event_type: str,
    message: str,
    payload: dict | None = None,
) -> None:
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
    return _job_row_to_dict(row) if row else None


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
    return [_job_row_to_dict(row) for row in rows]


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
    return _job_row_to_dict(row) if row else None


def claim_next_queued_job(engine, job_types: frozenset[str] | None = None) -> dict | None:
    """`job_types`, when given, restricts the claim to that set (the
    concurrency-lane worker calls this once per lane, each with its own
    fixed set of job types, so at most one job per lane runs at a time)."""
    params: dict = {}
    where = "status = 'queued'"
    if job_types is not None:
        placeholders = ", ".join(f":jt{i}" for i in range(len(job_types)))
        where += f" AND job_type IN ({placeholders})"
        params.update({f"jt{i}": jt for i, jt in enumerate(job_types)})
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT * FROM jobs WHERE {where} ORDER BY created_at LIMIT 1"), params
        ).fetchone()
    return _job_row_to_dict(row) if row else None


def start_job(engine, job_id: str) -> None:
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE jobs SET status = 'running', started_at = :now, updated_at = :now WHERE id = :id"),
            {"now": now, "id": job_id},
        )
    log_event(engine, job_id, None, "info", "job_started", "Job started.")


def finish_job(engine, job_id: str, status: str, summary_message: str | None = None) -> None:
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE jobs
                SET status = :status, finished_at = :now, updated_at = :now, summary_message = :msg
                WHERE id = :id
                """
            ),
            {"status": status, "now": now, "msg": summary_message, "id": job_id},
        )
    level = "error" if status == "failed" else "info"
    log_event(engine, job_id, None, level, _FINISH_EVENT_TYPES[status], summary_message or status)


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
        # Log before flagging: once the worker can see the cancel request it
        # may finish and log job_cancel_honored/job_cancelled within
        # microseconds, so logging after would risk this event landing after
        # them in the event stream.
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
