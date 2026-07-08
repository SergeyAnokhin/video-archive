"""Job queue tests: state machine, cancellation, restart/delete, retention.

This is the logic that had zero regression coverage after Stage 3 (job
infrastructure) landed - only exercised manually during development. Runs
against the isolated `engine`/`source` fixtures from conftest.py.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.jobs import service
from app.jobs.worker import JobWorker

from .conftest import make_files


def test_create_and_cancel_queued_job(engine, source):
    job = service.create_job(engine, "rescan", "source", None, {"path": ""})
    assert job["status"] == "queued"

    cancelled = service.cancel_job(engine, job["id"])
    assert cancelled["status"] == "cancelled"
    assert "before starting" in cancelled["summary_message"]


def test_cancel_finished_job_is_conflict(engine, source):
    job = service.create_job(engine, "rescan", "source", None, {"path": ""})
    service.start_job(engine, job["id"])
    service.finish_job(engine, job["id"], "completed", "done")

    with pytest.raises(service.JobConflictError) as exc_info:
        service.cancel_job(engine, job["id"])
    assert exc_info.value.code == "job_not_cancellable"


def test_restart_only_allowed_for_failed_or_cancelled(engine, source):
    job = service.create_job(engine, "rescan", "source", None, {"path": ""})
    service.start_job(engine, job["id"])

    with pytest.raises(service.JobConflictError) as exc_info:
        service.restart_job(engine, job["id"])
    assert exc_info.value.code == "job_not_restartable"

    service.finish_job(engine, job["id"], "failed", "boom")
    restarted = service.restart_job(engine, job["id"])
    assert restarted["status"] == "queued"
    assert restarted["job_type"] == "rescan"
    assert restarted["id"] != job["id"]


def test_delete_requires_finished_status(engine, source):
    job = service.create_job(engine, "rescan", "source", None, {"path": ""})

    with pytest.raises(service.JobConflictError) as exc_info:
        service.delete_job(engine, job["id"])
    assert exc_info.value.code == "job_not_deletable"

    service.cancel_job(engine, job["id"])  # queued -> cancelled
    assert service.delete_job(engine, job["id"]) is True
    assert service.get_job(engine, job["id"]) is None


def test_set_job_total_items(engine, source):
    job = service.create_job(engine, "preview", "source", None, {"path": ""})
    assert job["total_items"] is None

    service.set_job_total_items(engine, job["id"], 43)
    assert service.get_job(engine, job["id"])["total_items"] == 43


def test_retention_sweep_removes_old_finished_jobs(engine, source):
    job = service.create_job(engine, "rescan", "source", None, {"path": ""})
    service.start_job(engine, job["id"])
    service.finish_job(engine, job["id"], "completed", "done")

    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    with engine.begin() as conn:
        conn.execute(text("UPDATE jobs SET finished_at = :t WHERE id = :id"), {"t": old, "id": job["id"]})

    removed = service.run_retention_sweep(engine, older_than_hours=24)
    assert removed == 1
    assert service.get_job(engine, job["id"]) is None

    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) AS c FROM app_events WHERE job_id = :id"), {"id": job["id"]}
        ).fetchone().c
    assert count == 0


def test_rescan_job_runs_to_completion_via_worker(engine, source):
    make_files(source["root"], count=25)

    job = service.create_job(engine, "rescan", "source", None, {"path": ""})
    worker = JobWorker()
    worker.start()
    try:
        current = _wait_for_finish(engine, job["id"])
    finally:
        worker.stop()

    assert current["status"] == "completed"
    items = service.get_job_items(engine, job["id"])
    assert len(items) == 25
    assert all(item["status"] == "completed" for item in items)


def test_cancelling_a_running_job_stops_it_partway(engine, source, monkeypatch):
    make_files(source["root"], count=500)

    # Slow item processing down for this test only (production code is
    # untouched) so the cancellation window is reliably observable instead
    # of racing a worker thread that can process thousands of items/sec on
    # fast local SQLite/WAL storage.
    original_create_item = service.create_job_item

    def slow_create_job_item(*args, **kwargs):
        time.sleep(0.002)
        return original_create_item(*args, **kwargs)

    monkeypatch.setattr(service, "create_job_item", slow_create_job_item)

    job = service.create_job(engine, "rescan", "source", None, {"path": ""})
    worker = JobWorker()
    worker.start()
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if len(service.get_job_items(engine, job["id"])) >= 20:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("job never made visible progress")

        service.cancel_job(engine, job["id"])
        current = _wait_for_finish(engine, job["id"])
    finally:
        worker.stop()

    assert current["status"] == "cancelled"
    items = service.get_job_items(engine, job["id"])
    assert 0 < len(items) < 500

    with engine.connect() as conn:
        event_types = [
            row.event_type
            for row in conn.execute(
                text("SELECT event_type FROM app_events WHERE job_id = :id ORDER BY rowid"),
                {"id": job["id"]},
            ).all()
        ]
    assert event_types[:2] == ["job_queued", "job_started"]
    assert "job_cancel_requested" in event_types
    assert "job_cancel_honored" in event_types
    assert event_types[-1] == "job_cancelled"


def _wait_for_finish(engine, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = service.get_job(engine, job_id)
        if current["status"] in service.FINISHED_STATUSES:
            return current
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")
