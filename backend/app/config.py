"""Backend-wide constants and paths."""

from pathlib import Path

APP_VERSION = "0.1.0"

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = BACKEND_DIR / "video_archive.db"
SECRETS_PATH = BACKEND_DIR / "secrets.env"

# Local, per-source cache of generated preview assets (user request): kept on
# the backend's own disk rather than written back to the source, so previews
# stay fast regardless of source protocol and survive switching away from a
# source and back without regenerating. See `app/preview_cache.py`.
PREVIEW_CACHE_DIR = BACKEND_DIR / "preview_cache"
