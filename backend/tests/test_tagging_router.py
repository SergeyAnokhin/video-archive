"""HTTP-layer tests for the tag vocabulary CRUD + autocomplete, tag-filtered
file listing, per-file tag listing, tagging/provider settings, and the
`tag-directory`/`tag-file` job-trigger validation (missing provider, empty
vocabulary, 404s). Does not exercise a real tagging job run (that's
`test_tagging.py`'s job, with a stubbed provider) or a real provider network
call (manual/live verification only).
"""

from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

import app.db as db_module
from app.main import app
from app.providers import registry
from app.tags import resolve_tag_color

from .conftest import make_video

ffmpeg_missing = shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None


def _insert_source_and_folder(engine, root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "clip_0.mp4").write_bytes(b"0")

    source_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sources (id, name, protocol, root_path, is_active, created_at, updated_at) "
                "VALUES (:id, 'Test', 'local', :root, 1, :now, :now)"
            ),
            {"id": source_id, "root": str(root), "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO directories (id, source_id, relative_path, name, parent_relative_path, "
                "has_folder_preview, last_scanned_at, created_at, updated_at) "
                "VALUES (:id, :sid, '', 'Test', NULL, 0, :now, :now, :now)"
            ),
            {"id": str(uuid.uuid4()), "sid": source_id, "now": now},
        )
        file_id = str(uuid.uuid4())
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, created_at, updated_at) "
                "SELECT :fid, :sid, d.id, 'clip_0.mp4', 'clip_0.mp4', 'mp4', 1, :now, :now, 1, :now, :now "
                "FROM directories d WHERE d.source_id = :sid AND d.relative_path = ''"
            ),
            {"fid": file_id, "sid": source_id, "now": now},
        )
    return source_id, file_id


def _fresh_client(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)
    return TestClient(app)


def test_tag_crud_and_prefix_autocomplete_over_http(tmp_path, monkeypatch):
    with _fresh_client(tmp_path, monkeypatch) as client:
        r = client.post("/api/tags", json={"display_name": "Birthday"})
        assert r.status_code == 200
        tag_id = r.json()["id"]

        client.post("/api/tags", json={"display_name": "Beach"})

        r = client.get("/api/tags", params={"query": "bi"})
        assert [t["display_name"] for t in r.json()["tags"]] == ["Birthday"]

        r = client.put(f"/api/tags/{tag_id}", json={"display_name": "Birthday Party", "is_active": False})
        assert r.status_code == 200
        assert r.json()["display_name"] == "Birthday Party"

        r = client.post("/api/tags", json={"display_name": "birthday party"})
        assert r.status_code == 409

        r = client.delete(f"/api/tags/{tag_id}")
        assert r.status_code == 200
        r = client.delete(f"/api/tags/{tag_id}")
        assert r.status_code == 404


def test_tag_color_round_trip_and_fallback_over_http(tmp_path, monkeypatch):
    with _fresh_client(tmp_path, monkeypatch) as client:
        tag_id = client.post("/api/tags", json={"display_name": "Sunset"}).json()["id"]

        # No color ever picked: a stable, deterministic fallback is returned
        # every time, not null/empty.
        fallback = resolve_tag_color(tag_id, None)
        r = client.get("/api/tags", params={"query": "sunset"})
        assert r.json()["tags"][0]["color"] == fallback
        r = client.get("/api/tags", params={"query": "sunset"})
        assert r.json()["tags"][0]["color"] == fallback

        # Explicitly picking a color persists it and it round-trips exactly.
        r = client.put(
            f"/api/tags/{tag_id}",
            json={"display_name": "Sunset", "color": "#123456"},
        )
        assert r.status_code == 200
        assert r.json()["color"] == "#123456"
        r = client.get("/api/tags", params={"query": "sunset"})
        assert r.json()["tags"][0]["color"] == "#123456"


def test_get_file_tags_and_tag_filtered_listing_over_http(tmp_path, monkeypatch):
    with _fresh_client(tmp_path, monkeypatch) as client:
        engine = db_module.get_engine()
        _source_id, file_id = _insert_source_and_folder(engine, tmp_path / "source")

        r = client.get(f"/api/files/{file_id}/tags")
        assert r.status_code == 200
        assert r.json()["tags"] == []

        tag_id = client.post("/api/tags", json={"display_name": "Beach"}).json()["id"]
        now = datetime.now(timezone.utc).isoformat()
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO file_tags (id, file_id, tag_id, score, provider_name, assigned_at) "
                    "VALUES (:id, :fid, :tid, 87, 'openrouter', :now)"
                ),
                {"id": str(uuid.uuid4()), "fid": file_id, "tid": tag_id, "now": now},
            )

        r = client.get(f"/api/files/{file_id}/tags")
        assert r.status_code == 200
        assert r.json()["tags"] == [
            {
                "tag_id": tag_id,
                "display_name": "Beach",
                "color": resolve_tag_color(tag_id, None),
                "score": 87,
                "provider_name": "openrouter",
                "model_name": None,
                "assigned_at": now,
            }
        ]

        r = client.get("/api/files", params={"tags": "beach"})
        assert [f["id"] for f in r.json()["files"]] == [file_id]

        r = client.get("/api/files", params={"tags": "snow"})
        assert r.json()["files"] == []

        r = client.get(f"/api/files/{uuid.uuid4()}/tags")
        assert r.status_code == 404


def test_manual_tag_assign_and_remove_over_http(tmp_path, monkeypatch):
    with _fresh_client(tmp_path, monkeypatch) as client:
        engine = db_module.get_engine()
        _source_id, file_id = _insert_source_and_folder(engine, tmp_path / "source")

        # Assign an existing vocabulary entry by id -- full confidence,
        # provider "manual" rather than an AI model.
        tag_id = client.post("/api/tags", json={"display_name": "Beach"}).json()["id"]
        r = client.post(f"/api/files/{file_id}/tags", json={"tag_id": tag_id})
        assert r.status_code == 200
        r = client.get(f"/api/files/{file_id}/tags")
        assert r.json()["tags"] == [
            {
                "tag_id": tag_id,
                "display_name": "Beach",
                "color": resolve_tag_color(tag_id, None),
                "score": 100,
                "provider_name": "manual",
                "model_name": None,
                "assigned_at": r.json()["tags"][0]["assigned_at"],
            }
        ]

        # Typing a name that already exists (case/whitespace-insensitive)
        # reuses the existing tag rather than duplicating the assignment.
        r = client.post(f"/api/files/{file_id}/tags", json={"display_name": "  beach  "})
        assert r.status_code == 200
        assert len(client.get(f"/api/files/{file_id}/tags").json()["tags"]) == 1

        # Typing a brand-new name creates an ad-hoc tag and assigns it -- it
        # must NOT silently join the AI vocabulary (user request: only
        # Settings' own "add" flow populates that list).
        r = client.post(f"/api/files/{file_id}/tags", json={"display_name": "Sunset"})
        assert r.status_code == 200
        names = {t["display_name"] for t in client.get(f"/api/files/{file_id}/tags").json()["tags"]}
        assert names == {"Beach", "Sunset"}
        assert {t["display_name"] for t in client.get("/api/tags").json()["tags"]} == {"Beach"}

        # Neither tag_id nor display_name -> 422.
        r = client.post(f"/api/files/{file_id}/tags", json={})
        assert r.status_code == 422

        # Unknown file -> 404.
        r = client.post(f"/api/files/{uuid.uuid4()}/tags", json={"tag_id": tag_id})
        assert r.status_code == 404

        # Remove one assignment; the other stays.
        r = client.delete(f"/api/files/{file_id}/tags/{tag_id}")
        assert r.status_code == 200
        names = {t["display_name"] for t in client.get(f"/api/files/{file_id}/tags").json()["tags"]}
        assert names == {"Sunset"}

        # Removing an assignment that no longer exists -> 404.
        r = client.delete(f"/api/files/{file_id}/tags/{tag_id}")
        assert r.status_code == 404


def test_tags_category_query_param_scopes_to_one_pool(tmp_path, monkeypatch):
    with _fresh_client(tmp_path, monkeypatch) as client:
        client.post("/api/tags", json={"display_name": "Beach"})  # AI vocabulary (default)
        client.post(
            "/api/tags",
            json={"display_name": "Favorite", "is_ai_vocabulary": False, "is_user_defined": True},
        )

        assert {t["display_name"] for t in client.get("/api/tags").json()["tags"]} == {"Beach"}
        assert {t["display_name"] for t in client.get("/api/tags", params={"category": "user"}).json()["tags"]} == {
            "Favorite"
        }


def test_user_defined_tag_endpoint_over_http(tmp_path, monkeypatch):
    with _fresh_client(tmp_path, monkeypatch) as client:
        engine = db_module.get_engine()
        _source_id, file_id = _insert_source_and_folder(engine, tmp_path / "source")

        favorite_id = client.post(
            "/api/tags",
            json={"display_name": "Favorite", "is_ai_vocabulary": False, "is_user_defined": True},
        ).json()["id"]

        # Pick an existing user-defined tag by id.
        r = client.post(f"/api/files/{file_id}/tags/user-defined", json={"tag_id": favorite_id})
        assert r.status_code == 200
        names = {t["display_name"] for t in client.get(f"/api/files/{file_id}/tags").json()["tags"]}
        assert names == {"Favorite"}

        # Type a brand-new user-defined tag -- it must join the user-defined
        # pool, not the AI vocabulary or a bare ad-hoc tag.
        r = client.post(f"/api/files/{file_id}/tags/user-defined", json={"display_name": "Rewatch"})
        assert r.status_code == 200
        names = {t["display_name"] for t in client.get(f"/api/files/{file_id}/tags").json()["tags"]}
        assert names == {"Favorite", "Rewatch"}
        assert {t["display_name"] for t in client.get("/api/tags", params={"category": "user"}).json()["tags"]} == {
            "Favorite",
            "Rewatch",
        }
        assert client.get("/api/tags").json()["tags"] == []  # never joins the AI vocabulary

        # Unknown tag_id -> 404.
        r = client.post(f"/api/files/{file_id}/tags/user-defined", json={"tag_id": str(uuid.uuid4())})
        assert r.status_code == 404
        assert r.json()["detail"]["error"]["code"] == "tag_not_found"

        # Neither tag_id nor display_name -> 422.
        r = client.post(f"/api/files/{file_id}/tags/user-defined", json={})
        assert r.status_code == 422

        # Unknown file -> 404.
        r = client.post(f"/api/files/{uuid.uuid4()}/tags/user-defined", json={"tag_id": favorite_id})
        assert r.status_code == 404


def test_tagging_settings_roundtrip_over_http(tmp_path, monkeypatch):
    with _fresh_client(tmp_path, monkeypatch) as client:
        r = client.get("/api/tagging-settings")
        assert r.status_code == 200
        assert r.json()["sample_frame_count"] == 9

        r = client.put(
            "/api/tagging-settings",
            json={"sample_frame_count": 6, "combine_into_collage": False, "top_tag_count": 5, "image_resolution": 720},
        )
        assert r.status_code == 200
        assert r.json()["sample_frame_count"] == 6
        assert r.json()["combine_into_collage"] is False
        assert r.json()["image_resolution"] == 720


@pytest.mark.skipif(ffmpeg_missing, reason="ffmpeg/ffprobe not on PATH")
def test_tagging_preview_over_http(tmp_path, monkeypatch):
    with _fresh_client(tmp_path, monkeypatch) as client:
        engine = db_module.get_engine()
        root = tmp_path / "source"
        _source_id, file_id = _insert_source_and_folder(engine, root)
        make_video(root / "clip_0.mp4", duration=3.0, size="320x240")

        r = client.post(
            "/api/tagging-settings/preview",
            json={"file_id": file_id, "sample_frame_count": 4, "combine_into_collage": True, "image_resolution": 128},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["combine_into_collage"] is True
        assert len(body["images"]) == 1
        assert body["images"][0]["width"] % 128 == 0
        assert body["images"][0]["data_url"].startswith("data:image/jpeg;base64,")

        r = client.post(
            "/api/tagging-settings/preview",
            json={"file_id": file_id, "sample_frame_count": 3, "combine_into_collage": False, "image_resolution": 96},
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body["images"]) == 3
        assert all(max(img["width"], img["height"]) == 96 for img in body["images"])

        r = client.post(
            "/api/tagging-settings/preview",
            json={
                "file_id": str(uuid.uuid4()),
                "sample_frame_count": 3,
                "combine_into_collage": False,
                "image_resolution": 96,
            },
        )
        assert r.status_code == 404


def test_provider_entries_crud_and_key_masking_over_http(tmp_path, monkeypatch):
    with _fresh_client(tmp_path, monkeypatch) as client:
        r = client.get("/api/settings/provider-entries")
        assert r.status_code == 200
        assert r.json()["entries"] == []

        r = client.post(
            "/api/settings/provider-entries",
            json={"provider_type": "openrouter", "vision_model": "test-model", "api_key": "sk-should-not-leak"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["has_api_key"] is True
        assert "api_key" not in body
        assert "sk-should-not-leak" not in r.text
        entry_id = body["id"]

        r = client.post("/api/settings/provider-entries", json={"provider_type": "not-a-provider"})
        assert r.status_code == 400

        r = client.put(
            f"/api/settings/provider-entries/{entry_id}",
            json={"display_name": "Renamed", "enabled": True, "vision_model": "test-model", "batch_enabled": False},
        )
        assert r.status_code == 200
        assert r.json()["display_name"] == "Renamed"

        r = client.put("/api/settings/provider-entries/missing-id", json={"display_name": "x", "enabled": False})
        assert r.status_code == 404

        r = client.delete(f"/api/settings/provider-entries/{entry_id}")
        assert r.status_code == 200
        r = client.delete(f"/api/settings/provider-entries/{entry_id}")
        assert r.status_code == 404


def test_provider_entries_reorder_over_http(tmp_path, monkeypatch):
    with _fresh_client(tmp_path, monkeypatch) as client:
        a = client.post("/api/settings/provider-entries", json={"provider_type": "gemini"}).json()
        b = client.post("/api/settings/provider-entries", json={"provider_type": "mistral"}).json()

        r = client.post("/api/settings/provider-entries/reorder", json={"ordered_ids": [b["id"], a["id"]]})
        assert r.status_code == 200
        assert [e["id"] for e in r.json()["entries"]] == [b["id"], a["id"]]

        r = client.post("/api/settings/provider-entries/reorder", json={"ordered_ids": [b["id"]]})
        assert r.status_code == 400


def test_provider_entries_export_includes_plaintext_key_over_http(tmp_path, monkeypatch):
    with _fresh_client(tmp_path, monkeypatch) as client:
        client.post("/api/settings/provider-entries", json={"provider_type": "gemini", "api_key": "sk-export-me"})

        r = client.get("/api/settings/provider-entries/export")
        assert r.status_code == 200
        payload = r.json()
        assert payload["entries"][0]["api_key"] == "sk-export-me"
        assert "attachment" in r.headers["content-disposition"]


def test_provider_entries_import_round_trips_export_and_skips_unknown_types(tmp_path, monkeypatch):
    with _fresh_client(tmp_path, monkeypatch) as client:
        client.post("/api/settings/provider-entries", json={"provider_type": "gemini", "api_key": "sk-export-me"})
        exported = client.get("/api/settings/provider-entries/export").json()
        exported["entries"].append({**exported["entries"][0], "provider_type": "not-a-provider"})

        r = client.post("/api/settings/provider-entries/import", json={"entries": exported["entries"]})
        assert r.status_code == 200
        body = r.json()
        assert len(body["entries"]) == 1
        assert body["skipped"] == 1

        all_entries = client.get("/api/settings/provider-entries").json()["entries"]
        assert [e["provider_type"] for e in all_entries] == ["gemini", "gemini"]
        assert all(e["has_api_key"] for e in all_entries)


def test_provider_entries_export_and_import_round_trip_model_pricing(tmp_path, monkeypatch):
    with _fresh_client(tmp_path, monkeypatch) as client:
        client.put(
            "/api/settings/model-pricing",
            json={
                "provider_type": "gemini",
                "model_name": "gemini-custom",
                "input_per_million": 1.23,
                "output_per_million": 4.56,
            },
        )
        exported = client.get("/api/settings/provider-entries/export").json()
        assert any(p["model_name"] == "gemini-custom" for p in exported["model_pricing"])

        r = client.post(
            "/api/settings/provider-entries/import",
            json={"entries": [], "model_pricing": exported["model_pricing"]},
        )
        assert r.status_code == 200
        assert r.json()["prices_imported"] == len(exported["model_pricing"])

        prices = client.get("/api/settings/model-pricing").json()["prices"]
        restored = next(p for p in prices if p["model_name"] == "gemini-custom")
        assert restored["input_per_million"] == 1.23
        assert restored["output_per_million"] == 4.56


def test_provider_entries_model_listing_endpoints_over_http(tmp_path, monkeypatch):
    monkeypatch.setattr(
        registry, "list_models_for_provider_type", lambda provider_type, api_key: ["model-a", "model-b"]
    )

    with _fresh_client(tmp_path, monkeypatch) as client:
        r = client.post(
            "/api/settings/provider-entries/models", json={"provider_type": "gemini", "api_key": "sk-test"}
        )
        assert r.status_code == 200
        assert r.json()["models"] == ["model-a", "model-b"]

        entry = client.post(
            "/api/settings/provider-entries", json={"provider_type": "gemini", "api_key": "sk-test"}
        ).json()
        r = client.post(f"/api/settings/provider-entries/{entry['id']}/models")
        assert r.status_code == 200
        assert r.json()["models"] == ["model-a", "model-b"]

        no_key_entry = client.post("/api/settings/provider-entries", json={"provider_type": "mistral"}).json()
        r = client.post(f"/api/settings/provider-entries/{no_key_entry['id']}/models")
        assert r.status_code == 400


def test_tag_job_triggers_require_provider_and_vocabulary(tmp_path, monkeypatch):
    # The job worker thread is live for the duration of this `with` block (see
    # module docstring) and could pick up the job created below before the
    # test finishes; stub the provider call so that never means a real
    # network request with a fake key.
    monkeypatch.setattr(
        registry,
        "score_tags_with_fallback",
        lambda engine, entries, images, tags, dead_entry_ids, **_kwargs: ([50], entries[0]),
    )

    with _fresh_client(tmp_path, monkeypatch) as client:
        engine = db_module.get_engine()
        _source_id, file_id = _insert_source_and_folder(engine, tmp_path / "source")

        r = client.post("/api/jobs/tag-file", json={"file_id": file_id})
        assert r.status_code == 400
        assert r.json()["detail"]["error"]["code"] == "no_provider_configured"

        client.post(
            "/api/settings/provider-entries", json={"provider_type": "openrouter", "enabled": True, "api_key": "sk-test"}
        )

        r = client.post("/api/jobs/tag-file", json={"file_id": file_id})
        assert r.status_code == 400
        assert r.json()["detail"]["error"]["code"] == "empty_tag_vocabulary"

        client.post("/api/tags", json={"display_name": "Beach"})

        r = client.post("/api/jobs/tag-file", json={"file_id": file_id})
        assert r.status_code == 200
        assert r.json()["job_type"] == "tag"

        r = client.post("/api/jobs/tag-directory", json={"path": "does-not-exist"})
        assert r.status_code == 404

        r = client.post("/api/jobs/tag-file", json={"file_id": str(uuid.uuid4())})
        assert r.status_code == 404
