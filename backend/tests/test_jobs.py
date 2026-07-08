"""Job queue tests: state machine, cancellation, restart/delete, retention,
pause/resume, and the CPU/network concurrency-lane split (post-V1 user
request).

This is the logic that had zero regression coverage after Stage 3 (job
infrastructure) landed - only exercised manually during development. Runs
against the isolated `engine`/`source` fixtures from conftest.py.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from app.jobs import service
from app.jobs import worker as worker_module
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


def _wait_for_status(engine, job_id: str, status: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        current = service.get_job(engine, job_id)
        if current["status"] == status:
            return current
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not reach status {status!r} within {timeout}s")


def test_pause_and_resume_queued_job(engine, source):
    job = service.create_job(engine, "preview", "source", None, {"path": ""})

    paused = service.pause_job(engine, job["id"])
    assert paused["status"] == "paused"
    assert "before starting" in paused["summary_message"]

    resumed = service.resume_job(engine, job["id"])
    assert resumed["status"] == "queued"


def test_cancelling_a_paused_job_finishes_it_directly(engine, source):
    job = service.create_job(engine, "preview", "source", None, {"path": ""})
    service.pause_job(engine, job["id"])
    assert service.get_job(engine, job["id"])["status"] == "paused"

    cancelled = service.cancel_job(engine, job["id"])
    assert cancelled["status"] == "cancelled"
    assert "while paused" in cancelled["summary_message"]


def test_pause_finished_job_is_conflict(engine, source):
    job = service.create_job(engine, "preview", "source", None, {"path": ""})
    service.start_job(engine, job["id"])
    service.finish_job(engine, job["id"], "completed", "done")

    with pytest.raises(service.JobConflictError) as exc_info:
        service.pause_job(engine, job["id"])
    assert exc_info.value.code == "job_not_pausable"


def test_pause_rejects_job_types_without_a_per_item_loop(engine, source):
    job = service.create_job(engine, "optimize_db", "maintenance", None, {})

    with pytest.raises(service.JobConflictError) as exc_info:
        service.pause_job(engine, job["id"])
    assert exc_info.value.code == "job_not_pausable"


def test_resume_non_paused_job_is_conflict(engine, source):
    job = service.create_job(engine, "preview", "source", None, {"path": ""})

    with pytest.raises(service.JobConflictError) as exc_info:
        service.resume_job(engine, job["id"])
    assert exc_info.value.code == "job_not_resumable"


def test_pausing_a_running_job_stops_it_partway_and_resume_finishes_it(engine, source, monkeypatch):
    make_files(source["root"], count=500)

    # Same slow-down trick as test_cancelling_a_running_job_stops_it_partway,
    # so pausing has a reliable window to land mid-job instead of racing a
    # worker thread that can blow through 500 trivial rescan items almost
    # instantly on local SQLite/WAL storage.
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

        service.pause_job(engine, job["id"])
        _wait_for_status(engine, job["id"], "paused")
        items_at_pause = len(service.get_job_items(engine, job["id"]))
        assert 0 < items_at_pause < 500

        service.resume_job(engine, job["id"])
        current = _wait_for_finish(engine, job["id"])
    finally:
        worker.stop()

    assert current["status"] == "completed"
    # Resuming re-invokes the handler (it re-derives its candidate list, same
    # as `restart_job` would for a fresh job) rather than continuing mid-list,
    # so the post-resume pass alone creates a full 500 job items.
    assert len(service.get_job_items(engine, job["id"])) >= 500

    with engine.connect() as conn:
        event_types = [
            row.event_type
            for row in conn.execute(
                text("SELECT event_type FROM app_events WHERE job_id = :id ORDER BY rowid"),
                {"id": job["id"]},
            ).all()
        ]
    assert "job_pause_requested" in event_types
    assert "job_pause_honored" in event_types
    assert "job_resumed" in event_types
    assert event_types[-1] == "job_completed"


def test_cpu_and_network_job_types_are_partitioned(engine, source):
    assert worker_module._NETWORK_JOB_TYPES == {"tag"}
    assert "tag" not in worker_module._CPU_JOB_TYPES
    assert worker_module._CPU_JOB_TYPES | worker_module._NETWORK_JOB_TYPES == frozenset(worker_module._HANDLERS)


def test_claim_next_queued_job_respects_job_types_filter(engine, source):
    tag_job = service.create_job(engine, "tag", "source", None, {"path": ""})
    rescan_job = service.create_job(engine, "rescan", "source", None, {"path": ""})

    claimed = service.claim_next_queued_job(engine, job_types=worker_module._NETWORK_JOB_TYPES)
    assert claimed["id"] == tag_job["id"]

    claimed = service.claim_next_queued_job(engine, job_types=worker_module._CPU_JOB_TYPES)
    assert claimed["id"] == rescan_job["id"]


def test_cpu_and_network_jobs_run_concurrently(engine, source, monkeypatch):
    """Proves the two lanes genuinely run at the same time rather than one
    after another: each fake handler blocks on a 2-party barrier, so if the
    worker only ever ran one job at a time, the first handler would block
    forever waiting for a second job that never gets picked up -- the
    barrier's timeout would fire and the job would come back `failed`
    instead of `completed`."""
    barrier = threading.Barrier(2, timeout=5)

    def fake_convert(engine, job):
        barrier.wait()
        return "completed", "fake convert done"

    def fake_tag(engine, job):
        barrier.wait()
        return "completed", "fake tag done"

    monkeypatch.setitem(worker_module._HANDLERS, "convert", fake_convert)
    monkeypatch.setitem(worker_module._HANDLERS, "tag", fake_tag)

    convert_job = service.create_job(engine, "convert", "source", None, {})
    tag_job = service.create_job(engine, "tag", "source", None, {})

    worker = JobWorker()
    worker.start()
    try:
        convert_result = _wait_for_finish(engine, convert_job["id"])
        tag_result = _wait_for_finish(engine, tag_job["id"])
    finally:
        worker.stop()

    assert convert_result["status"] == "completed"
    assert tag_result["status"] == "completed"
