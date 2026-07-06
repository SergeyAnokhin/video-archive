"""HTTP-layer tests for the tag vocabulary CRUD + autocomplete, tag-filtered
file listing, per-file tag listing, tagging/provider settings, and the
`tag-directory`/`tag-file` job-trigger validation (missing provider, empty
vocabulary, 404s). Does not exercise a real tagging job run (that's
`test_tagging.py`'s job, with a stubbed provider) or a real provider network
call (manual/live verification only).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

import app.db as db_module
from app.main import app
from app.providers import registry


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


def test_tagging_settings_roundtrip_over_http(tmp_path, monkeypatch):
    with _fresh_client(tmp_path, monkeypatch) as client:
        r = client.get("/api/tagging-settings")
        assert r.status_code == 200
        assert r.json()["sample_frame_count"] == 9

        r = client.put(
            "/api/tagging-settings",
            json={"sample_frame_count": 6, "combine_into_collage": False, "top_tag_count": 5},
        )
        assert r.status_code == 200
        assert r.json()["sample_frame_count"] == 6
        assert r.json()["combine_into_collage"] is False


def test_provider_settings_mask_api_key_over_http(tmp_path, monkeypatch):
    with _fresh_client(tmp_path, monkeypatch) as client:
        r = client.get("/api/settings/providers")
        assert r.status_code == 200
        names = {p["provider_name"] for p in r.json()["providers"]}
        assert names == {"openrouter", "gemini", "fal", "mistral"}
        assert all(p["has_api_key"] is False for p in r.json()["providers"])

        r = client.put(
            "/api/settings/providers/openrouter",
            json={"enabled": True, "vision_model": "test-model", "api_key": "sk-should-not-leak"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["has_api_key"] is True
        assert "api_key" not in body
        assert "sk-should-not-leak" not in r.text

        r = client.put("/api/settings/providers/not-a-provider", json={"enabled": True})
        assert r.status_code == 404


def test_tag_job_triggers_require_provider_and_vocabulary(tmp_path, monkeypatch):
    # The job worker thread is live for the duration of this `with` block (see
    # module docstring) and could pick up the job created below before the
    # test finishes; stub the provider call so that never means a real
    # network request with a fake key.
    monkeypatch.setattr(registry, "score_tags_with_provider", lambda *args, **kwargs: [50])

    with _fresh_client(tmp_path, monkeypatch) as client:
        engine = db_module.get_engine()
        _source_id, file_id = _insert_source_and_folder(engine, tmp_path / "source")

        r = client.post("/api/jobs/tag-file", json={"file_id": file_id})
        assert r.status_code == 400
        assert r.json()["detail"]["error"]["code"] == "no_provider_configured"

        client.put("/api/settings/providers/openrouter", json={"enabled": True, "api_key": "sk-test"})

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
