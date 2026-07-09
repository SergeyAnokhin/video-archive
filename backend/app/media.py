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


def variant_base_stem(file_name: str) -> str | None:
    """The original file's stem for a `<stem>.variant-<params>.<ext>` name
    (Specification §8.3), or `None` if `file_name` isn't a variant output."""
    if VARIANT_MARKER not in file_name:
        return None
    return file_name.split(VARIANT_MARKER, 1)[0]


def parse_variant_suffix(file_name: str) -> dict:
    """Parse the `<params>` part of a variant's file name back into the
    pieces `conversion.encode_variant_suffix()` encoded it from, e.g.
    `clip.variant-d1000-crf28.mp4` -> `{"dimension": 1000, "crf": 28}`.
    Returns `{}` for a non-variant name."""
    base = variant_base_stem(file_name)
    if base is None:
        return {}
    suffix = PurePosixPath(file_name[len(base) + len(VARIANT_MARKER) :]).stem
    parsed: dict = {}
    for part in suffix.split("-"):
        if part.startswith("d") and part[1:].isdigit():
            parsed["dimension"] = int(part[1:])
        elif part.startswith("crf") and part[3:].isdigit():
            parsed["crf"] = int(part[3:])
        elif part:
            parsed["codec"] = part
    return parsed


def compute_variant_tags(rows: list[tuple[str, str]]) -> dict[str, dict]:
    """For a set of `(file_id, relative_path)` pairs — possibly spanning
    several directories — identify the single tuning parameter that
    distinguishes each variant from its sibling variants (i.e. the axis the
    user swept in `FileTuneModal`), so the UI can badge "this is the
    CRF-26 one" etc. Only variants sharing the same directory and original
    stem are compared against each other; a lone variant (no siblings) or a
    group where more than one parameter differs is left untagged rather than
    guessed at.

    Returns `{file_id: {"param": "dimension"|"crf"|"codec", "value": ...}}`
    for the files a confident tag could be determined for."""
    groups: dict[tuple[str, str], list[tuple[str, str, dict]]] = {}
    for file_id, relative_path in rows:
        path = PurePosixPath(relative_path)
        base = variant_base_stem(path.name)
        if base is None:
            continue
        group_key = (path.parent.as_posix(), base)
        groups.setdefault(group_key, []).append((file_id, path.name, parse_variant_suffix(path.name)))

    tags: dict[str, dict] = {}
    for members in groups.values():
        if len(members) < 2:
            continue
        keys = {key for _, _, parsed in members for key in parsed}
        varying = [key for key in keys if len({parsed.get(key) for _, _, parsed in members}) > 1]
        if len(varying) != 1:
            continue
        param = varying[0]
        for file_id, _, parsed in members:
            if param in parsed:
                tags[file_id] = {"param": param, "value": parsed[param]}
    return tags
