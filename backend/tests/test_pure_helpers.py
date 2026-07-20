"""Unit tests for small pure helpers with easy-to-regress logic and no
external dependency: media naming rules (`app/media.py`), ffmpeg command
construction and variant naming (`app/conversion.py` — the command an
external ffmpeg process is invoked with, without running it), aspect-ratio
resolution (`app/preview_settings.py`), collage frame-to-tile selection
(`app/preview.py`) with hand-built detection metadata, and detection math
(`app/detection.py` — greedy NMS, cosine-distance fallback) — no ffmpeg, no
models, no database.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app import detection
from app.conversion import build_ffmpeg_command, effective_max_dimension, encode_variant_suffix
from app.media import (
    PREVIEW_GIF_DIR,
    compute_variant_tags,
    is_test_artifact,
    parse_variant_suffix,
    preview_gif_relative_path,
    sibling_relative_path,
    variant_base_stem,
)
from app.preview import diverse_video_frame_plan, select_frames_for_tiles
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


def test_preview_gif_relative_path():
    # Flattened into PREVIEW_GIF_DIR, directory separators encoded so the
    # name alone still shows the source folder/file it belongs to.
    assert (
        preview_gif_relative_path("Foscam/2026/05/06/alarm.mp4")
        == f"{PREVIEW_GIF_DIR}/Foscam__2026__05__06__alarm.gif"
    )
    assert preview_gif_relative_path("clip.mp4") == f"{PREVIEW_GIF_DIR}/clip.gif"
    # Two different source files never collide.
    assert preview_gif_relative_path("a/clip.mp4") != preview_gif_relative_path("b/clip.mp4")


def test_variant_base_stem():
    assert variant_base_stem("clip.variant-d1000-crf28.mp4") == "clip"
    assert variant_base_stem("clip.mp4") is None


def test_parse_variant_suffix():
    assert parse_variant_suffix("clip.variant-d1000-crf28.mp4") == {"dimension": 1000, "crf": 28}
    assert parse_variant_suffix("clip.variant-crf28.mp4") == {"crf": 28}
    assert parse_variant_suffix("clip.variant-h264-d1000-crf30.mp4") == {
        "codec": "h264",
        "dimension": 1000,
        "crf": 30,
    }
    assert parse_variant_suffix("clip.mp4") == {}


def test_compute_variant_tags_identifies_the_swept_axis():
    # A CRF sweep: dimension stays fixed, crf varies -> tagged by crf.
    rows = [
        ("a", "clip.variant-d1920-crf22.mp4"),
        ("b", "clip.variant-d1920-crf26.mp4"),
        ("c", "clip.variant-d1920-crf30.mp4"),
    ]
    tags = compute_variant_tags(rows)
    assert tags == {
        "a": [{"param": "crf", "value": 22}],
        "b": [{"param": "crf", "value": 26}],
        "c": [{"param": "crf", "value": 30}],
    }


def test_compute_variant_tags_identifies_dimension_sweep():
    rows = [
        ("a", "clip.variant-d960-crf26.mp4"),
        ("b", "clip.variant-d1440-crf26.mp4"),
        ("c", "clip.variant-d1920-crf26.mp4"),
    ]
    tags = compute_variant_tags(rows)
    assert tags["a"] == [{"param": "dimension", "value": 960}]
    assert tags["c"] == [{"param": "dimension", "value": 1920}]


def test_compute_variant_tags_tags_every_varying_axis_when_sweeps_accumulate():
    # Two separate tuning sweeps left siblings next to the same source file
    # (a dimension sweep, then later a CRF sweep): both axes vary across the
    # combined group, so both get tagged instead of the whole group being
    # hidden.
    rows = [
        ("a", "clip.variant-d960-crf22.mp4"),
        ("b", "clip.variant-d1920-crf30.mp4"),
    ]
    tags = compute_variant_tags(rows)
    assert tags["a"] == [{"param": "dimension", "value": 960}, {"param": "crf", "value": 22}]
    assert tags["b"] == [{"param": "dimension", "value": 1920}, {"param": "crf", "value": 30}]


def test_compute_variant_tags_tags_lone_variant_with_its_own_params():
    # A single variant has no siblings to compare against, but it's still
    # tagged with its own tuning parameters (user request -- e.g. the last
    # surviving output after deleting the rest of a comparison group), not
    # left unlabeled.
    assert compute_variant_tags([("a", "clip.variant-crf28.mp4")]) == {
        "a": [{"param": "crf", "value": 28}]
    }

    # Non-variant files are simply left out of grouping entirely, but a lone
    # variant next to one is still tagged with its own parameters.
    rows = [("a", "clip.mp4"), ("b", "clip.variant-crf28.mp4")]
    assert compute_variant_tags(rows) == {"b": [{"param": "crf", "value": 28}]}


def test_compute_variant_tags_scopes_groups_to_their_directory():
    # Same stem in two different directories must not be compared to each
    # other -- each is a lone variant within its own folder, so each is
    # tagged with its own parameters rather than against the other's.
    rows = [
        ("a", "movies/clip.variant-crf22.mp4"),
        ("b", "clips/clip.variant-crf30.mp4"),
    ]
    assert compute_variant_tags(rows) == {
        "a": [{"param": "crf", "value": 22}],
        "b": [{"param": "crf", "value": 30}],
    }


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


def test_build_ffmpeg_command_applies_preset_for_software_encoder():
    args = build_ffmpeg_command(
        Path("in.mp4"), Path("out.mp4"), video_codec="h265", crf=26, drop_audio=True, preset="veryfast",
    )
    assert args[args.index("-preset") + 1] == "veryfast"


def test_build_ffmpeg_command_omits_preset_for_hardware_encoder():
    """qsv/vaapi encoders don't share x264/x265's `-preset` vocabulary, so it
    must be dropped once a hardware mapping is in effect."""
    args = build_ffmpeg_command(
        Path("in.mp4"), Path("out.mp4"), video_codec="h264", crf=26, drop_audio=True,
        hardware_accel="qsv", preset="veryfast",
    )
    assert "-preset" not in args


def test_build_ffmpeg_command_faststart_for_mp4_only():
    """User report: a converted mp4's moov atom otherwise lands at the end
    of the file, forcing the embedded player to stall on a Range-streamed
    file before it can start playback. `+faststart` is mp4-specific, so it
    must not be added for other containers."""
    mp4_args = build_ffmpeg_command(
        Path("in.mp4"), Path("out.mp4"), video_codec="h264", crf=23, drop_audio=False
    )
    assert mp4_args[mp4_args.index("-movflags") + 1] == "+faststart"

    mkv_args = build_ffmpeg_command(
        Path("in.mp4"), Path("out.mkv"), video_codec="h264", crf=23, drop_audio=False
    )
    assert "-movflags" not in mkv_args


# --- preview settings: aspect ratio resolution ---------------------------


def test_effective_aspect_ratio():
    assert effective_aspect_ratio({"aspect_ratio": "standard"}) == 4 / 3
    assert effective_aspect_ratio({"aspect_ratio": "phone-landscape"}) == 19.5 / 9
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


# --- preview: folder GIF diversity plan -----------------------------------


def test_diverse_video_frame_plan_alternates_two_videos():
    # Two videos, 4 frames requested: 2 from each, alternating (not blocked)
    # so the GIF visibly cycles between sources (user request).
    plan = diverse_video_frame_plan(["a.mp4", "b.mp4"], 4)
    assert plan == ["a.mp4", "b.mp4", "a.mp4", "b.mp4"]


def test_diverse_video_frame_plan_spreads_across_four_or_more_videos():
    plan = diverse_video_frame_plan(["a.mp4", "b.mp4", "c.mp4", "d.mp4", "e.mp4"], 4)
    assert len(plan) == 4
    assert len(set(plan)) == 4  # four distinct videos, no repeats needed


def test_diverse_video_frame_plan_splits_evenly_across_subfolders():
    paths = ["sub1/a.mp4", "sub1/b.mp4", "sub2/c.mp4", "sub2/d.mp4"]
    plan = diverse_video_frame_plan(paths, 4)
    assert sum(1 for p in plan if p.startswith("sub1/")) == 2
    assert sum(1 for p in plan if p.startswith("sub2/")) == 2


def test_diverse_video_frame_plan_recurses_into_nested_subfolders():
    # sub2 has only one video: it must repeat to fill its 2-frame share.
    paths = ["sub1/a.mp4", "sub1/b.mp4", "sub2/only.mp4"]
    plan = diverse_video_frame_plan(paths, 3)
    assert sum(1 for p in plan if p.startswith("sub1/")) == 2
    assert plan.count("sub2/only.mp4") == 1


def test_diverse_video_frame_plan_edge_cases():
    assert diverse_video_frame_plan([], 4) == []
    assert diverse_video_frame_plan(["a.mp4"], 3) == ["a.mp4", "a.mp4", "a.mp4"]
    assert diverse_video_frame_plan(["a.mp4", "b.mp4"], 0) == []


# --- detection math: greedy NMS and embedding distance ---------------------


def test_nms_suppresses_overlapping_lower_scored_box():
    # Two near-identical boxes: only the higher-scored one survives; a
    # distant third box is untouched.
    boxes = [
        (0.0, 0.0, 10.0, 10.0),
        (1.0, 1.0, 11.0, 11.0),  # IoU ~0.68 with the first box
        (100.0, 100.0, 110.0, 110.0),
    ]
    scores = [0.9, 0.8, 0.5]
    assert detection._nms(boxes, scores, iou_threshold=0.5) == [0, 2]


def test_nms_orders_by_score_not_input_position():
    boxes = [(1.0, 1.0, 11.0, 11.0), (0.0, 0.0, 10.0, 10.0)]
    scores = [0.3, 0.9]  # second box wins despite coming later
    assert detection._nms(boxes, scores, iou_threshold=0.5) == [1]


def test_nms_keeps_boxes_at_or_below_iou_threshold():
    # Side-by-side boxes with zero overlap are both kept, and a box whose
    # IoU is exactly the threshold survives (`<=` comparison).
    boxes = [(0.0, 0.0, 10.0, 10.0), (10.0, 0.0, 20.0, 10.0)]
    scores = [0.9, 0.8]
    assert detection._nms(boxes, scores, iou_threshold=0.0) == [0, 1]
    # IoU of these two is exactly 1/3: kept at threshold 1/3, dropped below.
    boxes = [(0.0, 0.0, 10.0, 10.0), (5.0, 0.0, 15.0, 10.0)]
    assert detection._nms(boxes, scores, iou_threshold=1 / 3) == [0, 1]
    assert detection._nms(boxes, scores, iou_threshold=0.33) == [0]


def test_nms_empty_input():
    assert detection._nms([], []) == []


def test_embedding_distance_numpy_fallback(monkeypatch):
    # Without the SFace recognizer the numpy cosine-distance fallback runs:
    # 0 for identical direction, 1 for orthogonal, 2 for opposite.
    monkeypatch.setattr(detection, "get_face_recognizer", lambda: None)
    assert detection.embedding_distance([1.0, 0.0], [2.0, 0.0]) == pytest.approx(0.0)
    assert detection.embedding_distance([1.0, 0.0], [0.0, 1.0]) == pytest.approx(1.0)
    assert detection.embedding_distance([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(2.0)


def test_embedding_distance_zero_vector_does_not_divide_by_zero(monkeypatch):
    monkeypatch.setattr(detection, "get_face_recognizer", lambda: None)
    assert detection.embedding_distance([0.0, 0.0], [0.0, 0.0]) == pytest.approx(1.0)
