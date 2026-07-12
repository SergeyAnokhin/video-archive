"""Tagging job frame preparation (Specification §12.2): sample interior
frames using the same strategy as previews (`app/sampling.py`), then package
them for a vision provider request — either as one combined grid collage
(the default per Settings §5) or as separate per-frame JPEGs. The pixel
resolution each image is sent at is user-configurable (`tagging_settings.
image_resolution`, Settings §5): each frame's longest side, whether it ends
up in a collage cell or sent separately — aspect ratio is always preserved.

The collage here is a plain, uniform grid (no enlarged tiles, no caption):
tagging only needs the model to see the frames, unlike preview collages
which are a user-facing visual artifact (Specification §9.2).
"""

from __future__ import annotations

import math
from io import BytesIO
from pathlib import Path

import cv2
from PIL import Image

from app import conversion
from app.preview import extract_frame_image, fill_missing_frames
from app.sampling import sample_interior_timestamps
from app.tagging_settings import DEFAULT_IMAGE_RESOLUTION

JPEG_QUALITY = 85


class TaggingInputError(Exception):
    """Raised when frames cannot be extracted for tagging."""


def _grid_dims(count: int) -> tuple[int, int]:
    cols = max(1, math.ceil(math.sqrt(count)))
    rows = max(1, math.ceil(count / cols))
    return rows, cols


def _encode_jpeg(image_bgr) -> bytes:
    ok, buf = cv2.imencode(".jpg", image_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
    if not ok:
        raise TaggingInputError("Failed to encode a sampled frame as JPEG.")
    return buf.tobytes()


def _resize_max_dim(image_bgr, max_dim: int):
    """Resize `image_bgr` so its longest side is `max_dim`, preserving
    aspect ratio (used for the per-frame, non-collage path)."""
    height, width = image_bgr.shape[:2]
    scale = max_dim / max(height, width)
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return cv2.resize(image_bgr, new_size, interpolation=cv2.INTER_LANCZOS4)


def _compose_grid(images: list, rows: int, cols: int, max_dim_px: int) -> bytes:
    """Lay `images` out in a `rows` x `cols` grid. Each frame keeps its
    original aspect ratio, scaled so its longest side is `max_dim_px`; the
    cell size is the largest such frame, and smaller frames are centered
    within their cell rather than stretched to fill it."""
    resized = [_resize_max_dim(image_bgr, max_dim_px) for image_bgr in images]
    cell_width = max(img.shape[1] for img in resized)
    cell_height = max(img.shape[0] for img in resized)
    canvas = Image.new("RGB", (cols * cell_width, rows * cell_height), (0, 0, 0))
    for idx, image_bgr in enumerate(resized):
        pil_image = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
        row, col = divmod(idx, cols)
        offset_x = col * cell_width + (cell_width - pil_image.width) // 2
        offset_y = row * cell_height + (cell_height - pil_image.height) // 2
        canvas.paste(pil_image, (offset_x, offset_y))
    buf = BytesIO()
    canvas.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def sample_frames(video_path: Path, frame_count: int) -> list:
    info = conversion.probe_media(video_path)
    if info is None or not info.get("has_video_stream") or not info.get("duration"):
        raise TaggingInputError("Source is not a probeable video with a video stream and duration.")

    timestamps = sample_interior_timestamps(info["duration"], frame_count)
    images = fill_missing_frames([extract_frame_image(video_path, ts) for ts in timestamps])
    images = [img for img in images if img is not None]
    if not images:
        raise TaggingInputError("Could not extract any frames from the source video.")
    return images


def build_tagging_images(
    video_path: Path, frame_count: int, combine_into_collage: bool, image_resolution: int = DEFAULT_IMAGE_RESOLUTION
) -> list[bytes]:
    """Returns a list of JPEG-encoded images to attach to the provider
    request: one composed collage, or one JPEG per sampled frame. Each frame
    is scaled, preserving aspect ratio, so its longest side is
    `image_resolution` pixels."""
    images = sample_frames(video_path, frame_count)

    if not combine_into_collage:
        return [_encode_jpeg(_resize_max_dim(img, image_resolution)) for img in images]

    rows, cols = _grid_dims(len(images))
    cell_count = rows * cols
    padded = list(images)
    while len(padded) < cell_count:
        padded.append(images[len(padded) % len(images)])
    return [_compose_grid(padded[:cell_count], rows, cols, image_resolution)]
