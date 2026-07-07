"""Supported media file rules shared by scan and browsing (Tech Stack)."""

from __future__ import annotations

from pathlib import PurePosixPath

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

# Fixed folder-preview file name (Specification §9.5). An animated GIF
# (user request) rather than a static collage, so it can cycle through
# frames sampled from different videos/subfolders for diversity.
FOLDER_PREVIEW_FILENAME = "folder-preview.gif"

# Sub-folder of the technical folder holding animated GIF preview loops
# (grid/list-view hover animation, user request). Kept off to the side
# instead of next to the video like `<name>.jpg`, since a GIF is a UI asset
# rather than archived library content.
PREVIEW_GIF_DIR = f"{TECHNICAL_FOLDER_NAME}/previews"


def preview_gif_relative_path(rel_path: str) -> str:
    """Deterministic path for `rel_path`'s animated GIF preview, flattened
    into `PREVIEW_GIF_DIR`: the full relative path (directories included)
    with `/` replaced by `__`, so the file name alone still shows which
    folder/video it belongs to, while staying unique across the source."""
    encoded = PurePosixPath(rel_path).with_suffix(".gif").as_posix().replace("/", "__")
    return f"{PREVIEW_GIF_DIR}/{encoded}"


def is_test_artifact(file_name: str) -> bool:
    """True for preserved originals and variant outputs, excluded from bulk
    conversion/preview/tag runs (Job Model "Skip-Processed Rule")."""
    return ORIGINAL_MARKER in file_name or VARIANT_MARKER in file_name


def sibling_relative_path(rel_path: str, new_name: str) -> str:
    """The relative path of `new_name` placed next to `rel_path` (same
    directory). Used by convert/preview/tag jobs to derive an output's
    relative path from a source file's, without ever touching a real
    `pathlib.Path` (SMB sources have no real local directory) — see
    `app/sources/access.py`."""
    parent = PurePosixPath(rel_path).parent
    return new_name if str(parent) == "." else f"{parent.as_posix()}/{new_name}"
