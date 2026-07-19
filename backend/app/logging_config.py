"""Console + rolling-file logging setup.

Chat request (2026-07-14): stop uvicorn's default per-request access log
(one "GET /api/jobs?limit=200 200 OK" line per hit) from drowning the
terminal under frontend polling, and keep a short-lived text copy of
everything the console prints so a backend error can be pulled up and
pasted into chat after the fact, not just seen scrolling by. Per-request
logging itself is `app.request_logging.RequestLoggingMiddleware`; this
module only wires up *where* every logger's output goes.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# Deliberately *outside* `backend/` (repo root instead): `uvicorn --reload`
# watches the whole `backend/` tree (package.json's `--reload-exclude "*.db*"`
# only narrows out the SQLite db/wal/shm files -- see docs/development.md's
# reload-wedging note), so a log file written inside it would retrigger the
# watcher on every single line logged -- reloading the app because the app
# logged something, forever.
# With VIDEO_ARCHIVE_STATE_DIR set (container/cluster run, no --reload —
# see app/config.py) logs join the rest of the state on that volume.
_STATE_DIR_ENV = os.environ.get("VIDEO_ARCHIVE_STATE_DIR")
LOG_DIR = (
    Path(_STATE_DIR_ENV) / "logs"
    if _STATE_DIR_ENV
    else Path(__file__).resolve().parent.parent.parent / "logs"
)
LOG_FILE = LOG_DIR / "backend.log"

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


class _WindowsSafeTimedRotatingFileHandler(TimedRotatingFileHandler):
    """Skip a rollover instead of raising if the file is still locked.

    `--reload` briefly runs old and new worker processes back to back, both
    holding a handle on the same `backend.log`; on Windows that makes the
    other process's rename in `doRollover` fail with `PermissionError`. It's
    already non-fatal (stdlib's `emit` catches it and just prints "Logging
    error"), but the traceback is noisy -- swallow it and retry at the next
    interval instead.
    """

    def doRollover(self) -> None:
        try:
            super().doRollover()
        except PermissionError:
            pass


def configure_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    formatter = logging.Formatter(_FORMAT)

    # `logging.StreamHandler()` writes to stderr, which Python opens as
    # `cp1252` on Windows regardless of terminal (Git Bash's mintty renders
    # UTF-8 fine, but never gets the chance) -- request log lines carry
    # emoji (see `app.request_logging`), and cp1252 can't encode them, so
    # they come out as literal `\U0001f4e5`-style escapes instead of crashing.
    # Force real UTF-8 bytes onto the stream so they render correctly.
    sys.stderr.reconfigure(encoding="utf-8")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Rotates every 5 minutes, one backup kept -- the file always holds the
    # last 5-10 minutes of activity (enough to diagnose an error just seen
    # in the console) without growing unbounded over a long dev session.
    file_handler = _WindowsSafeTimedRotatingFileHandler(
        LOG_FILE, when="M", interval=5, backupCount=1, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # `app.request_logging`'s middleware replaces uvicorn's own access log
    # with a quieter, more informative one (see there for the format and the
    # list of polling endpoints it stays silent on) -- disable the built-in
    # one so requests aren't logged twice.
    logging.getLogger("uvicorn.access").disabled = True

    # smbprotocol logs one INFO line per SMB2 read/write response -- with
    # large files that's dozens of lines per second. The bytes it reports
    # are already folded into our own network-throughput indicators (see
    # `app.sources.smb_backend`), so the raw per-chunk log adds noise
    # without new information. Keep warnings/errors, drop the per-chunk chatter.
    logging.getLogger("smbprotocol").setLevel(logging.WARNING)
