"""Persisted batch-tagging submissions (user request -- "the batch task
should survive a service restart, polling every 30 seconds"). A row here is
created the moment a batch is accepted by the provider, before any polling
starts, so the external id and everything needed to resolve it later
(`tag_ids_json`, `items_json`, `top_tag_count`) survive a process restart
even though the poll loop itself does not. `app/jobs/tag.py` polls a row
while its owning job is actually running; `requeue_stalled_jobs()` is called
once at startup (`app/main.py`'s lifespan) to put that job's `tag` job back
on the queue so the normal worker lane picks the resume back up -- see that
module's `run_tag_job()` for how it detects and resumes a pending row
instead of starting a fresh directory scan.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

STATUS_POLLING = "polling"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_FORGOTTEN = "forgotten"

_ACTIVE_STATUSES = (STATUS_POLLING,)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    return {
        "id": row.id,
        "job_id": row.job_id,
        "provider_entry_id": row.provider_entry_id,
        "provider_type": row.provider_type,
        "model_name": row.model_name,
        "external_batch_id": row.external_batch_id,
        "status": row.status,
        "tag_ids_json": row.tag_ids_json,
        "top_tag_count": row.top_tag_count,
        "items_json": row.items_json,
        "error_message": row.error_message,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "resolved_at": row.resolved_at,
    }


def create_submission(
    engine,
    *,
    job_id: str,
    provider_entry_id: str,
    provider_type: str,
    model_name: str | None,
    external_batch_id: str,
    tag_ids: list[str],
    top_tag_count: int,
    items: list[dict],
) -> dict:
    """`items` is `[{"file_id": ..., "item_id": ..., "relative_path": ...}]`,
    in the same order sent to the provider (Gemini correlates batch results
    back to files by response order, not by an echoed id -- see
    `app/providers/gemini.py`)."""
    submission_id = str(uuid.uuid4())
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO batch_submissions (
                    id, job_id, provider_entry_id, provider_type, model_name, external_batch_id,
                    status, tag_ids_json, top_tag_count, items_json, created_at, updated_at
                ) VALUES (
                    :id, :job_id, :provider_entry_id, :provider_type, :model_name, :external_batch_id,
                    :status, :tag_ids_json, :top_tag_count, :items_json, :now, :now
                )
                """
            ),
            {
                "id": submission_id,
                "job_id": job_id,
                "provider_entry_id": provider_entry_id,
                "provider_type": provider_type,
                "model_name": model_name,
                "external_batch_id": external_batch_id,
                "status": STATUS_POLLING,
                "tag_ids_json": json.dumps(tag_ids),
                "top_tag_count": top_tag_count,
                "items_json": json.dumps(items),
                "now": now,
            },
        )
    return get_submission(engine, submission_id)


def get_submission(engine, submission_id: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM batch_submissions WHERE id = :id"), {"id": submission_id}).fetchone()
    return _row_to_dict(row) if row else None


def get_pending_for_job(engine, job_id: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM batch_submissions WHERE job_id = :job_id AND status = :status"),
            {"job_id": job_id, "status": STATUS_POLLING},
        ).fetchone()
    return _row_to_dict(row) if row else None


def mark_resolved(engine, submission_id: str, status: str, error_message: str | None = None) -> None:
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE batch_submissions
                SET status = :status, error_message = :error_message, updated_at = :now, resolved_at = :now
                WHERE id = :id
                """
            ),
            {"status": status, "error_message": error_message, "now": now, "id": submission_id},
        )


def list_active(engine) -> list[dict]:
    """Every batch submission still `polling`, for the Jobs modal's
    "batch jobs in progress" view (Gemini/Mistral only, since those are the
    only batch-capable providers)."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT * FROM batch_submissions WHERE status IN "
                f"({', '.join(':s' + str(i) for i in range(len(_ACTIVE_STATUSES)))}) "
                "ORDER BY created_at DESC"
            ),
            {f"s{i}": status for i, status in enumerate(_ACTIVE_STATUSES)},
        ).all()
    return [_row_to_dict(row) for row in rows]


def forget(engine, submission_id: str) -> bool:
    """"Forget locally" (user request, deliberately no provider-side
    cancel): stops this app from polling/tracking the submission. The batch
    keeps running at the provider regardless -- there is no cancel call to
    it. Returns `False` if the row doesn't exist or isn't still active."""
    submission = get_submission(engine, submission_id)
    if submission is None or submission["status"] not in _ACTIVE_STATUSES:
        return False
    mark_resolved(engine, submission_id, STATUS_FORGOTTEN, error_message="Forgotten locally by user request.")
    return True


def requeue_stalled_jobs(engine) -> int:
    """Called once at startup (`app/main.py`'s lifespan, before the worker
    starts): any `tag` job left `running` with a still-`polling` batch
    submission was mid-poll when the process stopped, with nothing left to
    resume it now that the worker thread that owned it is gone. Putting the
    job back to `queued` lets the normal lane pick it up again through
    `claim_next_queued_job()`; `app/jobs/tag.py::run_tag_job()` detects the
    pending submission on entry and resumes polling instead of re-scanning
    the directory from scratch. Returns how many jobs were requeued."""
    with engine.begin() as conn:
        job_ids = conn.execute(
            text(
                """
                SELECT DISTINCT bs.job_id AS job_id
                FROM batch_submissions bs
                JOIN jobs j ON j.id = bs.job_id
                WHERE bs.status = :status AND j.status = 'running'
                """
            ),
            {"status": STATUS_POLLING},
        ).all()
        if not job_ids:
            return 0
        ids = [row.job_id for row in job_ids]
        now = _now()
        for job_id in ids:
            conn.execute(
                text("UPDATE jobs SET status = 'queued', updated_at = :now WHERE id = :id"),
                {"now": now, "id": job_id},
            )
    return len(ids)
