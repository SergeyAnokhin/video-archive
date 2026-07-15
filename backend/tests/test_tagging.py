"""Tagging tests (Specification §12): tag vocabulary CRUD, tagging/provider
settings singletons, the secrets store, provider prompt/response parsing,
frame/collage preparation (real ffmpeg via `conftest.make_video()`), and the
`tag` job handler with a stubbed provider (no real network calls here — real
provider verification is a manual/live step, not a unit test).
"""

from __future__ import annotations

import shutil
import uuid

import cv2
import numpy as np
import pytest
from sqlalchemy import text

from app import provider_entries, secrets_store, tagging, tagging_settings
from app import tags as tags_service
from app.jobs import service
from app.jobs import tag as tag_job
from app.providers import registry
from app.providers.base import ProviderError, build_prompt, parse_scores
from app.scan import scan_source

from .conftest import make_image, make_video

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


def test_assign_tuning_parameter_tags_excluded_from_vocabulary(engine, source):
    """User request (surfaced by Tag Lab): a swept encode parameter like
    "640px" must not appear in the tag vocabulary -- not in Settings'
    listing, not in the prompt sent to a vision provider."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, created_at, updated_at) "
                "VALUES ('f1', :sid, 'd1', 'clip.mp4', 'clip.mp4', 'mp4', 1, '2024', '2024', 1, '2024', '2024')"
            ),
            {"sid": source["id"]},
        )
    tags_service.create_tag(engine, {"display_name": "Beach"})
    tags_service.assign_tuning_parameter_tags(engine, "f1", ["640px", "H265"])

    assert [t["display_name"] for t in tags_service.list_tags(engine)] == ["Beach"]

    # But the parameter tags are still real, queryable file_tags rows.
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tc.display_name FROM file_tags ft JOIN tag_catalog tc ON tc.id = ft.tag_id "
                "WHERE ft.file_id = 'f1' ORDER BY tc.display_name"
            )
        ).all()
    assert [row.display_name for row in rows] == ["640px", "H265"]


def test_list_tags_category_user_returns_only_user_defined_pool(engine):
    tags_service.create_tag(engine, {"display_name": "Favorite", "is_ai_vocabulary": False, "is_user_defined": True})
    tags_service.create_tag(engine, {"display_name": "Beach"})  # AI vocabulary, default

    assert [t["display_name"] for t in tags_service.list_tags(engine, category="user")] == ["Favorite"]
    assert [t["display_name"] for t in tags_service.list_tags(engine)] == ["Beach"]


def test_assign_user_defined_tag_by_existing_id(engine, source):
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, created_at, updated_at) "
                "VALUES ('f1', :sid, 'd1', 'clip.mp4', 'clip.mp4', 'mp4', 1, '2024', '2024', 1, '2024', '2024')"
            ),
            {"sid": source["id"]},
        )
    favorite = tags_service.create_tag(
        engine, {"display_name": "Favorite", "is_ai_vocabulary": False, "is_user_defined": True}
    )

    result = tags_service.assign_user_defined_tag(engine, "f1", tag_id=favorite["id"])
    assert result["id"] == favorite["id"]

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT tc.display_name, ft.provider_name, ft.score FROM file_tags ft "
                 "JOIN tag_catalog tc ON tc.id = ft.tag_id WHERE ft.file_id = 'f1'")
        ).all()
    assert [(r.display_name, r.provider_name, r.score) for r in rows] == [("Favorite", "manual", 100)]


def test_assign_user_defined_tag_unknown_id_returns_none(engine, source):
    assert tags_service.assign_user_defined_tag(engine, "f1", tag_id=str(uuid.uuid4())) is None


def test_assign_user_defined_tag_creates_new_tag_in_user_defined_pool(engine, source):
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, created_at, updated_at) "
                "VALUES ('f1', :sid, 'd1', 'clip.mp4', 'clip.mp4', 'mp4', 1, '2024', '2024', 1, '2024', '2024')"
            ),
            {"sid": source["id"]},
        )
    result = tags_service.assign_user_defined_tag(engine, "f1", display_name="Rewatch")
    assert result["is_user_defined"] is True
    assert result["is_ai_vocabulary"] is False
    assert [t["display_name"] for t in tags_service.list_tags(engine, category="user")] == ["Rewatch"]


def test_list_used_tags_covers_every_pool(engine, source):
    """User request: typing-suggestion listings must cover the AI
    vocabulary, user-defined, and plain ad-hoc pools alike -- unlike
    `list_tags()`, which is always scoped to one managed pool."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, created_at, updated_at) "
                "VALUES ('f1', :sid, 'd1', 'clip.mp4', 'clip.mp4', 'mp4', 1, '2024', '2024', 1, '2024', '2024')"
            ),
            {"sid": source["id"]},
        )
    tags_service.assign_tuning_parameter_tags(engine, "f1", ["640px"])  # neither pool
    tags_service.assign_user_defined_tag(engine, "f1", display_name="Rewatch")  # user-defined pool
    ai_tag = tags_service.create_tag(engine, {"display_name": "Beach"})  # AI vocabulary pool
    tags_service.assign_file_tag(engine, "f1", ai_tag["id"])

    used = {t["display_name"] for t in tags_service.list_used_tags(engine)}
    assert used == {"640px", "Rewatch", "Beach"}


def test_get_or_create_tag_bare_call_joins_no_managed_pool(engine, source):
    """Typing a tag directly onto a file (the bare default, no explicit
    pool flag) must not silently join the AI vocabulary or the user-defined
    pool -- those are only ever populated through their own dedicated
    Settings/picker flows (user request)."""
    tag = tags_service.get_or_create_tag(engine, "Beach")
    assert tag["is_ai_vocabulary"] is False
    assert tag["is_user_defined"] is False
    assert tags_service.list_tags(engine) == []
    assert tags_service.list_tags(engine, category="user") == []


def test_get_or_create_tag_promotes_existing_tuning_tag_to_vocabulary(engine, source):
    """An explicit `is_ai_vocabulary=True` caller (Settings' own vocabulary
    "add" flow) must end up with a real, visible vocabulary entry -- even if
    that exact name was first auto-created as a tuning-parameter side
    effect."""
    tags_service.get_or_create_tag(engine, "640px")
    assert tags_service.list_tags(engine) == []

    promoted = tags_service.get_or_create_tag(engine, "640px", is_ai_vocabulary=True)
    assert promoted["is_ai_vocabulary"] is True
    assert [t["display_name"] for t in tags_service.list_tags(engine)] == ["640px"]


def test_get_or_create_tag_promotes_existing_ad_hoc_tag_to_user_defined(engine, source):
    """Mirrors the AI-vocabulary promotion above, for the user-defined pool:
    typing an existing ad-hoc tag's name into the user-defined picker's
    "create new" field promotes it rather than creating a duplicate."""
    tags_service.get_or_create_tag(engine, "Beach")
    assert tags_service.list_tags(engine, category="user") == []

    promoted = tags_service.get_or_create_tag(engine, "Beach", is_user_defined=True)
    assert promoted["is_user_defined"] is True
    assert [t["display_name"] for t in tags_service.list_tags(engine, category="user")] == ["Beach"]


def test_migration_26_backfill_only_demotes_tuning_only_tags(engine, source):
    """Exercises the migration 26 backfill statement (`app.db.MIGRATIONS[26]`)
    directly against pre-existing data, the way an upgraded database would
    see it: a tag used *only* via a tuning sweep is demoted, but a tag also
    used for anything else (AI-scored, manual, or both) is left alone."""
    import app.db as db_module

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, created_at, updated_at) "
                "VALUES ('f1', :sid, 'd1', 'clip.mp4', 'clip.mp4', 'mp4', 1, '2024', '2024', 1, '2024', '2024')"
            ),
            {"sid": source["id"]},
        )

    tuning_only = tags_service.create_tag(engine, {"display_name": "640px"})
    mixed = tags_service.create_tag(engine, {"display_name": "H265"})
    untouched = tags_service.create_tag(engine, {"display_name": "Beach"})

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO file_tags (id, file_id, tag_id, score, provider_name, assigned_at) "
                "VALUES ('ft1', 'f1', :tag_id, 100, 'tuning', '2024')"
            ),
            {"tag_id": tuning_only["id"]},
        )
        conn.execute(
            text(
                "INSERT INTO file_tags (id, file_id, tag_id, score, provider_name, assigned_at) "
                "VALUES ('ft2', 'f1', :tag_id, 100, 'tuning', '2024')"
            ),
            {"tag_id": mixed["id"]},
        )
        conn.execute(
            text(
                "INSERT INTO file_tags (id, file_id, tag_id, score, provider_name, assigned_at) "
                "VALUES ('ft3', 'f1', :tag_id, 80, 'openrouter', '2024')"
            ),
            {"tag_id": mixed["id"]},
        )
        # Simulate a pre-migration-26 database: every tag starts as vocabulary.
        conn.execute(text("UPDATE tag_catalog SET is_ai_vocabulary = 1"))
        for statement in db_module.MIGRATIONS[26][1:]:
            conn.execute(text(statement))

    with engine.connect() as conn:
        rows = {
            row.id: bool(row.is_ai_vocabulary)
            for row in conn.execute(text("SELECT id, is_ai_vocabulary FROM tag_catalog"))
        }
    assert rows[tuning_only["id"]] is False
    assert rows[mixed["id"]] is True
    assert rows[untouched["id"]] is True


def _insert_file_and_tags(engine, source, file_id: str, tag_scores: list[tuple[str, int]]) -> None:
    """`tag_scores` is `[(tag_id, score), ...]`; creates one `files` row and
    one `file_tags` row per pair."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, created_at, updated_at) "
                "VALUES (:id, :sid, 'd1', :id, :id, 'mp4', 1, '2024', '2024', 1, '2024', '2024')"
            ),
            {"id": file_id, "sid": source["id"]},
        )
        for i, (tag_id, score) in enumerate(tag_scores):
            conn.execute(
                text(
                    "INSERT INTO file_tags (id, file_id, tag_id, score, assigned_at) "
                    "VALUES (:ft_id, :file_id, :tag_id, :score, '2024')"
                ),
                {"ft_id": f"{file_id}-ft-{i}", "file_id": file_id, "tag_id": tag_id, "score": score},
            )


def test_list_top_tags_for_files_orders_by_score_and_caps_per_file(engine, source):
    """Bug fix (user request) -- the library grid/info panel weren't
    rendering any AI-assigned tags at all despite them being fully computed
    and stored; `list_top_tags_for_files()` is what makes them visible."""
    beach = tags_service.create_tag(engine, {"display_name": "Beach"})
    snow = tags_service.create_tag(engine, {"display_name": "Snow"})
    dog = tags_service.create_tag(engine, {"display_name": "Dog"})
    cat = tags_service.create_tag(engine, {"display_name": "Cat"})

    _insert_file_and_tags(
        engine, source, "f1",
        [(beach["id"], 40), (snow["id"], 90), (dog["id"], 60), (cat["id"], 10)],
    )

    result = tags_service.list_top_tags_for_files(engine, ["f1"], limit_per_file=2)

    assert [tag["display_name"] for tag in result["f1"]] == ["Snow", "Dog"]
    assert result["f1"][0]["score"] == 90


def test_list_top_tags_for_files_excludes_zero_score_tags(engine, source):
    """A 0% score means the model doesn't consider the tag applicable at all
    (user request), so it shouldn't be surfaced even if it was persisted by
    an older tag run predating the `_tag_one_file()` filter."""
    beach = tags_service.create_tag(engine, {"display_name": "Beach"})
    snow = tags_service.create_tag(engine, {"display_name": "Snow"})

    _insert_file_and_tags(engine, source, "f1", [(beach["id"], 80), (snow["id"], 0)])

    result = tags_service.list_top_tags_for_files(engine, ["f1"])

    assert [tag["display_name"] for tag in result["f1"]] == ["Beach"]


def test_list_top_tags_for_files_groups_by_file_and_skips_untagged(engine, source):
    beach = tags_service.create_tag(engine, {"display_name": "Beach"})
    _insert_file_and_tags(engine, source, "f1", [(beach["id"], 70)])
    _insert_file_and_tags(engine, source, "f2", [])  # no tags assigned yet

    result = tags_service.list_top_tags_for_files(engine, ["f1", "f2"])

    assert [tag["display_name"] for tag in result["f1"]] == ["Beach"]
    assert "f2" not in result  # untagged files simply have no entry, not an empty list error


def test_list_top_tags_for_files_empty_input_returns_empty_dict(engine):
    assert tags_service.list_top_tags_for_files(engine, []) == {}


def test_list_used_tags_only_includes_assigned_tags(engine, source):
    """Unlike `list_tags()`, `list_used_tags()` must exclude vocabulary
    entries configured for AI tagging but never actually assigned to a file
    (user request: playback screen's quick-add should suggest from what's
    really in this archive, not the full settings vocabulary)."""
    beach = tags_service.create_tag(engine, {"display_name": "Beach"})
    tags_service.create_tag(engine, {"display_name": "Birthday"})  # never assigned

    _insert_file_and_tags(engine, source, "f1", [(beach["id"], 80)])

    used = tags_service.list_used_tags(engine)
    assert [t["display_name"] for t in used] == ["Beach"]


def test_list_used_tags_prefix_filters_and_orders_by_usage(engine, source):
    beach = tags_service.create_tag(engine, {"display_name": "Beach"})
    birthday = tags_service.create_tag(engine, {"display_name": "Birthday"})
    bike = tags_service.create_tag(engine, {"display_name": "Bike"})

    _insert_file_and_tags(engine, source, "f1", [(beach["id"], 80), (birthday["id"], 50)])
    _insert_file_and_tags(engine, source, "f2", [(beach["id"], 60), (bike["id"], 40)])

    used = tags_service.list_used_tags(engine, query="b")
    assert [t["display_name"] for t in used] == ["Beach", "Bike", "Birthday"]

    used_snow = tags_service.list_used_tags(engine, query="sn")
    assert used_snow == []


def test_list_used_tags_respects_limit(engine, source):
    beach = tags_service.create_tag(engine, {"display_name": "Beach"})
    birthday = tags_service.create_tag(engine, {"display_name": "Birthday"})
    _insert_file_and_tags(engine, source, "f1", [(beach["id"], 80), (birthday["id"], 50)])

    used = tags_service.list_used_tags(engine, limit=1)
    assert len(used) == 1


def test_list_tags_by_ids_preserves_order_and_length(engine):
    """Batch-tagging resume (`app/jobs/tag_batch.py::resume_directory_scope`)
    relies on this to realign a batch's positional scores against the exact
    tag order the request was built with, even if the live vocabulary
    changed while the batch was in flight -- order and length must survive
    a tag having been deleted in the meantime (see the next test)."""
    beach = tags_service.create_tag(engine, {"display_name": "Beach"})
    snow = tags_service.create_tag(engine, {"display_name": "Snow"})

    result = tags_service.list_tags_by_ids(engine, [snow["id"], beach["id"]])

    assert [tag["display_name"] for tag in result] == ["Snow", "Beach"]


def test_list_tags_by_ids_returns_none_for_deleted_tag_without_shifting_positions(engine):
    beach = tags_service.create_tag(engine, {"display_name": "Beach"})
    snow = tags_service.create_tag(engine, {"display_name": "Snow"})
    tags_service.delete_tag(engine, snow["id"])

    result = tags_service.list_tags_by_ids(engine, [beach["id"], snow["id"]])

    assert len(result) == 2
    assert result[0]["display_name"] == "Beach"
    assert result[1] is None


def test_list_tags_by_ids_empty_input_returns_empty_list(engine):
    assert tags_service.list_tags_by_ids(engine, []) == []


# --- tagging settings + secrets ----------------------------------------------
# Provider entry CRUD lives in `test_provider_entries.py`.


def test_tagging_settings_singleton_roundtrip(engine):
    defaults = tagging_settings.get_settings(engine)
    assert defaults["sample_frame_count"] == 9
    assert defaults["combine_into_collage"] is True
    assert defaults["top_tag_count"] == 10
    assert defaults["image_resolution"] == 360
    assert defaults["request_timeout_seconds"] == 30

    updated = tagging_settings.update_settings(
        engine,
        {
            "sample_frame_count": 6,
            "combine_into_collage": False,
            "top_tag_count": 5,
            "image_resolution": 720,
            "request_timeout_seconds": 45,
        },
    )
    assert updated["sample_frame_count"] == 6
    assert updated["combine_into_collage"] is False
    assert updated["top_tag_count"] == 5
    assert updated["image_resolution"] == 720
    assert updated["request_timeout_seconds"] == 45


def test_secrets_store_roundtrip():
    # `isolated_secrets_file` (conftest.py, autouse) already points
    # `secrets_store.SECRETS_PATH` at a per-test temp file.
    assert secrets_store.get_entry_api_key("entry-1") is None
    secrets_store.set_entry_api_key("entry-1", "sk-abc123")
    assert secrets_store.get_entry_api_key("entry-1") == "sk-abc123"
    assert secrets_store.has_entry_api_key("entry-1") is True
    assert secrets_store.has_entry_api_key("entry-2") is False
    assert secrets_store.get_entry_api_key_suffix("entry-1") == "c123"
    secrets_store.delete_entry_api_key("entry-1")
    assert secrets_store.has_entry_api_key("entry-1") is False


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
def test_build_tagging_images_respects_image_resolution(tmp_path):
    video_path = tmp_path / "movie.mp4"
    make_video(video_path, duration=3.0, size="320x240")

    collage = tagging.build_tagging_images(
        video_path, frame_count=4, combine_into_collage=True, image_resolution=128
    )
    collage_arr = cv2.imdecode(np.frombuffer(collage[0], np.uint8), cv2.IMREAD_COLOR)
    # Source is 320x240 (4:3): each cell's longest side is capped at 128px
    # while preserving aspect ratio, so cells are 128x96, not square.
    cell_height, cell_width = 96, 128
    assert collage_arr.shape[0] % cell_height == 0 and collage_arr.shape[1] % cell_width == 0

    frames = tagging.build_tagging_images(
        video_path, frame_count=4, combine_into_collage=False, image_resolution=128
    )
    for frame in frames:
        frame_arr = cv2.imdecode(np.frombuffer(frame, np.uint8), cv2.IMREAD_COLOR)
        assert max(frame_arr.shape[:2]) == 128


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_sample_frames_raises_for_non_video(tmp_path):
    bogus = tmp_path / "not-a-video.mp4"
    bogus.write_bytes(b"not a real video")
    with pytest.raises(tagging.TaggingInputError):
        tagging.sample_frames(bogus, frame_count=3)


# --- standalone image tagging (no ffmpeg needed) ----------------------------


def test_load_image_raises_for_undecodable_file(tmp_path):
    bogus = tmp_path / "not-an-image.jpg"
    bogus.write_bytes(b"not a real image")
    with pytest.raises(tagging.TaggingInputError):
        tagging.load_image(bogus)


def test_build_tagging_images_for_file_image_path_returns_one_jpeg(tmp_path):
    image_path = tmp_path / "photo.jpg"
    make_image(image_path, size=(320, 240))

    images = tagging.build_tagging_images_for_file(
        image_path, is_video=False, frame_count=9, combine_into_collage=True, image_resolution=128
    )
    assert len(images) == 1
    assert images[0][:2] == b"\xff\xd8"  # JPEG magic bytes
    decoded = cv2.imdecode(np.frombuffer(images[0], np.uint8), cv2.IMREAD_COLOR)
    assert max(decoded.shape[:2]) == 128


def test_build_tagging_images_for_file_video_path_delegates_unchanged(tmp_path):
    """The dispatcher's video branch must behave exactly like calling
    `build_tagging_images()` directly -- no behavior change for videos."""
    if ffmpeg_missing:
        pytest.skip("ffmpeg/ffprobe not on PATH")
    video_path = tmp_path / "movie.mp4"
    make_video(video_path, duration=2.0, size="320x240")

    images = tagging.build_tagging_images_for_file(
        video_path, is_video=True, frame_count=4, combine_into_collage=False, image_resolution=128
    )
    assert len(images) == 4
    assert all(img[:2] == b"\xff\xd8" for img in images)


# --- tag job -----------------------------------------------------------------


@pytest.fixture()
def stub_provider(monkeypatch):
    """Bypasses the real HTTP call: returns a fixed score per tag position so
    top-N ranking is deterministic and no network access happens in tests."""

    def fake_fallback(engine, entries, images, tags, dead_entry_ids, **_kwargs):
        assert entries and entries[0]["provider_type"] == "openrouter"
        assert images
        scores = [max(0, 90 - 10 * i) for i in range(len(tags))]
        return scores, entries[0]

    monkeypatch.setattr(registry, "score_tags_with_fallback", fake_fallback)
    return fake_fallback


def _enable_openrouter(engine):
    provider_entries.create_entry(
        engine, {"provider_type": "openrouter", "display_name": "openrouter", "enabled": True, "api_key": "sk-test"}
    )
    tagging_settings.update_settings(engine, {"top_tag_count": 2})


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_tag_job_file_scope_assigns_top_n_tags(engine, source, stub_provider):
    _enable_openrouter(engine)
    for name in ("Beach", "Birthday", "Snow", "Dog"):
        tags_service.create_tag(engine, {"display_name": name})

    make_video(source["root"] / "clips" / "movie.mp4", duration=2.0, size="320x240")
    scan_source(engine, source["id"], source["root"])

    with engine.connect() as conn:
        file_row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'clips/movie.mp4'")).fetchone()

    job = service.create_job(engine, "tag", "file", file_row.id, {"file_id": file_row.id})
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
def test_tag_job_logs_provider_and_model_used(engine, source, monkeypatch):
    """User request -- job log entries for tag scoring should name the
    provider/model that produced them, not just the scores, so the log makes
    clear where a tagging request actually went."""
    entry = provider_entries.create_entry(
        engine,
        {
            "provider_type": "openrouter",
            "display_name": "openrouter",
            "enabled": True,
            "api_key": "sk-test",
            "vision_model": "test-vision-model",
        },
    )
    tags_service.create_tag(engine, {"display_name": "Beach"})

    def fake_fallback(engine, entries, images, tags, dead_entry_ids, **_kwargs):
        return [90], entries[0]

    monkeypatch.setattr(registry, "score_tags_with_fallback", fake_fallback)

    make_video(source["root"] / "clips" / "movie.mp4", duration=2.0, size="320x240")
    scan_source(engine, source["id"], source["root"])

    with engine.connect() as conn:
        file_row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'clips/movie.mp4'")).fetchone()

    job = service.create_job(engine, "tag", "file", file_row.id, {"file_id": file_row.id})
    service.start_job(engine, job["id"])
    status, _message = tag_job.run_tag_job(engine, job)
    assert status == "completed"

    with engine.connect() as conn:
        events = conn.execute(
            text("SELECT message FROM app_events WHERE job_id = :jid AND event_type = 'job_item_tags'"),
            {"jid": job["id"]},
        ).all()

    assert len(events) == 1
    assert f"via {entry['provider_type']}/{entry['vision_model']}" in events[0].message


@pytest.fixture()
def stub_provider_with_zero_scores(monkeypatch):
    """Only the first tag gets a non-zero score -- the rest are scored 0,
    meaning the model doesn't consider them applicable at all (user request:
    a tag with a 0% match shouldn't be assigned, even if `top_tag_count`
    hasn't been reached yet)."""

    def fake_fallback(engine, entries, images, tags, dead_entry_ids, **_kwargs):
        scores = [90] + [0] * (len(tags) - 1)
        return scores, entries[0]

    monkeypatch.setattr(registry, "score_tags_with_fallback", fake_fallback)
    return fake_fallback


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_tag_job_excludes_zero_score_tags(engine, source, stub_provider_with_zero_scores):
    _enable_openrouter(engine)  # top_tag_count = 2
    for name in ("Beach", "Birthday", "Snow", "Dog"):
        tags_service.create_tag(engine, {"display_name": name})

    make_video(source["root"] / "clips" / "movie.mp4", duration=2.0, size="320x240")
    scan_source(engine, source["id"], source["root"])

    with engine.connect() as conn:
        file_row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'clips/movie.mp4'")).fetchone()

    job = service.create_job(engine, "tag", "file", file_row.id, {"file_id": file_row.id})
    service.start_job(engine, job["id"])
    status, message = tag_job.run_tag_job(engine, job)

    assert status == "completed"
    assert "1 tag(s)" in message

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tc.display_name FROM file_tags ft JOIN tag_catalog tc ON tc.id = ft.tag_id "
                "WHERE ft.file_id = :fid"
            ),
            {"fid": file_row.id},
        ).all()
    assert [row.display_name for row in rows] == ["Beach"]


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_tag_job_retagging_replaces_previous_tags(engine, source, stub_provider):
    _enable_openrouter(engine)
    tags_service.create_tag(engine, {"display_name": "Beach"})
    tags_service.create_tag(engine, {"display_name": "Snow"})

    make_video(source["root"] / "clips" / "movie.mp4", duration=2.0, size="320x240")
    scan_source(engine, source["id"], source["root"])
    with engine.connect() as conn:
        file_row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'clips/movie.mp4'")).fetchone()

    job1 = service.create_job(engine, "tag", "file", file_row.id, {"file_id": file_row.id})
    tag_job.run_tag_job(engine, job1)
    job2 = service.create_job(engine, "tag", "file", file_row.id, {"file_id": file_row.id})
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

    job1 = service.create_job(engine, "tag", "source", None, {"path": ""})
    status1, message1 = tag_job.run_tag_job(engine, job1)
    assert status1 == "completed"
    assert "1 of 1" in message1  # test-artifact excluded from the total

    job2 = service.create_job(engine, "tag", "source", None, {"path": "", "skip_processed": True})
    status2, message2 = tag_job.run_tag_job(engine, job2)
    assert status2 == "completed"
    assert "1 skipped" in message2


def test_tag_job_file_scope_tags_standalone_image(engine, source, stub_provider):
    """Standalone images get AI auto-tagging too (post-V1, user request):
    the image itself is sent to the provider, not sampled frames -- no
    ffmpeg needed for this path at all."""
    _enable_openrouter(engine)
    for name in ("Beach", "Birthday", "Snow", "Dog"):
        tags_service.create_tag(engine, {"display_name": name})

    make_image(source["root"] / "photos" / "pic.jpg", size=(320, 240))
    scan_source(engine, source["id"], source["root"])

    with engine.connect() as conn:
        file_row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'photos/pic.jpg'")).fetchone()
    assert file_row.is_image_supported == 1
    assert file_row.is_video_supported == 0

    job = service.create_job(engine, "tag", "file", file_row.id, {"file_id": file_row.id})
    service.start_job(engine, job["id"])
    status, message = tag_job.run_tag_job(engine, job)

    assert status == "completed"
    assert "2 tag(s)" in message

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tc.display_name FROM file_tags ft JOIN tag_catalog tc ON tc.id = ft.tag_id "
                "WHERE ft.file_id = :fid ORDER BY ft.score DESC"
            ),
            {"fid": file_row.id},
        ).all()
    assert [row.display_name for row in rows] == ["Beach", "Birthday"]


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_tag_job_directory_scope_tags_video_and_image_together(engine, source, stub_provider):
    _enable_openrouter(engine)
    tags_service.create_tag(engine, {"display_name": "Beach"})

    make_video(source["root"] / "clip.mp4", duration=2.0, size="320x240")
    make_image(source["root"] / "pic.jpg", size=(320, 240))
    scan_source(engine, source["id"], source["root"])

    job = service.create_job(engine, "tag", "source", None, {"path": ""})
    status, message = tag_job.run_tag_job(engine, job)

    assert status == "completed"
    assert "2 of 2" in message

    with engine.connect() as conn:
        tagged_count = conn.execute(
            text("SELECT COUNT(*) FROM files WHERE tagged_at IS NOT NULL")
        ).scalar()
    assert tagged_count == 2


def test_tag_job_fails_without_vocabulary(engine, source):
    _enable_openrouter(engine)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM tag_catalog"))

    job = service.create_job(engine, "tag", "source", None, {"path": ""})
    with pytest.raises(RuntimeError, match="vocabulary"):
        tag_job.run_tag_job(engine, job)
