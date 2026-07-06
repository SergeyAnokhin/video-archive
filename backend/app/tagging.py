"""Tagging job frame preparation (Specification §12.2): sample interior
frames using the same strategy as previews (`app/sampling.py`), then package
them for a vision provider request — either as one combined grid collage
(the default per Settings §5) or as separate per-frame JPEGs.

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

CELL_SIZE_PX = 360
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


def _compose_grid(images: list, rows: int, cols: int) -> bytes:
    canvas = Image.new("RGB", (cols * CELL_SIZE_PX, rows * CELL_SIZE_PX), (0, 0, 0))
    for idx, image_bgr in enumerate(images):
        pil_image = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB))
        pil_image = pil_image.resize((CELL_SIZE_PX, CELL_SIZE_PX), Image.LANCZOS)
        row, col = divmod(idx, cols)
        canvas.paste(pil_image, (col * CELL_SIZE_PX, row * CELL_SIZE_PX))
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


def build_tagging_images(video_path: Path, frame_count: int, combine_into_collage: bool) -> list[bytes]:
    """Returns a list of JPEG-encoded images to attach to the provider
    request: one composed collage, or one JPEG per sampled frame."""
    images = sample_frames(video_path, frame_count)

    if not combine_into_collage:
        return [_encode_jpeg(img) for img in images]

    rows, cols = _grid_dims(len(images))
    cell_count = rows * cols
    padded = list(images)
    while len(padded) < cell_count:
        padded.append(images[len(padded) % len(images)])
    return [_compose_grid(padded[:cell_count], rows, cols)]
