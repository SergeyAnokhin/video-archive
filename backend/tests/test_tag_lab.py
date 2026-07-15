"""Tag Lab tests (user request): the synchronous, single-file, single-entry
alternative to the `tag` job used to compare AI providers/models. Mirrors
`test_tagging.py`'s stubbed-provider style but patches
`registry.score_tags_with_entry` (no fallback chain here) rather than
`_with_fallback`. No real network calls are made; a real provider call is a
manual/live verification step, not a unit test.
"""

from __future__ import annotations

import shutil
import uuid

import pytest
from sqlalchemy import text

from app import provider_entries, tag_lab, tag_lab_feedback, tagging_settings
from app import tags as tags_service
from app.providers import registry
from app.providers.base import ProviderError, UsageInfo
from app.scan import scan_source

from .conftest import make_image, make_video

ffmpeg_missing = shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None


def _enable_openrouter(engine, **overrides):
    data = {
        "provider_type": "openrouter",
        "display_name": "openrouter",
        "enabled": True,
        "api_key": "sk-test",
        "vision_model": "test-vision-model",
    }
    data.update(overrides)
    return provider_entries.create_entry(engine, data)


def _scanned_video_id(engine, source) -> str:
    make_video(source["root"] / "clips" / "movie.mp4", duration=2.0, size="320x240")
    scan_source(engine, source["id"], source["root"])
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'clips/movie.mp4'")).fetchone()
    return row.id


@pytest.fixture()
def stub_score_tags_with_entry(monkeypatch):
    """Fixed score per tag position, deterministic top ranking, plus a raw
    response string so the caller can assert it's threaded through."""

    def fake_score(engine, entry, images, tags, **_kwargs):
        assert images
        scores = [max(0, 90 - 10 * i) for i in range(len(tags))]
        return scores, UsageInfo(
            tokens_in=100, tokens_out=20, raw_text="[90, 80]", raw_full_response={"usage": {"total_tokens": 120}}
        )

    monkeypatch.setattr(registry, "score_tags_with_entry", fake_score)
    return fake_score


# --- run_tag_lab -------------------------------------------------------------


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_run_tag_lab_returns_images_prompt_response_and_ranked_tags(engine, source, stub_score_tags_with_entry):
    # provider_type='gemini' so the model matches app/model_pricing.py's seeded
    # ("gemini", "gemini-2.5-flash") row -- pricing is keyed by (provider_type,
    # model_name), not model_name alone.
    entry = _enable_openrouter(engine, provider_type="gemini", vision_model="gemini-2.5-flash")
    tags_service.create_tag(engine, {"display_name": "Beach"})
    tags_service.create_tag(engine, {"display_name": "Snow"})
    file_id = _scanned_video_id(engine, source)

    result = tag_lab.run_tag_lab(engine, file_id, entry["id"])

    assert result["run_id"]
    assert result["images"]
    assert all(img["data_url"].startswith("data:image/jpeg;base64,") for img in result["images"])
    assert "Beach" in result["prompt"] and "Snow" in result["prompt"]
    assert result["raw_response"] == "[90, 80]"
    assert result["raw_full_response"] == {"usage": {"total_tokens": 120}}
    assert result["tokens_in"] == 100
    assert result["tokens_out"] == 20
    assert result["estimated_cost_usd"] is not None  # gemini-2.5-flash is in the known-cost table
    assert result["provider_type"] == "gemini"
    assert result["model_name"] == "gemini-2.5-flash"
    assert [t["display_name"] for t in result["tags"]] == ["Beach", "Snow"]
    assert [t["score"] for t in result["tags"]] == [90, 80]


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_run_tag_lab_works_for_standalone_image(engine, source, stub_score_tags_with_entry):
    """Unlike `POST /tagging-settings/preview` (video-only), Tag Lab must
    also work for standalone images, since the same "Tags" button is shared
    by `FileInfoPanel` for both kinds."""
    entry = _enable_openrouter(engine)
    tags_service.create_tag(engine, {"display_name": "Beach"})
    make_image(source["root"] / "photo.jpg")
    scan_source(engine, source["id"], source["root"])
    with engine.connect() as conn:
        file_row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'photo.jpg'")).fetchone()

    result = tag_lab.run_tag_lab(engine, file_row.id, entry["id"])
    assert len(result["images"]) == 1
    assert result["tags"][0]["display_name"] == "Beach"


def test_run_tag_lab_missing_file_raises_file_not_found(engine, source):
    entry = _enable_openrouter(engine)
    tags_service.create_tag(engine, {"display_name": "Beach"})
    with pytest.raises(tag_lab.TagLabError) as excinfo:
        tag_lab.run_tag_lab(engine, str(uuid.uuid4()), entry["id"])
    assert excinfo.value.code == "file_not_found"


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_run_tag_lab_unknown_provider_entry_raises(engine, source):
    tags_service.create_tag(engine, {"display_name": "Beach"})
    file_id = _scanned_video_id(engine, source)
    with pytest.raises(tag_lab.TagLabError) as excinfo:
        tag_lab.run_tag_lab(engine, file_id, str(uuid.uuid4()))
    assert excinfo.value.code == "provider_entry_not_found"


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_run_tag_lab_empty_vocabulary_raises(engine, source):
    entry = _enable_openrouter(engine)
    file_id = _scanned_video_id(engine, source)
    with pytest.raises(tag_lab.TagLabError) as excinfo:
        tag_lab.run_tag_lab(engine, file_id, entry["id"])
    assert excinfo.value.code == "empty_tag_vocabulary"


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_run_tag_lab_entry_without_api_key_raises_provider_not_configured(engine, source):
    """No mocking needed here -- `registry.score_tags_with_entry` itself
    raises `ProviderNotConfiguredError` before any network call when the
    entry has no stored API key."""
    entry = provider_entries.create_entry(
        engine, {"provider_type": "openrouter", "display_name": "no-key", "enabled": True}
    )
    tags_service.create_tag(engine, {"display_name": "Beach"})
    file_id = _scanned_video_id(engine, source)
    with pytest.raises(tag_lab.TagLabError) as excinfo:
        tag_lab.run_tag_lab(engine, file_id, entry["id"])
    assert excinfo.value.code == "provider_not_configured"


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_run_tag_lab_provider_error_maps_to_tag_lab_failed(engine, source, monkeypatch):
    entry = _enable_openrouter(engine)
    tags_service.create_tag(engine, {"display_name": "Beach"})
    file_id = _scanned_video_id(engine, source)

    def fake_score(engine, entry, images, tags, **_kwargs):
        raise ProviderError("boom")

    monkeypatch.setattr(registry, "score_tags_with_entry", fake_score)

    with pytest.raises(tag_lab.TagLabError) as excinfo:
        tag_lab.run_tag_lab(engine, file_id, entry["id"])
    assert excinfo.value.code == "tag_lab_failed"


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_run_tag_lab_source_file_missing_raises(engine, source):
    entry = _enable_openrouter(engine)
    tags_service.create_tag(engine, {"display_name": "Beach"})
    file_id = _scanned_video_id(engine, source)
    (source["root"] / "clips" / "movie.mp4").unlink()

    with pytest.raises(tag_lab.TagLabError) as excinfo:
        tag_lab.run_tag_lab(engine, file_id, entry["id"])
    assert excinfo.value.code == "source_file_missing"


# --- image cache + prepare/timeout (user request) -----------------------------


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_run_tag_lab_reuses_cached_images_for_same_file(engine, source, monkeypatch, stub_score_tags_with_entry):
    """Re-running Tag Lab against the same video (e.g. to compare providers)
    must not re-sample frames from it a second time."""
    entry = _enable_openrouter(engine)
    tags_service.create_tag(engine, {"display_name": "Beach"})
    file_id = _scanned_video_id(engine, source)

    build_calls = []
    original_build = tag_lab.tagging.build_tagging_images_for_file

    def counting_build(*args, **kwargs):
        build_calls.append(1)
        return original_build(*args, **kwargs)

    monkeypatch.setattr(tag_lab.tagging, "build_tagging_images_for_file", counting_build)

    tag_lab.run_tag_lab(engine, file_id, entry["id"])
    tag_lab.run_tag_lab(engine, file_id, entry["id"])

    assert len(build_calls) == 1


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_run_tag_lab_rebuilds_images_when_settings_change(engine, source, monkeypatch, stub_score_tags_with_entry):
    entry = _enable_openrouter(engine)
    tags_service.create_tag(engine, {"display_name": "Beach"})
    file_id = _scanned_video_id(engine, source)

    tag_lab.run_tag_lab(engine, file_id, entry["id"])
    tagging_settings.update_settings(engine, {"image_resolution": 128})

    build_calls = []
    original_build = tag_lab.tagging.build_tagging_images_for_file

    def counting_build(*args, **kwargs):
        build_calls.append(1)
        return original_build(*args, **kwargs)

    monkeypatch.setattr(tag_lab.tagging, "build_tagging_images_for_file", counting_build)

    tag_lab.run_tag_lab(engine, file_id, entry["id"])
    assert len(build_calls) == 1


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_prepare_tag_lab_returns_images_and_prompt_without_calling_provider(engine, source, monkeypatch):
    tags_service.create_tag(engine, {"display_name": "Beach"})
    file_id = _scanned_video_id(engine, source)

    def fail_score(*_args, **_kwargs):
        raise AssertionError("prepare_tag_lab must not call the provider")

    monkeypatch.setattr(registry, "score_tags_with_entry", fail_score)

    result = tag_lab.prepare_tag_lab(engine, file_id)
    assert result["images"]
    assert all(img["data_url"].startswith("data:image/jpeg;base64,") for img in result["images"])
    assert "Beach" in result["prompt"]


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_run_tag_lab_passes_configured_timeout_to_provider(engine, source, monkeypatch):
    entry = _enable_openrouter(engine)
    tags_service.create_tag(engine, {"display_name": "Beach"})
    file_id = _scanned_video_id(engine, source)
    tagging_settings.update_settings(engine, {"request_timeout_seconds": 5})

    captured = {}

    def fake_score(engine, entry, images, tags, **kwargs):
        captured.update(kwargs)
        return [90], UsageInfo(tokens_in=1, tokens_out=1, raw_text="[90]")

    monkeypatch.setattr(registry, "score_tags_with_entry", fake_score)

    tag_lab.run_tag_lab(engine, file_id, entry["id"])
    assert captured["timeout"] == 5


# --- apply_tag_lab_result -----------------------------------------------------


def test_apply_tag_lab_result_mixes_model_and_manual_tags(engine, source):
    # apply() only writes file_tags rows given an existing file id -- no
    # ffmpeg/frame extraction involved, so a plain inserted row is enough.
    file_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, created_at, updated_at) "
                "VALUES (:id, :sid, 'd1', :id, :id, 'mp4', 1, '2024', '2024', 1, '2024', '2024')"
            ),
            {"id": file_id, "sid": source["id"]},
        )

    beach = tags_service.create_tag(engine, {"display_name": "Beach"})

    tag_lab.apply_tag_lab_result(
        engine, file_id,
        [{"tag_id": beach["id"], "score": 90}, {"display_name": "Brand New Tag"}],
        provider_type="openrouter", model_name="test-vision-model",
    )

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tc.display_name, ft.score, ft.provider_name, ft.model_name FROM file_tags ft "
                "JOIN tag_catalog tc ON tc.id = ft.tag_id WHERE ft.file_id = :fid ORDER BY ft.score DESC"
            ),
            {"fid": file_id},
        ).all()

    assert len(rows) == 2
    by_name = {row.display_name: row for row in rows}
    assert by_name["Beach"].score == 90
    assert by_name["Beach"].provider_name == "openrouter"
    assert by_name["Beach"].model_name == "test-vision-model"
    assert by_name["Brand New Tag"].score == 100
    assert by_name["Brand New Tag"].provider_name == "manual"
    assert by_name["Brand New Tag"].model_name is None
    # A manually-typed Tag Lab tag is an ordinary ad-hoc tag (user request) --
    # it must NOT silently join the AI vocabulary just because it was typed
    # during a Tag Lab review.
    assert all(t["display_name"] != "Brand New Tag" for t in tags_service.list_tags(engine))


def test_apply_tag_lab_result_drops_stale_tag_id(engine, source):
    file_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, created_at, updated_at) "
                "VALUES (:id, :sid, 'd1', :id, :id, 'mp4', 1, '2024', '2024', 1, '2024', '2024')"
            ),
            {"id": file_id, "sid": source["id"]},
        )
    beach = tags_service.create_tag(engine, {"display_name": "Beach"})
    stale_id = beach["id"]
    tags_service.delete_tag(engine, stale_id)

    valid = tags_service.create_tag(engine, {"display_name": "Snow"})

    tag_lab.apply_tag_lab_result(
        engine, file_id,
        [{"tag_id": stale_id, "score": 90}, {"tag_id": valid["id"], "score": 50}],
        provider_type="openrouter", model_name="test-vision-model",
    )

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT tag_id FROM file_tags WHERE file_id = :fid"), {"fid": file_id}).all()
    assert [row.tag_id for row in rows] == [valid["id"]]


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_apply_tag_lab_result_with_run_id_records_apply_kpi(engine, source, stub_score_tags_with_entry):
    entry = _enable_openrouter(engine, vision_model="gemini-2.5-flash")
    tags_service.create_tag(engine, {"display_name": "Beach"})
    tags_service.create_tag(engine, {"display_name": "Snow"})
    file_id = _scanned_video_id(engine, source)

    result = tag_lab.run_tag_lab(engine, file_id, entry["id"])
    suggested_ids = [t["tag_id"] for t in result["tags"] if t["score"] > 0]

    tag_lab.apply_tag_lab_result(
        engine, file_id,
        [{"tag_id": tag_id, "score": 90} for tag_id in suggested_ids],
        provider_type=result["provider_type"], model_name=result["model_name"], run_id=result["run_id"],
    )

    stats = tag_lab_feedback.get_model_stats(engine, result["provider_type"], result["model_name"])
    assert stats["runs_total"] == 1
    assert stats["applied_count"] == 1
    assert stats["applied_unchanged_count"] == 1
    assert stats["applied_changed_count"] == 0


def test_apply_tag_lab_result_missing_file_raises(engine):
    with pytest.raises(tag_lab.TagLabError) as excinfo:
        tag_lab.apply_tag_lab_result(
            engine, str(uuid.uuid4()), [{"display_name": "Beach"}], provider_type="manual", model_name=None
        )
    assert excinfo.value.code == "file_not_found"
