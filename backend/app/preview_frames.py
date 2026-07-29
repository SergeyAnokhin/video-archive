"""ffmpeg frame extraction for previews, tagging, and similarity signatures.

One ffmpeg invocation per sampled timestamp (`extract_frame_image()`) or per
short segment (`extract_clip_frames()`), automatically using hardware decode
when `app/hardware_decode.py` finds it available and silently falling back to
software per call otherwise. Rendering lives in `app/preview_render.py`;
frame ranking and preview orchestration in `app/preview.py`.
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import cv2
import numpy as np

from app import conversion, hardware_decode

# "clip" source mode: frames-per-second sampled from the short video segment
# at each position, and a hard cap on how many frames one segment can
# contribute (guards against a pathologically long `segment_seconds`).
CLIP_SAMPLE_FPS = 8.0
CLIP_MAX_FRAMES = 24

# Downscale target for collage/animated-preview frame extraction (user
# request, chat 2026-07-25 -- slow preview generation on underpowered
# hardware): >= both `CANVAS_WIDTH`'s per-tile width and `gif_max_width`'s
# default, so nothing downstream (collage tile, GIF frame, face/person
# detection) loses visible resolution. Only applied where extraction is
# explicitly passed `max_width=` (collage/animated-preview call sites) --
# other callers (AI tagging, similarity signatures computed independently
# of a preview, single-thumbnail picking) keep extracting at source
# resolution, unchanged.
EXTRACT_MAX_WIDTH = 1280

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


def extract_frame_image(
    video_path: Path, timestamp: float, *, seek_mode: str = "accurate", max_width: int | None = None
):
    """`seek_mode="keyframe"` (Preview Settings `frame_seek_mode`, user
    request) adds `-noaccurate_seek`: ffmpeg returns the nearest keyframe
    instead of decoding forward to the exact `timestamp`, which on a
    keyframe-sparse source is the difference between a ~1s and a ~20s+
    extraction. Default stays `"accurate"` (prior behavior, exact timestamp)
    since callers outside preview generation (AI tagging, standalone
    similarity signatures) don't opt into the tradeoff. `max_width` (used by
    collage/animated-preview callers only, see `EXTRACT_MAX_WIDTH`) scales
    the frame down during ffmpeg's own decode instead of after, which is
    also what makes the downstream JPEG encode/decode and face/person
    detection cheaper."""
    ffmpeg_bin = conversion.ffmpeg_path()
    if not ffmpeg_bin:
        return None

    hw_backend = _decode_hwaccel_backend()
    backends_to_try = [hw_backend, None] if hw_backend else [None]

    tmp_path = video_path.parent / f".{video_path.stem}.preview-frame-{uuid.uuid4().hex[:8]}.jpg"
    try:
        for backend in backends_to_try:
            args = [ffmpeg_bin, "-y", *_hwaccel_input_args(backend)]
            args += ["-ss", f"{timestamp:.3f}"]
            if seek_mode == "keyframe":
                args += ["-noaccurate_seek"]
            args += ["-i", str(video_path)]
            filters = []
            download_filter = _hwaccel_download_filter(backend)
            if download_filter:
                filters.append(download_filter)
            if max_width:
                filters.append(f"scale='min(iw,{max_width})':-2")
            if filters:
                args += ["-vf", ",".join(filters)]
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
    seek_mode: str = "accurate",
    max_width: int | None = None,
) -> list:
    """Sample a burst of frames from a short video segment starting at
    `start_timestamp` ("clip" animated-preview source mode, user request):
    unlike `extract_frame_image()`'s single `-frames:v 1`, this asks ffmpeg
    for `fps` frames/second over `duration_seconds` in one invocation, giving
    the animated preview real motion for this position instead of a still.
    Returns as many decoded frames as ffmpeg produced (possibly fewer than
    expected near the end of the video, possibly empty on failure) --
    callers must tolerate a short/empty result. `seek_mode`/`max_width`: see
    `extract_frame_image()`."""
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
            args += ["-ss", f"{max(0.0, start_timestamp):.3f}"]
            if seek_mode == "keyframe":
                args += ["-noaccurate_seek"]
            args += ["-i", str(video_path)]
            args += ["-t", f"{max(0.05, duration_seconds):.3f}"]
            filters = []
            download_filter = _hwaccel_download_filter(backend)
            if download_filter:
                filters.append(download_filter)
            filters.append(f"fps={fps}")
            if max_width:
                filters.append(f"scale='min(iw,{max_width})':-2")
            args += ["-vf", ",".join(filters), "-frames:v", str(max_frames), "-q:v", "2", str(tmp_dir / "f%04d.jpg")]
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

