"""Concurrency-lane job worker (Job Model "Concurrency Model", extended
post-V1 by user request for pause/resume + limited parallelism).

Two independent lanes run concurrently, each behaving like the original
single sequential worker (poll for the oldest queued job among its own set
of job types, run it to completion, repeat) so at most one CPU-bound job and
one network-bound job run at the same time:

- the CPU lane: rescan/rescan_with_media_info/convert/preview/cleanup/
  migrate_legacy_previews/optimize_db/backup/restore --
  all local ffmpeg/PIL/disk work, so running two of these at once would just
  contend for the same CPU/disk instead of going faster.
- the network lane: tag -- calls out to an external AI provider API, so it
  doesn't compete with the CPU lane for local resources and can run
  alongside it.

Pausing a running job frees its lane immediately once the handler notices
the request between items (see `service.check_stop_requested` call sites in
`app/jobs/*.py`), so another queued job of the same lane can start right
away instead of waiting for the paused one to finish.

A cancel request can also be *forced* (`service.cancel_job()`, user
request): if a job doesn't honor the first cooperative request -- e.g. its
current item is stuck in an unbounded blocking call with no timeout (a
network read, an unresponsive subprocess) -- a repeat cancel marks the job
`cancelled` in the database immediately, without waiting for the handler.
`_Lane._execute` below is what makes that actually free the lane: it runs
the handler in a separate daemon thread and polls it with a timeout instead
of calling it directly, so it can notice this out-of-band status change and
abandon a still-running handler thread rather than blocking on it forever
(which would otherwise wedge this lane -- and every future job of its
types -- until the process restarts). Python has no safe way to kill a
thread, so an abandoned thread finishes its current item on its own; it is
then stopped at its next cooperative checkpoint by
`service.mark_job_abandoned()` (without which it would work through the rest
of its item list -- for `convert`, still replacing source files -- long after
the UI reported the job cancelled). It's a daemon thread, so it can't block
process shutdown either.
"""

from __future__ import annotations

import threading
import time

from app.db import get_engine
from app.jobs import service
from app.jobs.backup import run_backup_job
from app.jobs.cleanup import run_cleanup_job
from app.jobs.convert import run_convert_job
from app.jobs.migrate_legacy_previews import run_migrate_legacy_previews_job
from app.jobs.optimize_db import run_optimize_db_job
from app.jobs.preview import run_preview_job
from app.jobs.rescan import run_rescan_job
from app.jobs.restore import run_restore_job
from app.jobs.tag import run_tag_job

_POLL_INTERVAL_SECONDS = 0.3
_RETENTION_INTERVAL_SECONDS = 60.0
_ABANDON_CHECK_SECONDS = 0.5

_HANDLERS = {
    "rescan": run_rescan_job,
    "rescan_with_media_info": run_rescan_job,
    "convert": run_convert_job,
    "preview": run_preview_job,
    "tag": run_tag_job,
    "cleanup": run_cleanup_job,
    "migrate_legacy_previews": run_migrate_legacy_previews_job,
    "optimize_db": run_optimize_db_job,
    "backup": run_backup_job,
    "restore": run_restore_job,
}

_NETWORK_JOB_TYPES = frozenset({"tag"})
_CPU_JOB_TYPES = frozenset(_HANDLERS) - _NETWORK_JOB_TYPES


class _Lane:
    """One sequential worker loop scoped to a fixed set of job types --
    exactly the pre-lane-split worker's behavior, just parameterized so two
    of these can run side by side without ever picking up each other's job
    types."""

    def __init__(self, name: str, job_types: frozenset[str], run_retention: bool) -> None:
        self._name = name
        self._job_types = job_types
        self._run_retention = run_retention
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name=f"job-worker-{self._name}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        engine = get_engine()
        last_retention = 0.0

        while not self._stop_event.is_set():
            job = service.claim_next_queued_job(engine, job_types=self._job_types)
            if job is None:
                time.sleep(_POLL_INTERVAL_SECONDS)
            else:
                self._execute(engine, job)

            # Only one lane needs to run the sweep -- both would otherwise
            # race to delete the same already-deleted rows every minute.
            if self._run_retention:
                now = time.monotonic()
                if now - last_retention > _RETENTION_INTERVAL_SECONDS:
                    service.run_retention_sweep(engine)
                    last_retention = now

    def _execute(self, engine, job: dict) -> None:
        job_id = job["id"]
        service.start_job(engine, job_id)
        handler = _HANDLERS.get(job["job_type"])
        if handler is None:
            service.finish_job(engine, job_id, "failed", f"No worker handler registered for job type: {job['job_type']}")
            service.clear_cancel_request(job_id)
            service.clear_pause_request(job_id)
            return

        # Run the handler on its own thread rather than calling it directly
        # on this lane's thread, so a force-cancel (see module docstring) can
        # free this lane even if the handler itself never returns.
        outcome: dict = {}

        def _run() -> None:
            try:
                status, message = handler(engine, job)
                outcome["status"] = status
                outcome["message"] = message
            except Exception as exc:  # noqa: BLE001 - a failed job must not stop the worker
                outcome["status"] = "failed"
                outcome["message"] = str(exc)

        thread = threading.Thread(target=_run, name=f"job-{job_id[:8]}", daemon=True)
        thread.start()

        while thread.is_alive():
            thread.join(timeout=_ABANDON_CHECK_SECONDS)
            if thread.is_alive():
                current = service.get_job(engine, job_id)
                if current is not None and current["status"] in service.FINISHED_STATUSES:
                    service.log_event(
                        engine, job_id, None, "warning", "job_force_abandoned",
                        "Job was force-stopped while its worker thread was still busy; the thread was abandoned.",
                    )
                    # Marked before the registries are cleared, so the
                    # abandoned thread never observes a moment with no stop
                    # signal set at all and run on past its next checkpoint.
                    service.mark_job_abandoned(job_id)
                    service.clear_cancel_request(job_id)
                    service.clear_pause_request(job_id)
                    return

        # The handler may have kept running past an external force-finish
        # that already recorded a terminal status (a race, not the abandon
        # case above) -- that status must win, not a late result from here.
        current = service.get_job(engine, job_id)
        if current is not None and current["status"] in service.FINISHED_STATUSES:
            service.clear_cancel_request(job_id)
            service.clear_pause_request(job_id)
            return

        status = outcome.get("status", "failed")
        message = outcome.get("message")
        if status == "paused":
            service.mark_job_paused(engine, job_id, message)
        else:
            service.finish_job(engine, job_id, status, message)
        service.clear_cancel_request(job_id)
        service.clear_pause_request(job_id)


class JobWorker:
    """Owns both lanes; started/stopped together from `main.py`'s lifespan so
    callers (and tests) don't need to know about the lane split."""

    def __init__(self) -> None:
        self._lanes = [
            _Lane("cpu", _CPU_JOB_TYPES, run_retention=True),
            _Lane("network", _NETWORK_JOB_TYPES, run_retention=False),
        ]

    def start(self) -> None:
        for lane in self._lanes:
            lane.start()

    def stop(self) -> None:
        for lane in self._lanes:
            lane.stop()
