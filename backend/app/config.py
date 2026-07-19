"""Backend-wide constants and paths."""

import os
from pathlib import Path

APP_VERSION = "0.1.0"

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Container/cluster override (docs/deployment.md): when VIDEO_ARCHIVE_STATE_DIR
# is set, every piece of mutable backend state (SQLite DB, secrets.env,
# detection models, logs) lives under that directory — in Kubernetes it
# points at the persistent volume. Unset (the normal local run) everything
# stays in its historical place next to the code.
_STATE_DIR_ENV = os.environ.get("VIDEO_ARCHIVE_STATE_DIR")
STATE_DIR = Path(_STATE_DIR_ENV) if _STATE_DIR_ENV else BACKEND_DIR

DATABASE_PATH = STATE_DIR / "video_archive.db"
SECRETS_PATH = STATE_DIR / "secrets.env"
