"""Backend-wide constants and paths."""

import os
from pathlib import Path

APP_VERSION = "0.1.0"

BACKEND_DIR = Path(__file__).resolve().parent.parent

# Container/cluster override (docs/deployment.md): when VIDEO_ARCHIVE_STATE_DIR
# is set, every piece of mutable backend state (SQLite DB, secrets.env, preview
# cache, detection models, logs) lives under that directory — in Kubernetes it
# points at the persistent volume. Unset (the normal local run) everything
# stays in its historical place next to the code.
_STATE_DIR_ENV = os.environ.get("VIDEO_ARCHIVE_STATE_DIR")
STATE_DIR = Path(_STATE_DIR_ENV) if _STATE_DIR_ENV else BACKEND_DIR

DATABASE_PATH = STATE_DIR / "video_archive.db"
SECRETS_PATH = STATE_DIR / "secrets.env"

# Local, per-source cache of generated preview assets (user request): kept on
# the backend's own disk rather than written back to the source, so previews
# stay fast regardless of source protocol and survive switching away from a
# source and back without regenerating. See `app/preview_cache.py`.
PREVIEW_CACHE_DIR = STATE_DIR / "preview_cache"
