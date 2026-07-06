"""Preview collage generation (Specification §9): frame sampling + local
detection-based tile selection + PIL collage rendering, used by the
`preview` job handler (`app/jobs/preview.py`) for both video previews and
folder previews.

Frame extraction shells out to ffmpeg per sampled timestamp (small frame
counts per video, so this stays cheap); detection is always best-effort via
`app/detection.py` and never blocks a preview from being produced — a frame
is picked by blur score alone when no face/person model is available.
"""

from __future__ import annotations

import math
import random
import subprocess
import uuid
from pathlib import Path

import cv2
from PIL import Image, ImageDraw, ImageFont

from app import conversion, detection
from app.preview_layouts import compute_layout_tiles
from app.sampling import sample_interior_timestamps

CANVAS_WIDTH = 2048
JPEG_QUALITY = 85
MARGIN_PX = 6
GAP_PX = 4
CAPTION_HEIGHT_PX = 40
CAPTION_COLOR = (230, 230, 230)


class PreviewError(Exception):
    """Raised when a preview cannot be produced at all (no probeable video
    stream, or no frame could be extracted)."""


# --- frame extraction -----------------------------------------------------


def _extract_frame_image(video_path: Path, timestamp: float):
    ffmpeg_bin = conversion.ffmpeg_path()
    if not ffmpeg_bin:
        return None

    tmp_path = video_path.parent / f".{video_path.stem}.preview-frame-{uuid.uuid4().hex[:8]}.jpg"
    args = [
        ffmpeg_bin, "-y",
        "-ss", f"{timestamp:.3f}",
        "-i", str(video_path),
        "-frames:v", "1", "-q:v", "2",
        str(tmp_path),
    ]
    try:
        result = subprocess.run(args, capture_output=True, timeout=30, check=False)
        if result.returncode != 0 or not tmp_path.exists():
            return None
        return cv2.imread(str(tmp_path))
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _fill_missing(images: list):
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


# --- file (video) preview ----------------------------------------------------


def generate_file_preview(video_path: Path, dest_path: Path, *, layout: dict, aspect_ratio: float) -> None:
    tiles = compute_layout_tiles(layout["grid_rows"], layout["grid_cols"], layout["layout_definition"])

    info = conversion.probe_media(video_path)
    if info is None or not info.get("has_video_stream") or not info.get("duration"):
        raise PreviewError("Source is not a probeable video with a video stream and duration.")

    timestamps = sample_interior_timestamps(info["duration"], len(tiles))
    images = _fill_missing([_extract_frame_image(video_path, ts) for ts in timestamps])
    if not any(img is not None for img in images):
        raise PreviewError("Could not extract any frames from the source video.")

    frame_infos = [_score_frame(img) for img in images]
    assignment = select_frames_for_tiles(
        tiles, images, frame_infos, layout["identity_diversity_enabled"], layout["timeline_flow"]
    )
    ordered_images = [images[assignment[i]] for i in range(len(tiles))]

    render_collage(
        ordered_images, tiles, video_path.name, aspect_ratio, dest_path,
        grid_rows=layout["grid_rows"], grid_cols=layout["grid_cols"],
    )


# --- folder preview -----------------------------------------------------


def _grid_dims_for_count(count: int) -> tuple[int, int]:
    cols = max(1, math.ceil(math.sqrt(count)))
    rows = max(1, math.ceil(count / cols))
    return rows, cols


def _evenly_spaced(items: list, count: int) -> list:
    if len(items) <= count:
        return list(items)
    if count <= 1:
        return [items[len(items) // 2]]
    step = (len(items) - 1) / (count - 1)
    return [items[round(i * step)] for i in range(count)]


def _pick_representative_frame(video_path: Path, candidate_count: int = 3):
    info = conversion.probe_media(video_path)
    if info is None or not info.get("duration"):
        return None

    timestamps = sample_interior_timestamps(info["duration"], candidate_count) or [info["duration"] / 2]
    candidates = [img for ts in timestamps if (img := _extract_frame_image(video_path, ts)) is not None]
    if not candidates:
        return None

    infos = [_score_frame(img) for img in candidates]
    for idx, frame_info in enumerate(infos):
        if frame_info["faces"]:
            return candidates[idx]
    for idx, frame_info in enumerate(infos):
        if frame_info["persons"]:
            return candidates[idx]
    best_idx = max(range(len(candidates)), key=lambda i: infos[i]["blur"])
    return candidates[best_idx]


def generate_folder_preview(
    video_paths: list[Path], frame_count: int, dest_path: Path, caption: str, aspect_ratio: float
) -> None:
    if not video_paths:
        raise PreviewError("No videos available to build a folder preview.")

    chosen_paths = _evenly_spaced(video_paths, frame_count)
    images = [img for img in (_pick_representative_frame(p) for p in chosen_paths) if img is not None]
    if not images:
        raise PreviewError("Could not extract any frames for the folder preview.")

    rows, cols = _grid_dims_for_count(frame_count)
    cell_count = rows * cols
    base_images = list(images)
    while len(images) < cell_count:
        images.append(base_images[len(images) % len(base_images)])
    images = images[:cell_count]

    tiles = compute_layout_tiles(rows, cols, [])
    render_collage(images, tiles, caption, aspect_ratio, dest_path, grid_rows=rows, grid_cols=cols)
