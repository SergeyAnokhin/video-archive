"""Supported media file rules shared by scan and browsing (Tech Stack)."""

from __future__ import annotations

# Naming markers for test-mode artifacts (Specification §8.2-8.3): preserved
# originals and variant-comparison outputs. Bulk workflows (folder-level
# convert/preview/tag) always exclude files matching either marker; they can
# still be processed individually on explicit user action.
ORIGINAL_MARKER = ".original."
VARIANT_MARKER = ".variant-"

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


def is_test_artifact(file_name: str) -> bool:
    """True for preserved originals and variant outputs, excluded from bulk
    conversion/preview/tag runs (Job Model "Skip-Processed Rule")."""
    return ORIGINAL_MARKER in file_name or VARIANT_MARKER in file_name
