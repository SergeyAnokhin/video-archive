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

# Standalone images (post-V1, user request): natively decodable by cv2/PIL
# without extra codecs. Disjoint from SUPPORTED_VIDEO_EXTENSIONS by
# construction -- a file is classified as at most one of the two.
SUPPORTED_IMAGE_EXTENSIONS = frozenset(
    {"jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff", "tif"}
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


def folder_gif_relative_path(directory_relative_path: str) -> str:
    """Deterministic path for a directory's animated `folder-preview.gif`,
    mirrored under `PREVIEW_GIF_DIR` rather than written into the directory
    itself."""
    base = f"{PREVIEW_GIF_DIR}/{directory_relative_path}" if directory_relative_path else PREVIEW_GIF_DIR
    return f"{base}/{FOLDER_PREVIEW_FILENAME}"


def file_row_to_dict(row, **extra) -> dict:
    """Common file summary fields shared by the `files` and `directories`
    listing endpoints (`app/routers/files.py`, `app/routers/directories.py`),
    which otherwise each hand-rolled this dict and had to be patched
    separately for the same field. `extra` covers the few fields that
    genuinely differ between the two endpoints (e.g. `relative_path` vs.
    `duration_seconds`)."""
    return {
        "id": row.id,
        "file_name": row.file_name,
        "extension": row.extension,
        "size_bytes": row.size_bytes,
        "modified_at": row.modified_at,
        "is_video_supported": bool(row.is_video_supported),
        "is_image_supported": bool(row.is_image_supported),
        "has_preview_asset": bool(row.has_preview_asset),
        "converted_at": row.converted_at,
        "tagged_at": row.tagged_at,
        "is_variant": VARIANT_MARKER in row.file_name,
        "is_original": ORIGINAL_MARKER in row.file_name,
        "variant_tags": [],
        "ai_tags": [],
        **extra,
    }


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


def resolve_variant_preview_flags(rows: list[tuple[str, str, str, bool]]) -> dict[str, bool]:
    """Given `(file_id, directory_id, file_name, has_preview_asset)` tuples,
    returns each file's *effective* preview-availability flag for display
    purposes. A variant-sweep output never gets its own preview generated
    (Specification §8.3) -- it's visually near-identical to the original it
    was tuned from -- so it borrows its original sibling's flag whenever
    that sibling is present in `rows` (same directory, matching base stem);
    `routers/files.py`'s `_preview_source_row` already serves the borrowed
    asset itself when `/preview.jpg`/`/preview.gif` is requested, this just
    lets listing endpoints know a thumbnail is actually available so they
    render it instead of a fallback icon. Non-variant files and variants
    that do have their own generated preview pass their own flag through
    unchanged."""
    originals_by_key: dict[tuple[str, str], bool] = {}
    for _, directory_id, file_name, has_preview_asset in rows:
        if variant_base_stem(file_name) is None:
            stem = PurePosixPath(file_name).stem
            originals_by_key.setdefault((directory_id, stem), bool(has_preview_asset))

    result: dict[str, bool] = {}
    for file_id, directory_id, file_name, has_preview_asset in rows:
        base_stem = variant_base_stem(file_name)
        if base_stem is None or has_preview_asset:
            result[file_id] = bool(has_preview_asset)
        else:
            result[file_id] = originals_by_key.get((directory_id, base_stem), False)
    return result


_VARIANT_TAG_ORDER = ("codec", "dimension", "crf")


def compute_variant_tags(rows: list[tuple[str, str]]) -> dict[str, list[dict]]:
    """For a set of `(file_id, relative_path)` pairs — possibly spanning
    several directories — identify the tuning parameter(s) that distinguish
    each variant from its sibling variants (i.e. the axis/axes the user
    swept in `FileTuneModal`), so the UI can badge "this is the CRF-26 one"
    etc. Only variants sharing the same directory and original stem are
    compared against each other; a lone variant (no siblings left in its
    group, e.g. every other comparison output was deleted after review) is
    still tagged with all of its own tuning parameters instead of being left
    unlabeled (user request) — there's nothing to compare it against, but
    the parameters it was generated with are informative on their own.

    A group can vary on more than one axis at once — e.g. a dimension sweep
    and a later CRF sweep both left siblings next to the same source file —
    so every varying axis is tagged rather than hiding the whole group when
    more than one differs.

    Returns `{file_id: [{"param": "dimension"|"crf"|"codec", "value": ...}, ...]}`
    for the files at least one tag could be determined for, ordered the same
    way `conversion.encode_variant_suffix()` encodes them into the file name."""
    groups: dict[tuple[str, str], list[tuple[str, str, dict]]] = {}
    for file_id, relative_path in rows:
        path = PurePosixPath(relative_path)
        base = variant_base_stem(path.name)
        if base is None:
            continue
        group_key = (path.parent.as_posix(), base)
        groups.setdefault(group_key, []).append((file_id, path.name, parse_variant_suffix(path.name)))

    tags: dict[str, list[dict]] = {}
    for members in groups.values():
        if len(members) < 2:
            for file_id, _, parsed in members:
                file_tags = [{"param": key, "value": parsed[key]} for key in _VARIANT_TAG_ORDER if key in parsed]
                if file_tags:
                    tags[file_id] = file_tags
            continue
        keys = {key for _, _, parsed in members for key in parsed}
        varying = {key for key in keys if len({parsed.get(key) for _, _, parsed in members}) > 1}
        if not varying:
            continue
        order = [key for key in _VARIANT_TAG_ORDER if key in varying]
        for file_id, _, parsed in members:
            file_tags = [{"param": key, "value": parsed[key]} for key in order if key in parsed]
            if file_tags:
                tags[file_id] = file_tags
    return tags
