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

from app import preview, preview_layouts, preview_settings
from app.jobs import preview as preview_job
from app.jobs import service
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


def test_generate_folder_preview_writes_jpeg(tmp_path):
    video_a = tmp_path / "a.mp4"
    video_b = tmp_path / "b.mp4"
    make_video(video_a, duration=2.0, size="320x240")
    make_video(video_b, duration=2.0, size="320x240")

    dest_path = tmp_path / "folder-preview.jpg"
    preview.generate_folder_preview([video_a, video_b], 4, dest_path, "My Folder", 4 / 3)

    assert dest_path.exists()
    with Image.open(dest_path) as img:
        assert img.format == "JPEG"


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
    assert (source["root"] / "clips" / "movie.jpg").exists()

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
    assert (source["root"] / "folder-preview.jpg").exists()
    assert (source["root"] / "clips" / "folder-preview.jpg").exists()
    assert (source["root"] / "clips" / "nested" / "folder-preview.jpg").exists()

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
    first_mtime = (source["root"] / "clips" / "movie.jpg").stat().st_mtime

    job2 = service.create_job(engine, "preview", "source", None, {"path": "", "skip_processed": True})
    service.start_job(engine, job2["id"])
    status, message = preview_job.run_preview_job(engine, job2)

    assert status == "completed"
    assert "1 skipped" in message
    assert (source["root"] / "clips" / "movie.jpg").stat().st_mtime == first_mtime


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


def test_preview_settings_singleton_roundtrip(engine):
    updated = preview_settings.update_settings(
        engine, {"aspect_ratio": "ultra-wide", "folder_preview_frame_count": 6}
    )
    assert updated["aspect_ratio"] == "ultra-wide"
    assert updated["folder_preview_frame_count"] == 6
    assert preview_settings.get_settings(engine) == updated
