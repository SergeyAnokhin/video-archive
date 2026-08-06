"""Preview generation: frame ranking, tile assignment, and the orchestration
that turns one video (or one folder) into its JPEG collage and animated GIF.

Frames come from `app/preview_frames.py`; the collage/GIF are drawn by
`app/preview_render.py`. Detection (`app/detection.py`) is always best-effort
and never blocks a preview from being produced -- a frame is picked by blur
score alone when no face/person model is available.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from pathlib import Path

import cv2
import numpy as np

from app import conversion, detection, hardware_decode, preview_frames, preview_render
from app.preview_frames import EXTRACT_MAX_WIDTH
from app.preview_layouts import compute_layout_tiles
from app.preview_render import GIF_DEFAULT_COLORS, GIF_DEFAULT_SEGMENT_SECONDS, GIF_MAX_WIDTH
from app.sampling import sample_interior_timestamps

class PreviewError(Exception):
    """Raised when a preview cannot be produced at all (no probeable video
    stream, or no frame could be extracted)."""


# --- frame scoring and tile assignment ------------------------------------


def _score_frame(image_bgr) -> dict:
    return {
        "faces": detection.detect_faces(image_bgr),
        "persons": detection.detect_persons(image_bgr),
        "blur": detection.blur_score(image_bgr),
    }


def select_frames_for_tiles(
    tiles: list[dict],
    images: list,
    frame_infos: list[dict],
    identity_diversity_enabled: bool,
    timeline_flow: str,
) -> dict[int, int]:
    """Map each tile index to a frame index (Specification §9.2.1 "Enlarged
    tile content priority" + §10 timeline flow)."""
    n = len(tiles)
    used: set[int] = set()
    assignment: dict[int, int] = {}

    def max_face_score(i: int) -> float:
        faces = frame_infos[i]["faces"]
        return max((f["confidence"] * f["bbox"][2] * f["bbox"][3] for f in faces), default=-1.0)

    def max_person_score(i: int) -> float:
        persons = frame_infos[i]["persons"]
        return max((p["confidence"] * p["bbox"][2] * p["bbox"][3] for p in persons), default=-1.0)

    face_order = sorted((i for i in range(n) if frame_infos[i]["faces"]), key=max_face_score, reverse=True)
    person_order = sorted((i for i in range(n) if frame_infos[i]["persons"]), key=max_person_score, reverse=True)
    blur_order = sorted(range(n), key=lambda i: frame_infos[i]["blur"], reverse=True)

    def pick(*orders: list[int]) -> int | None:
        for order in (*orders, blur_order):
            for i in order:
                if i not in used:
                    return i
        return None

    enlarged_indices = [i for i, t in enumerate(tiles) if t["type"] == "enlarged"]
    small_indices = [i for i, t in enumerate(tiles) if t["type"] == "small"]

    first_two = enlarged_indices[:2]
    first_face_frame: int | None = None
    for k, tile_idx in enumerate(first_two):
        frame_idx = None
        if k == 1 and identity_diversity_enabled and first_face_frame is not None and detection.get_face_recognizer():
            remaining_faces = [i for i in face_order if i not in used]
            prev_face = frame_infos[first_face_frame]["faces"][0]
            prev_emb = detection.face_embedding(images[first_face_frame], prev_face["row"])
            if prev_emb is not None and remaining_faces:
                scored = []
                for i in remaining_faces:
                    cand_emb = detection.face_embedding(images[i], frame_infos[i]["faces"][0]["row"])
                    if cand_emb is not None:
                        scored.append((detection.embedding_distance(prev_emb, cand_emb), i))
                if scored:
                    scored.sort(key=lambda pair: pair[0], reverse=True)
                    frame_idx = scored[0][1]
        if frame_idx is None:
            frame_idx = pick(face_order, person_order)
        assignment[tile_idx] = frame_idx
        used.add(frame_idx)
        if k == 0 and frame_infos[frame_idx]["faces"]:
            first_face_frame = frame_idx

    for tile_idx in enlarged_indices[2:]:
        frame_idx = pick(person_order, face_order)
        assignment[tile_idx] = frame_idx
        used.add(frame_idx)

    ordered_small_indices = list(small_indices)  # row-major, as emitted by compute_layout_tiles
    if timeline_flow == "column":
        ordered_small_indices.sort(key=lambda i: (tiles[i]["col"], tiles[i]["row"]))

    remaining_frames = [i for i in range(n) if i not in used]
    if timeline_flow == "shuffle":
        random.shuffle(remaining_frames)

    for tile_idx, frame_idx in zip(ordered_small_indices, remaining_frames):
        assignment[tile_idx] = frame_idx

    return assignment

# --- file (video) preview ----------------------------------------------------


def generate_file_preview(
    video_path: Path,
    dest_path: Path,
    *,
    layout: dict,
    aspect_ratio: float,
    gif_dest_path: Path | None = None,
    gif_max_width: int = GIF_MAX_WIDTH,
    gif_colors: int = GIF_DEFAULT_COLORS,
    animated_source_mode: str = "frame",
    animated_segment_seconds: float = GIF_DEFAULT_SEGMENT_SECONDS,
    animated_transition: str = "cut",
    frame_seek_mode: str = "keyframe",
    max_workers: int = 1,
    on_stage: Callable[[str], None] | None = None,
) -> tuple[dict, list]:
    """Returns `(info, images)`: `info` is the source's
    `conversion.probe_media()` dict (duration, width/height, codec,
    container, bitrate), so callers can persist the technical-data cache
    columns on `files` without a second probe; `images` is the list of
    already-decoded interior BGR frames sampled for the collage (post-V1,
    user request), so a caller that also needs a similarity signature for
    this file (`app/jobs/preview.py`) can hash them directly instead of
    re-probing and re-extracting the same file from scratch via
    `app/similarity.py::compute_signature()`.

    `max_workers` (post-V1, user request, default 1 = sequential, unchanged
    prior behavior) spreads this one file's independent per-timestamp ffmpeg
    frame extractions across a thread pool -- callers doing a single file at
    a time (a `preview` job's file scope) should pass the configured
    parallelism here; callers already processing several files concurrently
    (directory scope) should keep this at 1 to avoid spawning
    `files-in-flight x max_workers` ffmpeg processes at once.

    `on_stage` (post-V1, user request) is called with a human-readable
    message after each major stage (probing, frame extraction, animated
    preview rendering, collage rendering) so a caller with job/log access
    (`app/jobs/preview.py`) can surface per-file progress -- otherwise a
    multi-minute file sits silent between "started" and "completed",
    hiding which stage is actually slow.

    `frame_seek_mode` (Preview Settings `frame_seek_mode`, user request) is
    passed straight to `preview_frames.extract_frame_image()`/`preview_frames.extract_clip_frames()` --
    see there for what "keyframe" trades off against the default "accurate".
    All frame extraction here also uses `EXTRACT_MAX_WIDTH` regardless of
    this setting. When `frame_seek_mode == "keyframe"`, collage frames are
    also passed through `preview_frames.redo_duplicate_frames()`, which
    re-extracts (with exact seeking) any tile whose fast keyframe seek
    collapsed onto the same frame as an earlier tile -- otherwise visible as
    a repeated frame in the collage grid (user report, chat 2026-08-05)."""

    def stage(message: str) -> None:
        if on_stage is not None:
            on_stage(message)

    tiles = compute_layout_tiles(layout["grid_rows"], layout["grid_cols"], layout["layout_definition"])

    t0 = time.monotonic()
    info = conversion.probe_media(video_path)
    if info is None or not info.get("has_video_stream") or not info.get("duration"):
        raise PreviewError("Source is not a probeable video with a video stream and duration.")
    stage(f"Probed source ({info['duration']:.1f}s video) in {time.monotonic() - t0:.2f}s")

    # Once per file, not once per sampled frame (post-V1, user request "make
    # it visible when hardware acceleration is actually used"): every
    # `preview_frames.extract_frame_image()`/`preview_frames.extract_clip_frames()` call below re-checks
    # this same (cached) backend on its own, so logging it here once already
    # reflects what the whole file's extraction will use.
    hw_backend = hardware_decode.decode_backend()
    if hw_backend:
        stage(f"🚀 Hardware decode active ({hw_backend.upper()}) for frame extraction")

    t0 = time.monotonic()
    stage(f"Extracting {len(tiles)} collage frame(s)")
    timestamps = sample_interior_timestamps(info["duration"], len(tiles))
    images = preview_frames.fill_missing_frames(
        preview_frames._map_parallel(
            lambda ts: preview_frames.extract_frame_image(
                video_path, ts, seek_mode=frame_seek_mode, max_width=EXTRACT_MAX_WIDTH
            ),
            timestamps,
            max_workers,
        )
    )
    if not any(img is not None for img in images):
        raise PreviewError("Could not extract any frames from the source video.")
    if frame_seek_mode == "keyframe":
        images = preview_frames.redo_duplicate_frames(video_path, timestamps, images, max_width=EXTRACT_MAX_WIDTH)
    stage(f"Extracted {len(tiles)} collage frame(s) in {time.monotonic() - t0:.2f}s")

    if gif_dest_path is not None:
        t0 = time.monotonic()
        if animated_source_mode == "clip":
            stage(f"Extracting animated preview clip segments at {len(timestamps)} position(s)")

            # Same sample timestamps as the collage (user request: "clip"
            # mode grabs a short burst of frames per position instead of one
            # still), falling back to the already-extracted still frame if
            # the clip burst comes back empty (e.g. too close to EOF).
            def _extract_segment(pair: tuple[float, object]) -> list:
                timestamp, fallback = pair
                burst = preview_frames.extract_clip_frames(
                    video_path, timestamp, animated_segment_seconds,
                    seek_mode=frame_seek_mode, max_width=EXTRACT_MAX_WIDTH,
                )
                return burst if burst else ([fallback] if fallback is not None else [])

            gif_images: list = []
            gif_segment_sizes: list[int] = []
            for segment in preview_frames._map_parallel(_extract_segment, list(zip(timestamps, images)), max_workers):
                gif_images.extend(segment)
                gif_segment_sizes.append(len(segment))
            stage(f"Extracted {len(gif_images)} animated preview frame(s) in {time.monotonic() - t0:.2f}s")

            t0 = time.monotonic()
            preview_render.render_gif(
                gif_images, gif_dest_path, aspect_ratio, max_width=gif_max_width, colors=gif_colors,
                segment_seconds=animated_segment_seconds, transition=animated_transition,
                segment_sizes=gif_segment_sizes,
            )
        else:
            stage("Reusing collage frames for animated preview")
            preview_render.render_gif(
                images, gif_dest_path, aspect_ratio, max_width=gif_max_width, colors=gif_colors,
                segment_seconds=animated_segment_seconds, transition=animated_transition,
            )
        stage(f"Rendered animated preview GIF in {time.monotonic() - t0:.2f}s")

    t0 = time.monotonic()
    stage("Scoring and selecting frames for the collage layout")
    frame_infos = [_score_frame(img) for img in images]
    assignment = select_frames_for_tiles(
        tiles, images, frame_infos, layout["identity_diversity_enabled"], layout["timeline_flow"]
    )
    ordered_images = [images[assignment[i]] for i in range(len(tiles))]

    preview_render.render_collage(
        ordered_images, tiles, video_path.name, aspect_ratio, dest_path,
        grid_rows=layout["grid_rows"], grid_cols=layout["grid_cols"],
    )
    stage(f"Rendered collage image in {time.monotonic() - t0:.2f}s")

    return info, images


# --- folder preview (animated GIF, diverse across videos/images/subfolders) -


def evenly_spaced_sample(items: list, count: int) -> list:
    if len(items) <= count:
        return list(items)
    if count <= 1:
        return [items[len(items) // 2]]
    step = (len(items) - 1) / (count - 1)
    return [items[round(i * step)] for i in range(count)]


def _spread_with_repeats(items: list, count: int) -> list:
    """Like `evenly_spaced_sample`, but when `count` exceeds `len(items)` it
    round-robins through `items` instead of returning fewer than `count`
    entries — used to fill a folder GIF's frame budget when a folder (or
    subfolder share of it) has fewer distinct videos than frames needed."""
    if not items:
        return []
    if count <= len(items):
        return evenly_spaced_sample(items, count)
    return [items[i % len(items)] for i in range(count)]


def _group_by_next_path_segment(rel_paths: list[str]) -> dict[str, list[str]]:
    """Group POSIX-style relative paths by their first path segment
    (immediate subfolder), stripping that segment from the grouped values.
    Paths with no further subdirectory (direct children) are grouped under
    the empty-string key."""
    groups: dict[str, list[str]] = {}
    for rel in rel_paths:
        head, sep, rest = rel.partition("/")
        key, value = (head, rest) if sep else ("", head)
        groups.setdefault(key, []).append(value)
    return groups


def diverse_video_frame_plan(video_paths: list[str], frame_count: int) -> list[str]:
    """Choose `frame_count` candidate files -- videos and/or standalone
    images (relative paths, repeats allowed) -- for a folder's animated GIF
    preview (user request): recursively split the frame budget evenly across
    sibling subfolders before splitting across sibling files, so the
    animation mixes frames from different subfolders/videos/images instead
    of clustering on one source. Video vs. image is irrelevant here -- the
    caller (`app/jobs/preview.py`) decides how to turn each chosen path into
    a segment. `video_paths` must be relative to the folder being previewed
    (not the source root)."""
    if frame_count <= 0 or not video_paths:
        return []

    unique_paths = sorted(set(video_paths))
    if len(unique_paths) == 1:
        return unique_paths * frame_count

    groups = _group_by_next_path_segment(video_paths)
    if len(groups) <= 1:
        return _spread_with_repeats(unique_paths, frame_count)

    ordered_keys = sorted(groups)
    base_share, extra = divmod(frame_count, len(ordered_keys))
    plan: list[str] = []
    for index, key in enumerate(ordered_keys):
        share = base_share + (1 if index < extra else 0)
        if share == 0:
            continue
        prefix = f"{key}/" if key else ""
        plan.extend(f"{prefix}{rel}" for rel in diverse_video_frame_plan(groups[key], share))
    return plan


def _pick_representative_frame_and_timestamp(video_path: Path, candidate_count: int = 3):
    info = conversion.probe_media(video_path)
    if info is None or not info.get("duration"):
        return None, None

    timestamps = sample_interior_timestamps(info["duration"], candidate_count) or [info["duration"] / 2]
    candidates = [(ts, img) for ts in timestamps if (img := preview_frames.extract_frame_image(video_path, ts)) is not None]
    if not candidates:
        return None, None

    infos = [_score_frame(img) for _, img in candidates]
    for idx, frame_info in enumerate(infos):
        if frame_info["faces"]:
            return candidates[idx]
    for idx, frame_info in enumerate(infos):
        if frame_info["persons"]:
            return candidates[idx]
    best_idx = max(range(len(candidates)), key=lambda i: infos[i]["blur"])
    return candidates[best_idx]


def _pick_representative_frame(video_path: Path, candidate_count: int = 3):
    _, frame = _pick_representative_frame_and_timestamp(video_path, candidate_count)
    return frame


def pick_representative_frames(video_path: Path, count: int) -> list:
    """Extract `count` frames from the interior of `video_path` (never the
    very first frame, Specification §9.4 sampling rule). For `count == 1`
    this reuses `_pick_representative_frame`'s face/person/blur best-of-3
    selection; for `count > 1` (a video repeated across a folder GIF's
    frame plan, Specification §9.5) it instead spreads `count` interior
    timestamps evenly, since the goal is temporal variety, not a single
    "best" frame repeated with itself."""
    if count <= 0:
        return []
    if count == 1:
        frame = _pick_representative_frame(video_path)
        return [frame] if frame is not None else []

    info = conversion.probe_media(video_path)
    if info is None or not info.get("duration"):
        return []
    timestamps = sample_interior_timestamps(info["duration"], count)
    return [img for ts in timestamps if (img := preview_frames.extract_frame_image(video_path, ts)) is not None]


def pick_image_segments(image_path: Path, count: int) -> list[list]:
    """Like `pick_representative_segments()`, but for a standalone image file
    (folder-preview candidate, user request: image-only folders previously
    got no folder-preview.gif at all since candidate selection was
    video-only). A photo has no timestamps or motion to sample, so every
    position in the plan simply repeats the same decoded frame -- the
    surrounding video segments (or other images) in the plan are what give
    the GIF its variety. Same Windows non-ASCII-path-safe decode as
    `preview_frames.extract_frame_image()` (`cv2.imread()` silently fails on paths with
    non-ASCII characters)."""
    if count <= 0:
        return []
    data = np.fromfile(str(image_path), dtype=np.uint8)
    frame = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if frame is None:
        return []
    return [[frame] for _ in range(count)]


def pick_representative_segments(
    video_path: Path,
    count: int,
    *,
    mode: str = "frame",
    segment_seconds: float = GIF_DEFAULT_SEGMENT_SECONDS,
    seek_mode: str = "keyframe",
) -> list[list]:
    """Like `pick_representative_frames`, but returns one *segment* (a list
    of 1+ frames) per position instead of a single frame, so the folder
    animated preview can render either a still frame ("frame" mode) or a
    short clip burst ("clip" mode) per video (Preview Settings
    `animated_source_mode`, user request). Falls back to a single still
    frame at the same timestamp whenever a clip burst extraction comes back
    empty (e.g. too close to EOF). `seek_mode` (Preview Settings
    `frame_seek_mode`, user request) applies to the `count > 1` extraction
    loop below; the `count == 1` best-of-3 pick reuses
    `_pick_representative_frame_and_timestamp()`, which always extracts at
    source resolution/exact timestamp (a single video's folder preview, not
    the hot multi-frame path this setting targets)."""
    if count <= 0:
        return []

    if count == 1:
        timestamp, frame = _pick_representative_frame_and_timestamp(video_path)
        if timestamp is None:
            return []
        if mode == "clip":
            burst = preview_frames.extract_clip_frames(video_path, timestamp, segment_seconds, seek_mode=seek_mode)
            if burst:
                return [burst]
        return [[frame]] if frame is not None else []

    info = conversion.probe_media(video_path)
    if info is None or not info.get("duration"):
        return []
    timestamps = sample_interior_timestamps(info["duration"], count)
    segments: list[list] = []
    for timestamp in timestamps:
        if mode == "clip":
            burst = preview_frames.extract_clip_frames(
                video_path, timestamp, segment_seconds, seek_mode=seek_mode, max_width=EXTRACT_MAX_WIDTH
            )
            if burst:
                segments.append(burst)
                continue
        frame = preview_frames.extract_frame_image(video_path, timestamp, seek_mode=seek_mode, max_width=EXTRACT_MAX_WIDTH)
        segments.append([frame] if frame is not None else [])
    return segments
