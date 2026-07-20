"""Preview collage generation (Specification §9): frame sampling + local
detection-based tile selection + PIL collage rendering, used by the
`preview` job handler (`app/jobs/preview.py`) for both video previews and
folder previews. Also renders a lightweight animated GIF loop from the same
sampled frames (`render_gif()`) for grid/list-view hover previews.

Frame extraction shells out to ffmpeg per sampled timestamp (small frame
counts per video, so this stays cheap), automatically using hardware decode
when `app/hardware_decode.py` finds it available and silently falling back
to software per call otherwise; detection is always best-effort via
`app/detection.py` and never blocks a preview from being produced — a frame
is picked by blur score alone when no face/person model is available.
"""

from __future__ import annotations

import random
import shutil
import subprocess
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app import conversion, detection, hardware_decode
from app.preview_layouts import compute_layout_tiles
from app.sampling import sample_interior_timestamps

CANVAS_WIDTH = 2048
JPEG_QUALITY = 85
MARGIN_PX = 6
GAP_PX = 4
CAPTION_HEIGHT_PX = 40
CAPTION_COLOR = (230, 230, 230)

GIF_MAX_WIDTH = 640
GIF_DEFAULT_COLORS = 64
# Default "how long each position is shown" (Preview Settings
# `animated_segment_seconds`, user request): still-frame hold time in
# "frame" mode, sampled-clip length in "clip" mode. Matches the fixed hold
# time the animated preview used before this was configurable.
GIF_DEFAULT_SEGMENT_SECONDS = 0.45
GIF_MIN_FRAME_DURATION_MS = 20
# "clip" source mode: frames-per-second sampled from the short video segment
# at each position, and a hard cap on how many frames one segment can
# contribute (guards against a pathologically long `segment_seconds`).
CLIP_SAMPLE_FPS = 8.0
CLIP_MAX_FRAMES = 24
# Crossfade transition (Preview Settings `animated_transition`, user
# request): a fixed number of alpha-blended frames inserted between
# consecutive segments, each held briefly, instead of a hard cut.
CROSSFADE_STEPS = 5
CROSSFADE_FRAME_DURATION_MS = 40


class PreviewError(Exception):
    """Raised when a preview cannot be produced at all (no probeable video
    stream, or no frame could be extracted)."""


# --- frame extraction -----------------------------------------------------


def _decode_hwaccel_backend() -> str | None:
    """Unlike encode, decode output is bit-identical to software decode (see
    `app/hardware_decode.py`), so callers use this automatically -- no
    per-profile opt-in. Thin wrapper kept here (post-V1, user request:
    `app/conversion.py`'s encode input now uses the same hw-decode backend
    selection, see `hardware_decode.decode_backend()`) so existing callers
    and tests in this module don't need to change."""
    return hardware_decode.decode_backend()


def _hwaccel_input_args(backend: str | None) -> list[str]:
    return hardware_decode.hwaccel_input_args(backend)


def _hwaccel_download_filter(backend: str | None) -> str | None:
    """Hardware decode hands back frames in a GPU-specific surface format
    (`qsv`/`vaapi` pixel format) that the mjpeg encoder can't consume
    directly -- without this, ffmpeg fails with "Impossible to convert
    between the formats" and writes nothing. `hwdownload,format=nv12` copies
    the decoded frame into normal system memory first (verified against a
    real file: identical pixel output to software decode, just faster)."""
    if backend is None:
        return None
    return "hwdownload,format=nv12"


def extract_frame_image(video_path: Path, timestamp: float):
    ffmpeg_bin = conversion.ffmpeg_path()
    if not ffmpeg_bin:
        return None

    hw_backend = _decode_hwaccel_backend()
    backends_to_try = [hw_backend, None] if hw_backend else [None]

    tmp_path = video_path.parent / f".{video_path.stem}.preview-frame-{uuid.uuid4().hex[:8]}.jpg"
    try:
        for backend in backends_to_try:
            args = [ffmpeg_bin, "-y", *_hwaccel_input_args(backend)]
            args += ["-ss", f"{timestamp:.3f}", "-i", str(video_path)]
            download_filter = _hwaccel_download_filter(backend)
            if download_filter:
                args += ["-vf", download_filter]
            args += ["-frames:v", "1", "-q:v", "2", str(tmp_path)]
            # A hardware-decode attempt failing (unsupported codec, driver
            # hiccup, GPU contention) falls through to software silently --
            # no log per call, see `app/hardware_decode.py`'s module docstring
            # for why this needs no per-profile setting like encode has.
            try:
                result = subprocess.run(args, capture_output=True, timeout=30, check=False)
            except (OSError, subprocess.SubprocessError):
                continue
            if result.returncode != 0 or not tmp_path.exists():
                continue
            # cv2.imread() silently fails (returns None) on Windows when the
            # path contains non-ASCII characters (e.g. Cyrillic folder
            # names) -- it shells out to an fopen()-style API that mangles
            # them. Reading the bytes via Python's own (Unicode-safe) file
            # I/O and decoding them in memory sidesteps that.
            data = np.fromfile(str(tmp_path), dtype=np.uint8)
            image = cv2.imdecode(data, cv2.IMREAD_COLOR)
            if image is not None:
                return image
        return None
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def extract_clip_frames(
    video_path: Path,
    start_timestamp: float,
    duration_seconds: float,
    *,
    fps: float = CLIP_SAMPLE_FPS,
    max_frames: int = CLIP_MAX_FRAMES,
) -> list:
    """Sample a burst of frames from a short video segment starting at
    `start_timestamp` ("clip" animated-preview source mode, user request):
    unlike `extract_frame_image()`'s single `-frames:v 1`, this asks ffmpeg
    for `fps` frames/second over `duration_seconds` in one invocation, giving
    the animated preview real motion for this position instead of a still.
    Returns as many decoded frames as ffmpeg produced (possibly fewer than
    expected near the end of the video, possibly empty on failure) --
    callers must tolerate a short/empty result."""
    ffmpeg_bin = conversion.ffmpeg_path()
    if not ffmpeg_bin:
        return []

    hw_backend = _decode_hwaccel_backend()
    backends_to_try = [hw_backend, None] if hw_backend else [None]

    tmp_dir = video_path.parent / f".{video_path.stem}.preview-clip-{uuid.uuid4().hex[:8]}"
    tmp_dir.mkdir(exist_ok=True)
    try:
        for backend in backends_to_try:
            args = [ffmpeg_bin, "-y", *_hwaccel_input_args(backend)]
            args += ["-ss", f"{max(0.0, start_timestamp):.3f}", "-i", str(video_path)]
            args += ["-t", f"{max(0.05, duration_seconds):.3f}"]
            download_filter = _hwaccel_download_filter(backend)
            vf = f"{download_filter},fps={fps}" if download_filter else f"fps={fps}"
            args += ["-vf", vf, "-frames:v", str(max_frames), "-q:v", "2", str(tmp_dir / "f%04d.jpg")]
            try:
                result = subprocess.run(args, capture_output=True, timeout=30, check=False)
            except (OSError, subprocess.SubprocessError):
                continue
            if result.returncode != 0:
                continue
            frames = []
            # Unicode-safe read, same reasoning as `extract_frame_image()`.
            for frame_path in sorted(tmp_dir.glob("f*.jpg")):
                data = np.fromfile(str(frame_path), dtype=np.uint8)
                image = cv2.imdecode(data, cv2.IMREAD_COLOR)
                if image is not None:
                    frames.append(image)
            if frames:
                return frames
            # Hardware attempt produced no usable frames -- clear any stray
            # output before falling back to software so a partial failure
            # can't get mixed into the next attempt's results.
            for frame_path in tmp_dir.glob("f*.jpg"):
                frame_path.unlink()
        return []
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _map_parallel(func, items: list, max_workers: int) -> list:
    """`[func(item) for item in items]`, optionally spread across a thread
    pool (post-V1, user request: a single file's independent per-timestamp
    ffmpeg frame extractions are the "one file, many threads" case for
    preview generation -- `app/jobs/convert.py`'s variant sweep is the
    equivalent for conversion). Preserves input order regardless of
    completion order, which callers rely on (frame index <-> timestamp
    index correspondence). Falls back to a plain sequential loop for
    `max_workers <= 1` or a single item, since spinning up a thread pool for
    one call only adds overhead."""
    if max_workers <= 1 or len(items) <= 1:
        return [func(item) for item in items]
    with ThreadPoolExecutor(max_workers=min(max_workers, len(items))) as executor:
        return list(executor.map(func, items))


def fill_missing_frames(images: list):
    """Replace failed extractions (`None`) with the nearest successful
    neighbor so a single ffmpeg hiccup never breaks the whole collage."""
    filled = list(images)
    for i, img in enumerate(filled):
        if img is not None:
            continue
        for offset in range(1, len(filled)):
            for j in (i - offset, i + offset):
                if 0 <= j < len(filled) and filled[j] is not None:
                    filled[i] = filled[j]
                    break
            if filled[i] is not None:
                break
    return filled


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


# --- collage rendering ------------------------------------------------------


def shrink_frame(image_bgr, max_width: int):
    """Downscale a decoded BGR frame to at most `max_width` wide, preserving
    aspect ratio (post-V1, user request): used when a frame is going to be
    cached in memory across several downstream uses (folder-preview frame
    reuse across ancestor directories, `app/jobs/preview.py`) instead of
    consumed once and discarded, so the cache holds GIF-sized frames instead
    of full source-resolution ones. A no-op (returns the same array) when
    the frame is already at or below `max_width` -- never upscales."""
    if image_bgr is None:
        return None
    height, width = image_bgr.shape[:2]
    if width <= max_width:
        return image_bgr
    scale = max_width / width
    new_size = (max_width, max(1, round(height * scale)))
    return cv2.resize(image_bgr, new_size, interpolation=cv2.INTER_AREA)


def _cover_resize(image: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Resize+center-crop to fill the target box without distortion (like
    CSS `object-fit: cover`)."""
    src_w, src_h = image.size
    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = max(1, round(src_w * scale)), max(1, round(src_h * scale))
    resized = image.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return resized.crop((left, top, left + target_w, top + target_h))


def render_collage(
    images: list,
    tiles: list[dict],
    caption: str,
    aspect_ratio: float,
    dest_path: Path,
    *,
    grid_rows: int,
    grid_cols: int,
    width: int = CANVAS_WIDTH,
    quality: int = JPEG_QUALITY,
) -> None:
    """Compose `images[i]` into `tiles[i]`'s cell on a black canvas with a
    caption bar (Specification §9.2.1). `tiles`/`images` must be the same
    length and in matching order."""
    height = round(width / aspect_ratio)
    canvas = Image.new("RGB", (width, height), (0, 0, 0))

    grid_area_width = width - 2 * MARGIN_PX
    grid_area_height = height - CAPTION_HEIGHT_PX - 2 * MARGIN_PX
    cell_w = (grid_area_width - (grid_cols - 1) * GAP_PX) / grid_cols
    cell_h = (grid_area_height - (grid_rows - 1) * GAP_PX) / grid_rows

    for tile, image_bgr in zip(tiles, images):
        x = MARGIN_PX + tile["col"] * (cell_w + GAP_PX)
        y = MARGIN_PX + tile["row"] * (cell_h + GAP_PX)
        w = tile["span"] * cell_w + (tile["span"] - 1) * GAP_PX
        h = tile["span"] * cell_h + (tile["span"] - 1) * GAP_PX

        pil_image = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
        fitted = _cover_resize(pil_image, max(1, round(w)), max(1, round(h)))
        canvas.paste(fitted, (round(x), round(y)))

    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    caption_top = height - CAPTION_HEIGHT_PX
    text_bbox = draw.textbbox((0, 0), caption, font=font)
    text_w, text_h = text_bbox[2] - text_bbox[0], text_bbox[3] - text_bbox[1]
    draw.text(
        ((width - text_w) / 2, caption_top + (CAPTION_HEIGHT_PX - text_h) / 2),
        caption,
        fill=CAPTION_COLOR,
        font=font,
    )

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(dest_path, format="JPEG", quality=quality)


# --- animated GIF preview ---------------------------------------------------


def render_gif(
    images: list,
    dest_path: Path,
    aspect_ratio: float,
    *,
    max_width: int = GIF_MAX_WIDTH,
    colors: int = GIF_DEFAULT_COLORS,
    segment_seconds: float = GIF_DEFAULT_SEGMENT_SECONDS,
    transition: str = "cut",
    segment_sizes: list[int] | None = None,
) -> None:
    """Compose frames into a small looping GIF for grid/list-view hover
    previews — a lighter, lower-fidelity companion to the JPEG collage.
    Each frame is cover-cropped to `aspect_ratio` (user request), same as
    the collage's tiles, so a native-ratio source video never appears
    letterboxed inside the fixed-ratio preview slot. `max_width`/`colors`
    (user request — GIFs previously matched the collage's fidelity despite
    only ever being shown in a small hover thumbnail) are configurable via
    `preview_settings.py`'s `gif_max_width`/`gif_colors`; a smaller palette
    shrinks file size at the cost of banding, which is an acceptable
    trade-off at this size.

    `images` is a flat, already-ordered list of frames; `segment_sizes`
    (user request, animated-preview source mode) optionally groups them into
    consecutive "positions" -- e.g. a burst of frames sampled from one short
    clip in "clip" mode -- so each position's frames together fill
    `segment_seconds` regardless of how many frames represent it. When
    omitted, every image is its own one-frame segment ("frame" mode, and the
    prior single-still-per-position behavior). `transition="crossfade"`
    inserts a few alpha-blended frames between consecutive positions instead
    of a hard cut."""
    target_w = max_width
    target_h = max(1, round(target_w / aspect_ratio))
    fitted_frames = []
    for image_bgr in images:
        if image_bgr is None:
            continue
        pil_image = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
        fitted_frames.append(_cover_resize(pil_image, target_w, target_h))
    if not fitted_frames:
        return

    if segment_sizes is None:
        segment_sizes = [1] * len(fitted_frames)

    segments = []
    cursor = 0
    for size in segment_sizes:
        if size <= 0:
            continue
        segments.append(fitted_frames[cursor : cursor + size])
        cursor += size
    if not segments:
        return

    output_frames = []
    durations = []
    for index, segment in enumerate(segments):
        per_frame_ms = max(GIF_MIN_FRAME_DURATION_MS, round(segment_seconds * 1000 / len(segment)))
        for frame in segment:
            output_frames.append(frame)
            durations.append(per_frame_ms)
        if transition == "crossfade" and index < len(segments) - 1:
            last_frame = segment[-1]
            next_frame = segments[index + 1][0]
            for step in range(1, CROSSFADE_STEPS + 1):
                alpha = step / (CROSSFADE_STEPS + 1)
                output_frames.append(Image.blend(last_frame, next_frame, alpha))
                durations.append(CROSSFADE_FRAME_DURATION_MS)

    palette_frames = [frame.convert("P", palette=Image.ADAPTIVE, colors=colors) for frame in output_frames]

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    palette_frames[0].save(
        dest_path,
        format="GIF",
        save_all=True,
        append_images=palette_frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
    )


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
    hiding which stage is actually slow."""

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
    # `extract_frame_image()`/`extract_clip_frames()` call below re-checks
    # this same (cached) backend on its own, so logging it here once already
    # reflects what the whole file's extraction will use.
    hw_backend = hardware_decode.decode_backend()
    if hw_backend:
        stage(f"🚀 Hardware decode active ({hw_backend.upper()}) for frame extraction")

    t0 = time.monotonic()
    stage(f"Extracting {len(tiles)} collage frame(s)")
    timestamps = sample_interior_timestamps(info["duration"], len(tiles))
    images = fill_missing_frames(
        _map_parallel(lambda ts: extract_frame_image(video_path, ts), timestamps, max_workers)
    )
    if not any(img is not None for img in images):
        raise PreviewError("Could not extract any frames from the source video.")
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
                burst = extract_clip_frames(video_path, timestamp, animated_segment_seconds)
                return burst if burst else ([fallback] if fallback is not None else [])

            gif_images: list = []
            gif_segment_sizes: list[int] = []
            for segment in _map_parallel(_extract_segment, list(zip(timestamps, images)), max_workers):
                gif_images.extend(segment)
                gif_segment_sizes.append(len(segment))
            stage(f"Extracted {len(gif_images)} animated preview frame(s) in {time.monotonic() - t0:.2f}s")

            t0 = time.monotonic()
            render_gif(
                gif_images, gif_dest_path, aspect_ratio, max_width=gif_max_width, colors=gif_colors,
                segment_seconds=animated_segment_seconds, transition=animated_transition,
                segment_sizes=gif_segment_sizes,
            )
        else:
            stage("Reusing collage frames for animated preview")
            render_gif(
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

    render_collage(
        ordered_images, tiles, video_path.name, aspect_ratio, dest_path,
        grid_rows=layout["grid_rows"], grid_cols=layout["grid_cols"],
    )
    stage(f"Rendered collage image in {time.monotonic() - t0:.2f}s")

    return info, images


# --- folder preview (animated GIF, diverse across videos/subfolders) ------


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
    """Choose `frame_count` videos (relative paths, repeats allowed) for a
    folder's animated GIF preview (user request): recursively split the
    frame budget evenly across sibling subfolders before splitting across
    sibling videos, so the animation mixes frames from different
    subfolders/videos instead of clustering on one source. `video_paths`
    must be relative to the folder being previewed (not the source root)."""
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
    candidates = [(ts, img) for ts in timestamps if (img := extract_frame_image(video_path, ts)) is not None]
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
    return [img for ts in timestamps if (img := extract_frame_image(video_path, ts)) is not None]


def pick_representative_segments(
    video_path: Path,
    count: int,
    *,
    mode: str = "frame",
    segment_seconds: float = GIF_DEFAULT_SEGMENT_SECONDS,
) -> list[list]:
    """Like `pick_representative_frames`, but returns one *segment* (a list
    of 1+ frames) per position instead of a single frame, so the folder
    animated preview can render either a still frame ("frame" mode) or a
    short clip burst ("clip" mode) per video (Preview Settings
    `animated_source_mode`, user request). Falls back to a single still
    frame at the same timestamp whenever a clip burst extraction comes back
    empty (e.g. too close to EOF)."""
    if count <= 0:
        return []

    if count == 1:
        timestamp, frame = _pick_representative_frame_and_timestamp(video_path)
        if timestamp is None:
            return []
        if mode == "clip":
            burst = extract_clip_frames(video_path, timestamp, segment_seconds)
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
            burst = extract_clip_frames(video_path, timestamp, segment_seconds)
            if burst:
                segments.append(burst)
                continue
        frame = extract_frame_image(video_path, timestamp)
        segments.append([frame] if frame is not None else [])
    return segments
