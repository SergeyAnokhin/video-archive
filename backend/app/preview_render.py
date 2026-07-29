"""PIL rendering of the two preview artifacts: the JPEG collage
(`render_collage()`) written next to its video, and the small looping animated
GIF (`render_gif()`) used for grid/list-view hover thumbnails.

Takes already-extracted frames (`app/preview_frames.py`) and already-assigned
tiles (`app/preview.py`); does no ffmpeg work and no frame selection of its own.
"""

from __future__ import annotations

from pathlib import Path

import cv2
from PIL import Image, ImageDraw, ImageFont

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


_GIF_PALETTE_THUMB_SIZE = 32


def _build_shared_gif_palette(frames: list, colors: int):
    """One `colors`-color palette shared by every output frame (user
    request, chat 2026-07-25 -- slow preview generation): built from a small
    thumbnail of each frame pasted into one strip, so quantizing it costs
    roughly one frame's worth of work regardless of how many frames the GIF
    actually has, instead of a full-resolution ADAPTIVE search per frame."""
    strip = Image.new(
        "RGB", (_GIF_PALETTE_THUMB_SIZE * len(frames), _GIF_PALETTE_THUMB_SIZE)
    )
    for index, frame in enumerate(frames):
        thumb = frame.resize((_GIF_PALETTE_THUMB_SIZE, _GIF_PALETTE_THUMB_SIZE), Image.BILINEAR)
        strip.paste(thumb, (index * _GIF_PALETTE_THUMB_SIZE, 0))
    return strip.quantize(colors=colors)


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

    # One shared palette built from all frames (previously: a separate
    # ADAPTIVE palette computed per frame -- expensive at 100+ frames and
    # prone to visible color flicker between frames since each one picked
    # its own best-fit colors independently).
    shared_palette = _build_shared_gif_palette(output_frames, colors)
    palette_frames = [frame.quantize(palette=shared_palette, dither=Image.FLOYDSTEINBERG) for frame in output_frames]

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    palette_frames[0].save(
        dest_path,
        format="GIF",
        save_all=True,
        append_images=palette_frames[1:],
        duration=durations,
        loop=0,
    )
