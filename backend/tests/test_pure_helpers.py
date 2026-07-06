"""Unit tests for small pure helpers with easy-to-regress logic and no
external dependency: media naming rules (`app/media.py`), ffmpeg command
construction and variant naming (`app/conversion.py` — the command an
external ffmpeg process is invoked with, without running it), aspect-ratio
resolution (`app/preview_settings.py`), and collage frame-to-tile selection
(`app/preview.py`) with hand-built detection metadata — no ffmpeg, no
models, no database.
"""

from __future__ import annotations

from pathlib import Path

from app.conversion import build_ffmpeg_command, effective_max_dimension, encode_variant_suffix
from app.media import is_test_artifact, sibling_relative_path
from app.preview import select_frames_for_tiles
from app.preview_layouts import compute_layout_tiles
from app.preview_settings import effective_aspect_ratio


# --- media naming rules --------------------------------------------------


def test_is_test_artifact():
    assert is_test_artifact("clip.original.mp4")
    assert is_test_artifact("clip.variant-d1000-crf28.mp4")
    assert not is_test_artifact("clip.mp4")
    assert not is_test_artifact("original.mp4")  # marker includes both dots
    assert not is_test_artifact("variant.mp4")


def test_sibling_relative_path():
    assert sibling_relative_path("a/b/clip.mp4", "clip.jpg") == "a/b/clip.jpg"
    assert sibling_relative_path("clip.mp4", "clip.jpg") == "clip.jpg"
    # Never produces backslashes, even on Windows (SMB-safe posix paths).
    assert "\\" not in sibling_relative_path("a/b/clip.mp4", "clip.jpg")


# --- conversion: resize decision, variant naming, command construction ---


def test_effective_max_dimension_resizes_only_when_source_exceeds_limit():
    info = {"width": 1920, "height": 1080}
    assert effective_max_dimension(info, 1280) == 1280
    assert effective_max_dimension(info, 1920) is None  # equal: no resize
    assert effective_max_dimension(info, 4000) is None
    # Portrait: the larger side (height) drives the decision.
    assert effective_max_dimension({"width": 1080, "height": 1920}, 1280) == 1280
    assert effective_max_dimension(None, 1280) is None
    assert effective_max_dimension(info, None) is None
    assert effective_max_dimension({"width": None, "height": None}, 1280) is None


def test_encode_variant_suffix():
    profile = {"video_codec": "h265", "crf": 28, "max_dimension": None}
    assert encode_variant_suffix(profile, {}) == "crf28"
    assert encode_variant_suffix(profile, {"max_dimension": 1000}) == "d1000-crf28"
    assert encode_variant_suffix(profile, {"video_codec": "h264", "max_dimension": 1000, "crf": 30}) == "h264-d1000-crf30"
    # Same codec as the profile is not repeated in the suffix.
    assert encode_variant_suffix(profile, {"video_codec": "h265", "crf": 30}) == "crf30"


def test_build_ffmpeg_command_shape():
    args = build_ffmpeg_command(
        Path("in.mp4"), Path("out.mp4"), video_codec="h265", crf=28, drop_audio=False
    )
    assert args[-1] == "out.mp4"
    assert args[args.index("-i") + 1] == "in.mp4"
    assert args[args.index("-c:v") + 1] == "libx265"
    assert args[args.index("-crf") + 1] == "28"
    assert "-vf" not in args  # no max_dimension: no scale filter
    assert "-an" not in args
    assert args[args.index("-c:a") + 1] == "copy"


def test_build_ffmpeg_command_scale_audio_and_extra_args():
    args = build_ffmpeg_command(
        Path("in.mp4"),
        Path("out.mp4"),
        video_codec="h264",
        crf=23,
        drop_audio=True,
        max_dimension=1280,
        extra_encoder_args=["-preset", "fast"],
    )
    assert args[args.index("-c:v") + 1] == "libx264"
    assert "-an" in args and "-c:a" not in args
    scale = args[args.index("-vf") + 1]
    assert "1280" in scale and scale.startswith("scale=")
    assert args[args.index("-preset") + 1] == "fast"
    # Unknown codec names pass through as the encoder itself.
    passthrough = build_ffmpeg_command(
        Path("i"), Path("o"), video_codec="mycodec", crf=20, drop_audio=True
    )
    assert passthrough[passthrough.index("-c:v") + 1] == "mycodec"


# --- preview settings: aspect ratio resolution ---------------------------


def test_effective_aspect_ratio():
    assert effective_aspect_ratio({"aspect_ratio": "standard"}) == 4 / 3
    assert effective_aspect_ratio({"aspect_ratio": "ultra-wide"}) == 21 / 9
    assert effective_aspect_ratio(
        {"aspect_ratio": "custom", "aspect_ratio_custom_width": 16, "aspect_ratio_custom_height": 10}
    ) == 1.6
    # Missing custom dimensions fall back to 1 each, never divide by zero.
    assert effective_aspect_ratio(
        {"aspect_ratio": "custom", "aspect_ratio_custom_width": None, "aspect_ratio_custom_height": None}
    ) == 1.0
    # Unknown preset name falls back to standard.
    assert effective_aspect_ratio({"aspect_ratio": "bogus"}) == 4 / 3


# --- preview: frame-to-tile selection ------------------------------------


def _frame_info(*, faces=(), persons=(), blur=0.0) -> dict:
    return {
        "faces": [
            {"confidence": c, "bbox": [0, 0, w, h], "row": None} for (c, w, h) in faces
        ],
        "persons": [
            {"confidence": c, "bbox": [0, 0, w, h]} for (c, w, h) in persons
        ],
        "blur": blur,
    }


def test_select_frames_for_tiles_prefers_faces_then_persons_for_enlarged():
    # 3x3 grid with one 2x2 enlarged tile -> 1 enlarged + 5 small = 6 tiles.
    tiles = compute_layout_tiles(3, 3, [{"row": 0, "col": 0, "span": 2}])
    frame_infos = [
        _frame_info(blur=10.0),
        _frame_info(persons=[(0.9, 100, 200)], blur=5.0),
        _frame_info(faces=[(0.9, 50, 50)], blur=1.0),
        _frame_info(blur=20.0),
        _frame_info(blur=15.0),
        _frame_info(blur=2.0),
    ]
    assignment = select_frames_for_tiles(tiles, [None] * 6, frame_infos, False, "row")

    assert sorted(assignment.keys()) == list(range(6))
    assert sorted(assignment.values()) == list(range(6))  # every frame used once

    enlarged_idx = next(i for i, t in enumerate(tiles) if t["type"] == "enlarged")
    assert assignment[enlarged_idx] == 2  # the face frame wins over person/blur

    # Small tiles (row-major) receive the remaining frames in timeline order.
    small_indices = [i for i, t in enumerate(tiles) if t["type"] == "small"]
    assert [assignment[i] for i in small_indices] == [0, 1, 3, 4, 5]


def test_select_frames_for_tiles_falls_back_to_person_then_blur():
    # 2x3 grid with one 2x2 enlarged tile -> 1 enlarged + 2 small = 3 tiles
    # (one frame per tile).
    tiles = compute_layout_tiles(2, 3, [{"row": 0, "col": 0, "span": 2}])
    enlarged_idx = next(i for i, t in enumerate(tiles) if t["type"] == "enlarged")

    # No faces anywhere: the enlarged tile takes the person frame.
    frame_infos = [
        _frame_info(blur=50.0),
        _frame_info(persons=[(0.8, 10, 10)], blur=1.0),
        _frame_info(blur=10.0),
    ]
    assignment = select_frames_for_tiles(tiles, [None] * 3, frame_infos, False, "row")
    assert assignment[enlarged_idx] == 1

    # No faces and no persons: sharpest (highest blur score) frame wins.
    frame_infos = [_frame_info(blur=1.0), _frame_info(blur=50.0), _frame_info(blur=10.0)]
    assignment = select_frames_for_tiles(tiles, [None] * 3, frame_infos, False, "row")
    assert assignment[enlarged_idx] == 1


def test_select_frames_for_tiles_column_flow_orders_by_column():
    tiles = compute_layout_tiles(2, 2, [])  # 4 small tiles, row-major
    frame_infos = [_frame_info(blur=float(i)) for i in range(4)]
    assignment = select_frames_for_tiles(tiles, [None] * 4, frame_infos, False, "column")

    by_pos = {(t["row"], t["col"]): assignment[i] for i, t in enumerate(tiles)}
    # Column flow: frames run down each column before moving right.
    assert [by_pos[(0, 0)], by_pos[(1, 0)], by_pos[(0, 1)], by_pos[(1, 1)]] == [0, 1, 2, 3]
