"""Single sequential job worker (Job Model "Concurrency Model").

Exactly one job runs at a time, strictly FIFO. The worker owns a background
thread started/stopped from the FastAPI lifespan in `app/main.py`; it polls
for the oldest queued job rather than using an in-memory queue so that jobs
created by any request handler are picked up without extra plumbing.
"""

from __future__ import annotations

import threading
import time

from app.db import get_engine
from app.jobs import service
from app.jobs.convert import run_convert_job
from app.jobs.preview import run_preview_job
from app.jobs.rescan import run_rescan_job

_POLL_INTERVAL_SECONDS = 0.3
_RETENTION_INTERVAL_SECONDS = 60.0

_HANDLERS = {
    "rescan": run_rescan_job,
    "convert": run_convert_job,
    "preview": run_preview_job,
}


class JobWorker:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="job-worker", daemon=True)
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
            job = service.claim_next_queued_job(engine)
            if job is None:
                time.sleep(_POLL_INTERVAL_SECONDS)
            else:
                self._execute(engine, job)

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
            service.finish_job(engine, job["id"], status, message)
        except Exception as exc:  # noqa: BLE001 - a failed job must not stop the worker
            service.finish_job(engine, job["id"], "failed", str(exc))
        finally:
            service.clear_cancel_request(job["id"])
