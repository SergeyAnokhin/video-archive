"""Backend-wide constants and paths."""

from pathlib import Path

APP_VERSION = "0.1.0"

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = BACKEND_DIR / "video_archive.db"
