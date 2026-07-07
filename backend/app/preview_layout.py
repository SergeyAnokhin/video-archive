from __future__ import annotations

import math

import cv2
import numpy
from PIL import Image

from .errors import ApiError


LAYOUT_VERSION = 1
DEFAULT_PRESET_ID = "default-preview-grid"
TIMELINE_FLOW_MODES = {"row", "column", "shuffle"}

DEFAULT_PREVIEW_SETTINGS = {
    "sample_count": 9,
    "large_tile_count": 2,
    "timeline_flow": "row",
    "identity_diversity_enabled": True,
    "aspect_ratio_preset": "s24",
    "layout_preset_id": DEFAULT_PRESET_ID,
}

DEFAULT_LAYOUT_DEFINITION = {
    "kind": "auto-grid",
    "version": LAYOUT_VERSION,
}

ASPECT_RATIO_PRESETS = {
    "square": (1.0, 1.0),
    "video": (16.0, 9.0),
    "portrait": (4.0, 5.0),
    "s24": (9.0, 19.5),
    "ultrawide": (21.0, 9.0),
}


def coerce_int(value: object, field_name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ApiError("invalid_request", f"Field '{field_name}' must be an integer.", status=400)
    if value < minimum or value > maximum:
        raise ApiError("invalid_request", f"Field '{field_name}' must be between {minimum} and {maximum}.", status=400)
    return value


def resize_for_detector(image_rgb: numpy.ndarray, *, max_side: int) -> tuple[numpy.ndarray, float]:
    height, width = image_rgb.shape[:2]
    current_max = max(height, width)
    if current_max <= max_side:
        return image_rgb, 1.0
    scale = max_side / current_max
    resized = cv2.resize(image_rgb, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
    return resized, scale


def frame_to_tile_image(image_bgr: numpy.ndarray, width: int, height: int) -> Image.Image:
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    source = Image.fromarray(rgb)
    ratio = max(width / source.width, height / source.height)
    resized = source.resize((max(1, int(source.width * ratio)), max(1, int(source.height * ratio))), Image.Resampling.LANCZOS)
    left = max((resized.width - width) // 2, 0)
    top = max((resized.height - height) // 2, 0)
    return resized.crop((left, top, left + width, top + height))


def order_frames_for_flow(frames: list[object], timeline_flow: str) -> list[object]:
    if timeline_flow == "row":
        return sorted(frames, key=lambda frame: frame.sample_index)
    if timeline_flow == "column":
        return sorted(frames, key=lambda frame: (frame.sample_index % 3, frame.sample_index))
    return [frames[index] for index in shuffle_indices(len(frames))]


def shuffle_indices(length: int) -> list[int]:
    if length <= 2:
        return list(range(length))
    order: list[int] = []
    left = 0
    right = length - 1
    toggle = True
    while left <= right:
        if toggle:
            order.append(left)
            left += 1
        else:
            order.append(right)
            right -= 1
        toggle = not toggle
    return order


def parent_directory(relative_path: str) -> str:
    if "/" not in relative_path:
        return ""
    return relative_path.rsplit("/", 1)[0]


def build_preview_layout(*, sample_count: int, large_tile_count: int, timeline_flow: str, aspect_ratio_preset: str) -> dict:
    columns = 4 if sample_count >= 8 else 3 if sample_count >= 4 else 2
    aspect_width, aspect_height = ASPECT_RATIO_PRESETS[aspect_ratio_preset]
    aspect_ratio = aspect_width / aspect_height
    base_area = 140 * 140
    cell_width = max(72, int(round(math.sqrt(base_area * aspect_ratio))))
    cell_height = max(72, int(round(math.sqrt(base_area / aspect_ratio))))
    gap = 12
    large_tile_count = min(large_tile_count, sample_count)
    occupancy: list[list[bool]] = []
    tiles: list[dict] = []

    def ensure_rows(row_count: int) -> None:
        while len(occupancy) < row_count:
            occupancy.append([False] * columns)

    def can_place(start_row: int, start_col: int, row_span: int, col_span: int) -> bool:
        if start_col + col_span > columns:
            return False
        ensure_rows(start_row + row_span)
        for row_index in range(start_row, start_row + row_span):
            for col_index in range(start_col, start_col + col_span):
                if occupancy[row_index][col_index]:
                    return False
        return True

    def place_tile(is_large: bool, slot_index: int) -> None:
        row_span = 2 if is_large and columns >= 3 else 1
        col_span = 2 if is_large and columns >= 3 else 1
        row_index = 0
        while True:
            ensure_rows(row_index + row_span)
            for col_index in range(columns):
                if not can_place(row_index, col_index, row_span, col_span):
                    continue
                for fill_row in range(row_index, row_index + row_span):
                    for fill_col in range(col_index, col_index + col_span):
                        occupancy[fill_row][fill_col] = True
                tiles.append(
                    {
                        "slot_index": slot_index,
                        "is_large": is_large,
                        "x": col_index * (cell_width + gap),
                        "y": row_index * (cell_height + gap),
                        "width": (cell_width * col_span) + (gap * (col_span - 1)),
                        "height": (cell_height * row_span) + (gap * (row_span - 1)),
                        "row": row_index,
                        "column": col_index,
                    }
                )
                return
            row_index += 1

    for slot_index in range(sample_count):
        place_tile(slot_index < large_tile_count, slot_index)

    if timeline_flow == "column":
        tiles = sorted(tiles, key=lambda tile: (0 if tile["is_large"] else 1, tile["column"], tile["row"], tile["slot_index"]))
        tiles = [{**tile, "slot_index": index} for index, tile in enumerate(tiles)]
    elif timeline_flow == "shuffle":
        large_tiles = [tile for tile in tiles if tile["is_large"]]
        small_tiles = [tile for tile in tiles if not tile["is_large"]]
        shuffled_small = [small_tiles[index] for index in shuffle_indices(len(small_tiles))]
        tiles = large_tiles + shuffled_small
        tiles = [{**tile, "slot_index": index} for index, tile in enumerate(tiles)]
    else:
        tiles = sorted(tiles, key=lambda tile: (0 if tile["is_large"] else 1, tile["row"], tile["column"], tile["slot_index"]))
        tiles = [{**tile, "slot_index": index} for index, tile in enumerate(tiles)]

    total_rows = max((tile["row"] + (2 if tile["is_large"] and columns >= 3 else 1) for tile in tiles), default=1)
    return {
        "sample_count": sample_count,
        "large_tile_count": large_tile_count,
        "timeline_flow": timeline_flow,
        "aspect_ratio_preset": aspect_ratio_preset,
        "columns": columns,
        "cell_width": cell_width,
        "cell_height": cell_height,
        "gap": gap,
        "canvas_width": columns * cell_width + (columns - 1) * gap,
        "canvas_height": total_rows * cell_height + (total_rows - 1) * gap,
        "tiles": tiles,
    }
