import sys
import threading
import traceback

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def get_health() -> dict:
    return {"status": "ok"}


@router.get("/health/thread-dump")
def get_thread_dump() -> dict:
    """Current stack of every live thread -- the diagnostic for a job that
    stops logging and never returns (user-reported: a `convert` job that
    printed its `job_parameters` line and then nothing, with the SMB lock
    reporting itself free). The job handler runs on its own thread named
    `job-<id8>` (see `app/jobs/worker.py`'s `_execute`), so its frame here
    names the exact blocking call instead of leaving it to be inferred from
    which log lines are missing.

    Read-only: `sys._current_frames()` snapshots frames without suspending
    anything, so this stays safe to call while a job is wedged.
    """
    names_by_ident = {t.ident: t.name for t in threading.enumerate()}
    frames = sys._current_frames()
    return {
        "threads": [
            {
                "ident": ident,
                "name": names_by_ident.get(ident, "(unknown)"),
                "stack": [line.rstrip("\n") for line in traceback.format_stack(frame)],
            }
            for ident, frame in sorted(frames.items())
        ]
    }
