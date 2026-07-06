"""Tagging tests (Specification §12): tag vocabulary CRUD, tagging/provider
settings singletons, the secrets store, provider prompt/response parsing,
frame/collage preparation (real ffmpeg via `conftest.make_video()`), and the
`tag` job handler with a stubbed provider (no real network calls here — real
provider verification is a manual/live step, not a unit test).
"""

from __future__ import annotations

import shutil

import pytest
from sqlalchemy import text

from app import provider_configs, secrets_store, tagging, tagging_settings
from app import tags as tags_service
from app.jobs import service
from app.jobs import tag as tag_job
from app.providers import registry
from app.providers.base import ProviderError, build_prompt, parse_scores
from app.scan import scan_source

from .conftest import make_video

ffmpeg_missing = shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None


# --- tag vocabulary CRUD -----------------------------------------------------


def test_normalize_tag_key_collapses_whitespace_and_case():
    assert tags_service.normalize_tag_key("  Birthday   Party ") == "birthday party"


def test_create_and_list_tags(engine):
    tags_service.create_tag(engine, {"display_name": "Beach"})
    tags_service.create_tag(engine, {"display_name": "Snow", "is_active": False})

    all_tags = tags_service.list_tags(engine)
    assert [t["display_name"] for t in all_tags] == ["Beach", "Snow"]

    active_only = tags_service.list_tags(engine, active_only=True)
    assert [t["display_name"] for t in active_only] == ["Beach"]


def test_create_tag_rejects_duplicate_key(engine):
    tags_service.create_tag(engine, {"display_name": "Beach"})
    with pytest.raises(tags_service.DuplicateTagError):
        tags_service.create_tag(engine, {"display_name": " beach "})


def test_list_tags_prefix_query_for_autocomplete(engine):
    tags_service.create_tag(engine, {"display_name": "Birthday"})
    tags_service.create_tag(engine, {"display_name": "Beach"})
    tags_service.create_tag(engine, {"display_name": "Snow"})

    matches = tags_service.list_tags(engine, query="bi")
    assert [t["display_name"] for t in matches] == ["Birthday"]

    matches = tags_service.list_tags(engine, query="b")
    assert {t["display_name"] for t in matches} == {"Birthday", "Beach"}


def test_update_tag_rename_and_deactivate(engine):
    tag = tags_service.create_tag(engine, {"display_name": "Beach"})
    updated = tags_service.update_tag(engine, tag["id"], {"display_name": "Beach Day", "is_active": False})
    assert updated["display_name"] == "Beach Day"
    assert updated["tag_key"] == "beach day"
    assert updated["is_active"] is False


def test_delete_tag_cascades_file_tags(engine, source):
    tag = tags_service.create_tag(engine, {"display_name": "Beach"})
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, created_at, updated_at) "
                "VALUES ('f1', :sid, 'd1', 'clip.mp4', 'clip.mp4', 'mp4', 1, '2024', '2024', 1, '2024', '2024')"
            ),
            {"sid": source["id"]},
        )
        conn.execute(
            text(
                "INSERT INTO file_tags (id, file_id, tag_id, score, assigned_at) "
                "VALUES ('ft1', 'f1', :tag_id, 80, '2024')"
            ),
            {"tag_id": tag["id"]},
        )

    assert tags_service.delete_tag(engine, tag["id"]) is True
    with engine.connect() as conn:
        remaining = conn.execute(text("SELECT COUNT(*) FROM file_tags")).scalar()
    assert remaining == 0


# --- tagging settings + provider configs + secrets --------------------------


def test_tagging_settings_singleton_roundtrip(engine):
    defaults = tagging_settings.get_settings(engine)
    assert defaults["sample_frame_count"] == 9
    assert defaults["combine_into_collage"] is True
    assert defaults["top_tag_count"] == 10

    updated = tagging_settings.update_settings(
        engine,
        {"sample_frame_count": 6, "combine_into_collage": False, "top_tag_count": 5, "default_provider": "openrouter"},
    )
    assert updated["sample_frame_count"] == 6
    assert updated["combine_into_collage"] is False
    assert updated["default_provider"] == "openrouter"


def test_provider_configs_seeded_and_updatable(engine):
    providers = provider_configs.list_providers(engine)
    assert {p["provider_name"] for p in providers} == set(provider_configs.PROVIDERS)
    assert all(p["enabled"] is False and p["has_api_key"] is False for p in providers)

    updated = provider_configs.update_provider(
        engine, "openrouter", {"enabled": True, "vision_model": "test-model", "api_key": "sk-test"}
    )
    assert updated["enabled"] is True
    assert updated["vision_model"] == "test-model"
    assert updated["has_api_key"] is True


def test_provider_configs_never_expose_api_key_value(engine):
    provider_configs.update_provider(engine, "gemini", {"enabled": True, "api_key": "secret-value"})
    config = provider_configs.get_provider(engine, "gemini")
    assert "api_key" not in config
    assert config["has_api_key"] is True


def test_provider_configs_rejects_unknown_provider(engine):
    with pytest.raises(provider_configs.UnknownProviderError):
        provider_configs.update_provider(engine, "not-a-provider", {"enabled": True})


def test_secrets_store_roundtrip():
    # `isolated_secrets_file` (conftest.py, autouse) already points
    # `secrets_store.SECRETS_PATH` at a per-test temp file.
    assert secrets_store.get_provider_api_key("openrouter") is None
    secrets_store.set_provider_api_key("openrouter", "sk-abc123")
    assert secrets_store.get_provider_api_key("openrouter") == "sk-abc123"
    assert secrets_store.has_provider_api_key("openrouter") is True
    assert secrets_store.has_provider_api_key("gemini") is False


# --- provider prompt/response parsing ---------------------------------------


def test_build_prompt_numbers_tags_in_order():
    prompt = build_prompt(["cat", "beach"])
    assert "0: cat" in prompt
    assert "1: beach" in prompt


def test_parse_scores_extracts_json_array_and_clamps():
    scores = parse_scores("Sure, here you go: [10, 250, -5]", expected_count=3)
    assert scores == [10, 100, 0]


def test_parse_scores_pads_short_arrays():
    assert parse_scores("[42]", expected_count=3) == [42, 0, 0]


def test_parse_scores_rejects_missing_array():
    with pytest.raises(ProviderError):
        parse_scores("no array here", expected_count=2)


# --- frame/collage preparation (real ffmpeg) --------------------------------


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_build_tagging_images_combine_returns_one_collage(tmp_path):
    video_path = tmp_path / "movie.mp4"
    make_video(video_path, duration=3.0, size="320x240")

    images = tagging.build_tagging_images(video_path, frame_count=9, combine_into_collage=True)
    assert len(images) == 1
    assert images[0][:2] == b"\xff\xd8"  # JPEG magic bytes


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_build_tagging_images_uncombined_returns_per_frame(tmp_path):
    video_path = tmp_path / "movie.mp4"
    make_video(video_path, duration=3.0, size="320x240")

    images = tagging.build_tagging_images(video_path, frame_count=4, combine_into_collage=False)
    assert len(images) == 4
    assert all(img[:2] == b"\xff\xd8" for img in images)


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_sample_frames_raises_for_non_video(tmp_path):
    bogus = tmp_path / "not-a-video.mp4"
    bogus.write_bytes(b"not a real video")
    with pytest.raises(tagging.TaggingInputError):
        tagging.sample_frames(bogus, frame_count=3)


# --- tag job -----------------------------------------------------------------


@pytest.fixture()
def stub_provider(monkeypatch):
    """Bypasses the real HTTP call: returns a fixed score per tag position so
    top-N ranking is deterministic and no network access happens in tests."""

    def fake_score(engine, provider_name, images, tags):
        assert provider_name == "openrouter"
        assert images
        return [max(0, 90 - 10 * i) for i in range(len(tags))]

    monkeypatch.setattr(registry, "score_tags_with_provider", fake_score)
    return fake_score


def _enable_openrouter(engine):
    provider_configs.update_provider(engine, "openrouter", {"enabled": True, "api_key": "sk-test"})
    tagging_settings.update_settings(engine, {"default_provider": "openrouter", "top_tag_count": 2})


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_tag_job_file_scope_assigns_top_n_tags(engine, source, stub_provider):
    _enable_openrouter(engine)
    for name in ("Beach", "Birthday", "Snow", "Dog"):
        tags_service.create_tag(engine, {"display_name": name})

    make_video(source["root"] / "clips" / "movie.mp4", duration=2.0, size="320x240")
    scan_source(engine, source["id"], source["root"])

    with engine.connect() as conn:
        file_row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'clips/movie.mp4'")).fetchone()

    job = service.create_job(
        engine, "tag", "file", file_row.id, {"file_id": file_row.id, "provider_name": "openrouter"}
    )
    service.start_job(engine, job["id"])
    status, message = tag_job.run_tag_job(engine, job)

    assert status == "completed"
    assert "2 tag(s)" in message

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tc.display_name, ft.score, ft.provider_name FROM file_tags ft "
                "JOIN tag_catalog tc ON tc.id = ft.tag_id WHERE ft.file_id = :fid ORDER BY ft.score DESC"
            ),
            {"fid": file_row.id},
        ).all()
        updated_file = conn.execute(text("SELECT tagged_at FROM files WHERE id = :id"), {"id": file_row.id}).fetchone()

    assert [row.display_name for row in rows] == ["Beach", "Birthday"]
    assert rows[0].provider_name == "openrouter"
    assert updated_file.tagged_at is not None


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_tag_job_retagging_replaces_previous_tags(engine, source, stub_provider):
    _enable_openrouter(engine)
    tags_service.create_tag(engine, {"display_name": "Beach"})
    tags_service.create_tag(engine, {"display_name": "Snow"})

    make_video(source["root"] / "clips" / "movie.mp4", duration=2.0, size="320x240")
    scan_source(engine, source["id"], source["root"])
    with engine.connect() as conn:
        file_row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'clips/movie.mp4'")).fetchone()

    job1 = service.create_job(engine, "tag", "file", file_row.id, {"file_id": file_row.id, "provider_name": "openrouter"})
    tag_job.run_tag_job(engine, job1)
    job2 = service.create_job(engine, "tag", "file", file_row.id, {"file_id": file_row.id, "provider_name": "openrouter"})
    tag_job.run_tag_job(engine, job2)

    with engine.connect() as conn:
        count = conn.execute(text("SELECT COUNT(*) FROM file_tags WHERE file_id = :fid"), {"fid": file_row.id}).scalar()
    assert count == 2  # not doubled


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_tag_job_directory_scope_skip_processed_and_test_artifacts(engine, source, stub_provider):
    _enable_openrouter(engine)
    tags_service.create_tag(engine, {"display_name": "Beach"})

    make_video(source["root"] / "clips" / "movie.mp4", duration=2.0, size="320x240")
    make_video(source["root"] / "clips" / "movie.original.mov", duration=2.0, size="320x240")
    scan_source(engine, source["id"], source["root"])

    job1 = service.create_job(engine, "tag", "source", None, {"path": "", "provider_name": "openrouter"})
    status1, message1 = tag_job.run_tag_job(engine, job1)
    assert status1 == "completed"
    assert "1 of 1" in message1  # test-artifact excluded from the total

    job2 = service.create_job(
        engine, "tag", "source", None, {"path": "", "skip_processed": True, "provider_name": "openrouter"}
    )
    status2, message2 = tag_job.run_tag_job(engine, job2)
    assert status2 == "completed"
    assert "1 skipped" in message2


def test_tag_job_fails_without_vocabulary(engine, source):
    _enable_openrouter(engine)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM tag_catalog"))

    job = service.create_job(engine, "tag", "source", None, {"path": "", "provider_name": "openrouter"})
    with pytest.raises(RuntimeError, match="vocabulary"):
        tag_job.run_tag_job(engine, job)
