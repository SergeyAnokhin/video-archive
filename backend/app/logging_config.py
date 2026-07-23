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
# Chat request: diagnose Kubernetes OOM restarts that were silently killing
# in-progress jobs (`app.jobs.service.reap_orphaned_jobs`) by sampling
# CPU/memory on an interval (see `app/resource_monitor.py`) into its own
# file, rotated far less aggressively than `backend.log` -- a ~30 minute
# OOM cycle needs more than backend.log's ~10 minute retention to show up.
RESOURCE_LOG_FILE = LOG_DIR / "resource_usage.log"
RESOURCE_MONITOR_LOGGER_NAME = "app.resource_monitor"

_TIME_FORMAT = "%H:%M:%S"
# Console drops the level word entirely (user request: it stretched every
# line out) and relies on `_ColorConsoleFormatter` coloring the timestamp
# instead, mirroring `LogViewerModal.tsx`'s `.log-viewer__row--warning
# .log-viewer__time` / `--error` coloring on the frontend. The rotating file
# has no color, so it keeps the level as text.
_CONSOLE_FORMAT = "%(asctime)s %(short_name)s: %(message)s"
_FILE_FORMAT = "%(asctime)s %(levelname)s %(short_name)s: %(message)s"

_ANSI_YELLOW = "\x1b[33m"
_ANSI_RED = "\x1b[31m"
_ANSI_RESET = "\x1b[0m"
_LEVEL_COLORS = {"WARNING": _ANSI_YELLOW, "ERROR": _ANSI_RED, "CRITICAL": _ANSI_RED}


def _abbreviate_logger_name(name: str) -> str:
    """User request, terminal legibility: "app.jobs.service" -> "a.j.service"
    -- keeps the last component (the actual module) in full and collapses
    every parent package down to its initial."""
    parts = name.split(".")
    if len(parts) <= 1:
        return name
    return ".".join(part[:1] for part in parts[:-1]) + "." + parts[-1]


class _AbbreviatingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.short_name = _abbreviate_logger_name(record.name)
        return super().format(record)


class _ColorConsoleFormatter(_AbbreviatingFormatter):
    """Colors the timestamp by level instead of printing a level word, only
    when writing to a real terminal (`use_color`) -- so output redirected to
    a file/pipe stays plain, ANSI-free text."""

    def __init__(self, *args, use_color: bool, **kwargs):
        super().__init__(*args, **kwargs)
        self._use_color = use_color

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        time_str = super().formatTime(record, datefmt)
        color = _LEVEL_COLORS.get(record.levelname)
        if self._use_color and color:
            return f"{color}{time_str}{_ANSI_RESET}"
        return time_str


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

    # `logging.StreamHandler()` writes to stderr, which Python opens as
    # `cp1252` on Windows regardless of terminal (Git Bash's mintty renders
    # UTF-8 fine, but never gets the chance) -- request log lines carry
    # emoji (see `app.request_logging`), and cp1252 can't encode them, so
    # they come out as literal `\U0001f4e5`-style escapes instead of crashing.
    # Force real UTF-8 bytes onto the stream so they render correctly.
    sys.stderr.reconfigure(encoding="utf-8")

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        _ColorConsoleFormatter(_CONSOLE_FORMAT, datefmt=_TIME_FORMAT, use_color=sys.stderr.isatty())
    )

    # Rotates every 5 minutes, one backup kept -- the file always holds the
    # last 5-10 minutes of activity (enough to diagnose an error just seen
    # in the console) without growing unbounded over a long dev session.
    file_handler = _WindowsSafeTimedRotatingFileHandler(
        LOG_FILE, when="M", interval=5, backupCount=1, encoding="utf-8"
    )
    file_handler.setFormatter(_AbbreviatingFormatter(_FILE_FORMAT, datefmt=_TIME_FORMAT))

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # Own handler + own rotation schedule, and `propagate = False` so it
    # never also lands in `backend.log`/the console -- one sample line per
    # interval would otherwise add noise to the general-purpose log without
    # the longer retention it actually needs (see RESOURCE_LOG_FILE above).
    resource_log_handler = _WindowsSafeTimedRotatingFileHandler(
        RESOURCE_LOG_FILE, when="H", interval=1, backupCount=48, encoding="utf-8"
    )
    resource_log_handler.setFormatter(_AbbreviatingFormatter(_FILE_FORMAT, datefmt=_TIME_FORMAT))
    resource_logger = logging.getLogger(RESOURCE_MONITOR_LOGGER_NAME)
    resource_logger.setLevel(logging.INFO)
    resource_logger.propagate = False
    resource_logger.addHandler(resource_log_handler)

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

    # watchfiles (uvicorn --reload's file watcher) logs an INFO line on every
    # file save -- "1 change detected" -- which is reload plumbing, not
    # application activity. Keep warnings/errors, drop the per-save chatter.
    logging.getLogger("watchfiles.main").setLevel(logging.WARNING)
