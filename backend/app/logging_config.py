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
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

# Deliberately *outside* `backend/` (repo root instead): `uvicorn --reload`
# watches the whole `backend/` tree (no `--reload-exclude` narrowing it --
# see docs/development.md's reload-wedging note), so a log file written
# inside it would retrigger the watcher on every single line logged --
# reloading the app because the app logged something, forever.
LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
LOG_FILE = LOG_DIR / "backend.log"

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging() -> None:
    LOG_DIR.mkdir(exist_ok=True)
    formatter = logging.Formatter(_FORMAT)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Rotates every 5 minutes, one backup kept -- the file always holds the
    # last 5-10 minutes of activity (enough to diagnose an error just seen
    # in the console) without growing unbounded over a long dev session.
    file_handler = TimedRotatingFileHandler(LOG_FILE, when="M", interval=5, backupCount=1, encoding="utf-8")
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
