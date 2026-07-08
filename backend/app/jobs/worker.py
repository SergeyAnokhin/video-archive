"""Concurrency-lane job worker (Job Model "Concurrency Model", extended
post-V1 by user request for pause/resume + limited parallelism).

Two independent lanes run concurrently, each behaving like the original
single sequential worker (poll for the oldest queued job among its own set
of job types, run it to completion, repeat) so at most one CPU-bound job and
one network-bound job run at the same time:

- the CPU lane: rescan/convert/preview/cleanup/optimize_db/backup/restore --
  all local ffmpeg/PIL/disk work, so running two of these at once would just
  contend for the same CPU/disk instead of going faster.
- the network lane: tag -- calls out to an external AI provider API, so it
  doesn't compete with the CPU lane for local resources and can run
  alongside it.

Pausing a running job frees its lane immediately once the handler notices
the request between items (see `service.check_stop_requested` call sites in
`app/jobs/*.py`), so another queued job of the same lane can start right
away instead of waiting for the paused one to finish.
"""

from __future__ import annotations

import threading
import time

from app.db import get_engine
from app.jobs import service
from app.jobs.backup import run_backup_job
from app.jobs.cleanup import run_cleanup_job
from app.jobs.convert import run_convert_job
from app.jobs.optimize_db import run_optimize_db_job
from app.jobs.preview import run_preview_job
from app.jobs.rescan import run_rescan_job
from app.jobs.restore import run_restore_job
from app.jobs.tag import run_tag_job

_POLL_INTERVAL_SECONDS = 0.3
_RETENTION_INTERVAL_SECONDS = 60.0

_HANDLERS = {
    "rescan": run_rescan_job,
    "convert": run_convert_job,
    "preview": run_preview_job,
    "tag": run_tag_job,
    "cleanup": run_cleanup_job,
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
        service.start_job(engine, job["id"])
        handler = _HANDLERS.get(job["job_type"])
        try:
            if handler is None:
                raise RuntimeError(f"No worker handler registered for job type: {job['job_type']}")
            status, message = handler(engine, job)
            if status == "paused":
                service.mark_job_paused(engine, job["id"], message)
            else:
                service.finish_job(engine, job["id"], status, message)
        except Exception as exc:  # noqa: BLE001 - a failed job must not stop the worker
            service.finish_job(engine, job["id"], "failed", str(exc))
        finally:
            service.clear_cancel_request(job["id"])
            service.clear_pause_request(job["id"])


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
