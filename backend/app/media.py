"""Supported media file rules shared by scan and browsing (Tech Stack)."""

from __future__ import annotations

SUPPORTED_VIDEO_EXTENSIONS = frozenset(
    {
        "mp4", "m4v", "mov", "mkv", "webm", "avi", "wmv", "flv", "mpg", "mpeg",
        "m2v", "ts", "m2ts", "mts", "vob", "3gp", "3g2", "ogv", "asf", "divx", "rmvb",
    }
)

# Technical folder excluded from scanning (Specification §5.3).
TECHNICAL_FOLDER_NAME = ".video-archive"

# Fixed folder-preview file name (Specification §9.5).
FOLDER_PREVIEW_FILENAME = "folder-preview.jpg"
