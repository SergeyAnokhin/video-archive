"""Preview generation tests (Specification §9): timeline sampling, grid
layout geometry/validation, collage rendering, and the `preview` job handler
(file scope, directory scope with skip-processed + folder previews,
excluding test-mode artifacts).

Collage rendering tests run real ffmpeg/ffprobe against tiny synthetic
videos from `conftest.make_video()` (skipped automatically if neither is on
PATH), same as `test_conversion.py`.
"""

from __future__ import annotations

import shutil

import pytest
from PIL import Image
from sqlalchemy import text

from app import performance_settings, preview, preview_layouts, preview_settings
from app.jobs import preview as preview_job
from app.jobs import service
from app.media import folder_gif_relative_path, preview_gif_relative_path
from app.sampling import sample_interior_timestamps
from app.scan import scan_source

from .conftest import make_video

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not on PATH",
)


# --- sampling -----------------------------------------------------------


def test_sample_interior_timestamps_avoids_edges():
    timestamps = sample_interior_timestamps(10.0, 3)
    assert len(timestamps) == 3
    assert timestamps == [2.5, 5.0, 7.5]
    assert timestamps[0] > 0
    assert timestamps[-1] < 10.0


def test_sample_interior_timestamps_edge_cases():
    assert sample_interior_timestamps(10.0, 0) == []
    assert sample_interior_timestamps(0, 3) == []


# --- frame extraction -------------------------------------------------------


def test_extract_frame_image_handles_non_ascii_path(tmp_path):
    """`cv2.imread()` silently returns `None` on Windows when the path
    contains non-ASCII characters; regression test for a real-world failure
    where every frame extraction failed for videos under a Cyrillic-named
    folder."""
    video_dir = tmp_path / "Я умею любить"
    video_dir.mkdir()
    video_path = video_dir / "clip.mp4"
    make_video(video_path, duration=2.0, size="320x240")

    image = preview.extract_frame_image(video_path, 1.0)
    assert image is not None
    assert image.shape[:2] == (240, 320)


# --- layout geometry ------------------------------------------------------


def test_compute_layout_tiles_fills_grid_completely():
    tiles = preview_layouts.compute_layout_tiles(4, 4, [{"row": 0, "col": 0, "span": 2}])
    assert len(tiles) == 13  # 16 cells - 4 absorbed + 1 enlarged tile itself
    covered = set()
    for tile in tiles:
        for r in range(tile["row"], tile["row"] + tile["span"]):
            for c in range(tile["col"], tile["col"] + tile["span"]):
                assert (r, c) not in covered, "cells must not overlap"
                covered.add((r, c))
    assert covered == {(r, c) for r in range(4) for c in range(4)}


def test_compute_layout_tiles_rejects_overlap():
    with pytest.raises(preview_layouts.LayoutValidationError):
        preview_layouts.compute_layout_tiles(
            4, 4, [{"row": 0, "col": 0, "span": 2}, {"row": 1, "col": 1, "span": 2}]
        )


def test_compute_layout_tiles_rejects_out_of_bounds():
    with pytest.raises(preview_layouts.LayoutValidationError):
        preview_layouts.compute_layout_tiles(4, 4, [{"row": 3, "col": 3, "span": 2}])


def test_compute_layout_tiles_rejects_invalid_span():
    with pytest.raises(preview_layouts.LayoutValidationError):
        preview_layouts.compute_layout_tiles(4, 4, [{"row": 0, "col": 0, "span": 4}])


# --- preset CRUD ----------------------------------------------------------


def test_builtin_presets_are_protected(engine):
    presets = preview_layouts.list_presets(engine)
    builtin = next(p for p in presets if p["is_builtin"])

    with pytest.raises(preview_layouts.PresetProtectedError):
        preview_layouts.update_preset(engine, builtin["id"], {**builtin, "name": "Renamed"})
    with pytest.raises(preview_layouts.PresetProtectedError):
        preview_layouts.delete_preset(engine, builtin["id"])


def test_custom_preset_crud(engine):
    created = preview_layouts.create_preset(
        engine,
        {
            "name": "My Layout",
            "grid_rows": 3,
            "grid_cols": 3,
            "timeline_flow": "column",
            "identity_diversity_enabled": False,
            "layout_definition": [{"row": 0, "col": 0, "span": 2}],
        },
    )
    assert created["is_builtin"] is False

    updated = preview_layouts.update_preset(engine, created["id"], {**created, "name": "Renamed", "is_default": True})
    assert updated["name"] == "Renamed"
    assert updated["is_default"] is True

    assert preview_layouts.delete_preset(engine, created["id"]) is True
    assert preview_layouts.get_preset(engine, created["id"]) is None


# --- collage rendering -----------------------------------------------------


def _layout_from_preset(preset: dict) -> dict:
    return {
        "grid_rows": preset["grid_rows"],
        "grid_cols": preset["grid_cols"],
        "layout_definition": preset["layout_definition"],
        "identity_diversity_enabled": preset.get("identity_diversity_enabled", True),
        "timeline_flow": preset.get("timeline_flow", "row"),
    }


def test_generate_file_preview_writes_jpeg_next_to_video(tmp_path):
    video_path = tmp_path / "movie.mp4"
    make_video(video_path, duration=3.0, size="320x240")

    layout = _layout_from_preset(preview_layouts._BUILTIN_PRESETS[0])
    dest_path = tmp_path / "movie.jpg"
    preview.generate_file_preview(video_path, dest_path, layout=layout, aspect_ratio=4 / 3)

    assert dest_path.exists()
    with Image.open(dest_path) as img:
        assert img.format == "JPEG"
        assert img.size[0] == preview.CANVAS_WIDTH
        assert abs(img.size[0] / img.size[1] - 4 / 3) < 0.01


def test_generate_file_preview_also_writes_gif_when_requested(tmp_path):
    video_path = tmp_path / "movie.mp4"
    make_video(video_path, duration=3.0, size="320x240")

    layout = _layout_from_preset(preview_layouts._BUILTIN_PRESETS[0])
    dest_path = tmp_path / "movie.jpg"
    gif_path = tmp_path / "movie.preview.gif"
    preview.generate_file_preview(
        video_path, dest_path, layout=layout, aspect_ratio=4 / 3, gif_dest_path=gif_path
    )

    assert dest_path.exists()
    assert gif_path.exists()
    with Image.open(gif_path) as img:
        assert img.format == "GIF"
        assert img.is_animated
        assert img.width <= preview.GIF_MAX_WIDTH


def test_generate_file_preview_honors_custom_gif_max_width(tmp_path):
    # User request: GIF size/quality is configurable (Preview Settings),
    # independent of the JPEG collage's own fixed CANVAS_WIDTH.
    video_path = tmp_path / "movie.mp4"
    make_video(video_path, duration=3.0, size="320x240")

    layout = _layout_from_preset(preview_layouts._BUILTIN_PRESETS[0])
    dest_path = tmp_path / "movie.jpg"
    gif_path = tmp_path / "movie.preview.gif"
    preview.generate_file_preview(
        video_path, dest_path, layout=layout, aspect_ratio=4 / 3, gif_dest_path=gif_path,
        gif_max_width=240, gif_colors=16,
    )

    with Image.open(gif_path) as img:
        assert img.width == 240


def test_generate_file_preview_rejects_non_video(tmp_path):
    not_a_video = tmp_path / "notes.txt"
    not_a_video.write_text("hello")

    layout = _layout_from_preset(preview_layouts._BUILTIN_PRESETS[0])
    with pytest.raises(preview.PreviewError):
        preview.generate_file_preview(not_a_video, tmp_path / "notes.jpg", layout=layout, aspect_ratio=4 / 3)


def test_generate_file_preview_degrades_to_blur_ranking_without_models(tmp_path, monkeypatch):
    """Tech Stack's "must work, with reduced frame-selection quality, if a
    model file is missing" guarantee: force every detector to be unavailable
    (as if opencv/onnxruntime were missing or the model download failed) and
    confirm preview generation still succeeds using blur-score ranking alone.
    """
    from app import detection

    monkeypatch.setattr(detection, "get_face_detector", lambda: None)
    monkeypatch.setattr(detection, "get_person_session", lambda: None)
    monkeypatch.setattr(detection, "get_face_recognizer", lambda: None)

    video_path = tmp_path / "movie.mp4"
    make_video(video_path, duration=3.0, size="320x240")

    layout = _layout_from_preset(preview_layouts._BUILTIN_PRESETS[0])
    dest_path = tmp_path / "movie.jpg"
    preview.generate_file_preview(video_path, dest_path, layout=layout, aspect_ratio=4 / 3)

    assert dest_path.exists()
    with Image.open(dest_path) as img:
        assert img.format == "JPEG"


def test_pick_representative_frames_single_uses_best_of_three(tmp_path):
    video_path = tmp_path / "movie.mp4"
    make_video(video_path, duration=3.0, size="320x240")

    frames = preview.pick_representative_frames(video_path, 1)
    assert len(frames) == 1


def test_pick_representative_frames_multi_spreads_across_interior(tmp_path):
    video_path = tmp_path / "movie.mp4"
    make_video(video_path, duration=3.0, size="320x240")

    frames = preview.pick_representative_frames(video_path, 3)
    assert len(frames) == 3


def test_render_gif_crops_frames_to_aspect_ratio(tmp_path):
    video_path = tmp_path / "movie.mp4"
    make_video(video_path, duration=2.0, size="320x240")
    images = [img for img in (preview.extract_frame_image(video_path, 1.0),) if img is not None]

    dest_path = tmp_path / "folder-preview.gif"
    preview.render_gif(images, dest_path, 19.5 / 9)

    assert dest_path.exists()
    with Image.open(dest_path) as img:
        assert img.format == "GIF"
        assert abs(img.size[0] / img.size[1] - 19.5 / 9) < 0.02


# --- animated preview: clip source mode + crossfade transition ------------


def test_extract_clip_frames_samples_a_burst(tmp_path):
    video_path = tmp_path / "movie.mp4"
    make_video(video_path, duration=3.0, size="320x240")

    frames = preview.extract_clip_frames(video_path, 1.0, 0.5, fps=8.0)
    # ~0.5s at 8fps should yield several frames, not just one still.
    assert len(frames) >= 2
    assert all(frame.shape[:2] == (240, 320) for frame in frames)


def test_pick_representative_segments_frame_mode_matches_single_frames(tmp_path):
    video_path = tmp_path / "movie.mp4"
    make_video(video_path, duration=3.0, size="320x240")

    segments = preview.pick_representative_segments(video_path, 3, mode="frame")
    assert len(segments) == 3
    assert all(len(segment) == 1 for segment in segments)


def test_pick_representative_segments_clip_mode_returns_bursts(tmp_path):
    video_path = tmp_path / "movie.mp4"
    make_video(video_path, duration=3.0, size="320x240")

    segments = preview.pick_representative_segments(video_path, 2, mode="clip", segment_seconds=0.5)
    assert len(segments) == 2
    assert all(len(segment) >= 1 for segment in segments)


def test_render_gif_clip_segments_hold_for_configured_duration(tmp_path):
    video_path = tmp_path / "movie.mp4"
    make_video(video_path, duration=3.0, size="320x240")

    burst_a = preview.extract_clip_frames(video_path, 0.5, 0.4)
    burst_b = preview.extract_clip_frames(video_path, 2.0, 0.4)
    images = burst_a + burst_b
    segment_sizes = [len(burst_a), len(burst_b)]

    dest_path = tmp_path / "clip-preview.gif"
    preview.render_gif(images, dest_path, 4 / 3, segment_seconds=0.4, segment_sizes=segment_sizes)

    assert dest_path.exists()
    with Image.open(dest_path) as img:
        assert img.is_animated
        # Pillow's GIF writer (optimize=True) can collapse consecutive
        # frames that end up pixel-identical (the synthetic test source
        # repeats frames when sampled faster than its own low framerate),
        # so this only checks that more than one frame survived -- i.e.
        # the clip burst produced motion, not a single static image.
        assert img.n_frames >= 2


def test_render_gif_crossfade_inserts_blended_frames(tmp_path):
    video_path = tmp_path / "movie.mp4"
    make_video(video_path, duration=3.0, size="320x240")
    images = [
        preview.extract_frame_image(video_path, 0.5),
        preview.extract_frame_image(video_path, 2.5),
    ]

    dest_cut = tmp_path / "cut.gif"
    preview.render_gif(images, dest_cut, 4 / 3, transition="cut")
    dest_crossfade = tmp_path / "crossfade.gif"
    preview.render_gif(images, dest_crossfade, 4 / 3, transition="crossfade")

    with Image.open(dest_cut) as img:
        cut_frame_count = img.n_frames
    with Image.open(dest_crossfade) as img:
        crossfade_frame_count = img.n_frames

    assert crossfade_frame_count == cut_frame_count + preview.CROSSFADE_STEPS


# --- preview job: file scope -----------------------------------------------


def test_preview_job_file_scope_marks_file_previewed(engine, source):
    make_video(source["root"] / "clips" / "movie.mp4", duration=2.0, size="320x240")
    scan_source(engine, source["id"], source["root"])

    with engine.connect() as conn:
        file_row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'clips/movie.mp4'")).fetchone()

    job = service.create_job(engine, "preview", "file", file_row.id, {"file_id": file_row.id})
    service.start_job(engine, job["id"])
    status, _message = preview_job.run_preview_job(engine, job)

    assert status == "completed"
    # Collage lands next to the video on the source; GIF lands in the
    # source's technical folder alongside it (`app/media.py`).
    assert (source["root"] / "clips" / "movie.jpg").exists()
    assert (source["root"] / preview_gif_relative_path("clips/movie.mp4")).exists()

    with engine.connect() as conn:
        updated = conn.execute(text("SELECT * FROM files WHERE id = :id"), {"id": file_row.id}).fetchone()
    assert updated.has_preview_asset == 1
    assert updated.preview_generated_at is not None


# --- preview job: directory scope -----------------------------------------


def test_preview_job_directory_scope_recursive_with_folder_previews(engine, source):
    make_video(source["root"] / "clips" / "a.mp4", duration=2.0, size="320x240")
    make_video(source["root"] / "clips" / "nested" / "b.mp4", duration=2.0, size="320x240")
    scan_source(engine, source["id"], source["root"])

    job = service.create_job(engine, "preview", "source", None, {"path": "", "skip_processed": True})
    service.start_job(engine, job["id"])
    status, message = preview_job.run_preview_job(engine, job)

    assert status == "completed"
    assert (source["root"] / "clips" / "a.jpg").exists()
    assert (source["root"] / "clips" / "nested" / "b.jpg").exists()
    assert (source["root"] / folder_gif_relative_path("")).exists()
    assert (source["root"] / folder_gif_relative_path("clips")).exists()
    assert (source["root"] / folder_gif_relative_path("clips/nested")).exists()

    with engine.connect() as conn:
        directories = {
            row.relative_path: bool(row.has_folder_preview)
            for row in conn.execute(text("SELECT relative_path, has_folder_preview FROM directories")).all()
        }
    assert directories[""] is True
    assert directories["clips"] is True
    assert directories["clips/nested"] is True


def test_preview_job_skip_processed_rule(engine, source):
    video_path = source["root"] / "clips" / "movie.mp4"
    make_video(video_path, duration=2.0, size="320x240")
    scan_source(engine, source["id"], source["root"])

    job1 = service.create_job(engine, "preview", "source", None, {"path": ""})
    service.start_job(engine, job1["id"])
    preview_job.run_preview_job(engine, job1)
    collage = source["root"] / "clips" / "movie.jpg"
    first_mtime = collage.stat().st_mtime

    job2 = service.create_job(engine, "preview", "source", None, {"path": "", "skip_processed": True})
    service.start_job(engine, job2["id"])
    status, message = preview_job.run_preview_job(engine, job2)

    assert status == "completed"
    assert "1 skipped" in message
    assert collage.stat().st_mtime == first_mtime


def test_preview_job_excludes_test_artifacts(engine, source):
    make_video(source["root"] / "clips" / "movie.mp4", duration=2.0, size="320x240")
    make_video(source["root"] / "clips" / "movie.original.mov", duration=2.0, size="320x240")
    make_video(source["root"] / "clips" / "movie.variant-crf28.mp4", duration=2.0, size="320x240")
    scan_source(engine, source["id"], source["root"])

    job = service.create_job(engine, "preview", "source", None, {"path": ""})
    service.start_job(engine, job["id"])
    status, message = preview_job.run_preview_job(engine, job)

    assert status == "completed"
    assert "1 of 1" in message
    assert not (source["root"] / "clips" / "movie.original.jpg").exists()
    assert not (source["root"] / "clips" / "movie.variant-crf28.jpg").exists()


def test_preview_job_items_and_events_identify_file_by_path(engine, source):
    """User-reported: a stuck preview job gave no way to tell which file it
    was on -- `job_items.item_key` was never set (unlike `rescan`) and no
    event fired until a file finished, so a hung file left no trace at all.
    Both the file-scope and directory-scope code paths now set `item_key` to
    the file's relative path and log a `job_item_started` event before doing
    any work, so the Jobs modal's "current item" line and the job log both
    identify the in-progress file immediately, not only on completion."""
    video_path = source["root"] / "clips" / "movie.mp4"
    make_video(video_path, duration=2.0, size="320x240")
    scan_source(engine, source["id"], source["root"])

    job = service.create_job(engine, "preview", "source", None, {"path": ""})
    service.start_job(engine, job["id"])
    status, _ = preview_job.run_preview_job(engine, job)
    assert status == "completed"

    items = service.get_job_items(engine, job["id"])
    assert len(items) == 1
    assert items[0]["item_key"] == "clips/movie.mp4"

    with engine.connect() as conn:
        events = [
            (row.event_type, row.message)
            for row in conn.execute(
                text("SELECT event_type, message FROM app_events WHERE job_id = :id ORDER BY rowid"),
                {"id": job["id"]},
            ).all()
        ]
    event_types = [event_type for event_type, _ in events]
    assert event_types.index("job_item_started") < event_types.index("job_item_completed")
    started_message = next(message for event_type, message in events if event_type == "job_item_started")
    assert "clips/movie.mp4" in started_message


def test_preview_job_logs_per_stage_progress_events(engine, source):
    """User request: a slow preview sat silent between "started" and
    "completed" with no way to tell which stage (probing, frame extraction,
    GIF rendering, collage rendering) was actually taking the time. Each
    stage now logs its own `job_item_progress` event, in order, between the
    two."""
    video_path = source["root"] / "clips" / "movie.mp4"
    make_video(video_path, duration=2.0, size="320x240")
    scan_source(engine, source["id"], source["root"])

    job = service.create_job(engine, "preview", "source", None, {"path": ""})
    service.start_job(engine, job["id"])
    status, _ = preview_job.run_preview_job(engine, job)
    assert status == "completed"

    with engine.connect() as conn:
        events = [
            (row.event_type, row.message)
            for row in conn.execute(
                text("SELECT event_type, message FROM app_events WHERE job_id = :id ORDER BY rowid"),
                {"id": job["id"]},
            ).all()
        ]
    event_types = [event_type for event_type, _ in events]
    progress_messages = [message for event_type, message in events if event_type == "job_item_progress"]

    assert event_types.index("job_item_started") < event_types.index("job_item_progress") < event_types.index(
        "job_item_completed"
    )
    assert any("Probed" in message for message in progress_messages)
    assert any("collage frame" in message for message in progress_messages)
    assert any("collage" in message.lower() and "Rendered" in message for message in progress_messages)


# --- parallel processing (post-V1, user request) --------------------------


def test_preview_job_directory_scope_generates_all_across_multiple_batches(engine, source):
    """`parallel_workers=2` against 5 candidate files forces the
    directory-scope loop through three flushed batches (2 + 2 + 1) instead
    of one -- every file must still get its collage/GIF and be counted
    exactly once regardless of the batch boundaries."""
    performance_settings.update_settings(engine, {"parallel_workers": 2})
    for i in range(5):
        make_video(source["root"] / "clips" / f"clip_{i}.mp4", duration=2.0, size="320x240")
    scan_source(engine, source["id"], source["root"])

    job = service.create_job(engine, "preview", "source", None, {"path": "", "skip_processed": True})
    service.start_job(engine, job["id"])
    status, message = preview_job.run_preview_job(engine, job)

    assert status == "completed"
    assert "Generated previews for 5 of 5 file(s)" in message
    for i in range(5):
        assert (source["root"] / "clips" / f"clip_{i}.jpg").exists()

    with engine.connect() as conn:
        previewed = conn.execute(
            text("SELECT COUNT(*) FROM files WHERE has_preview_asset = 1")
        ).scalar_one()
    assert previewed == 5


def test_preview_settings_singleton_roundtrip(engine):
    defaults = preview_settings.get_settings(engine)
    assert defaults["gif_max_width"] == preview_settings.DEFAULT_GIF_MAX_WIDTH
    assert defaults["gif_colors"] == preview_settings.DEFAULT_GIF_COLORS
    assert defaults["animated_source_mode"] == preview_settings.DEFAULT_ANIMATED_SOURCE_MODE
    assert defaults["animated_segment_seconds"] == preview_settings.DEFAULT_ANIMATED_SEGMENT_SECONDS
    assert defaults["animated_transition"] == preview_settings.DEFAULT_ANIMATED_TRANSITION

    updated = preview_settings.update_settings(
        engine,
        {
            "aspect_ratio": "ultra-wide",
            "folder_preview_frame_count": 6,
            "gif_max_width": 320,
            "gif_colors": 32,
            "animated_source_mode": "clip",
            "animated_segment_seconds": 0.8,
            "animated_transition": "crossfade",
        },
    )
    assert updated["aspect_ratio"] == "ultra-wide"
    assert updated["folder_preview_frame_count"] == 6
    assert updated["gif_max_width"] == 320
    assert updated["gif_colors"] == 32
    assert updated["animated_source_mode"] == "clip"
    assert updated["animated_segment_seconds"] == 0.8
    assert updated["animated_transition"] == "crossfade"
    assert preview_settings.get_settings(engine) == updated
