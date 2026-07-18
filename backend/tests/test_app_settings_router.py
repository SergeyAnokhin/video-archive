"""HTTP-layer tests for the app-settings export/import bundle
(`routers/app_settings.py`): tags (both pools), conversion profiles, preview
layout presets, and every settings singleton -- excluding provider entries
(own export/import, see `test_tagging_router.py`) and sources.
"""

from __future__ import annotations

import app.db as db_module
from fastapi.testclient import TestClient

from app.main import app


def _fresh_client(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)
    return TestClient(app)


def test_export_excludes_provider_entries_and_sources(tmp_path, monkeypatch):
    with _fresh_client(tmp_path, monkeypatch) as client:
        client.post("/api/settings/provider-entries", json={"provider_type": "gemini", "api_key": "sk-secret"})

        r = client.get("/api/settings/app-settings/export")
        assert r.status_code == 200
        payload = r.json()
        assert "attachment" in r.headers["content-disposition"]
        assert "provider_entries" not in payload
        assert "sources" not in payload
        assert "sk-secret" not in r.text


def test_export_import_round_trips_tags_profiles_and_settings(tmp_path, monkeypatch):
    with _fresh_client(tmp_path, monkeypatch) as client:
        client.post("/api/tags", json={"display_name": "Beach", "color": "#123456"})
        client.post(
            "/api/tags", json={"display_name": "Favorite", "is_ai_vocabulary": False, "is_user_defined": True}
        )
        client.post(
            "/api/conversion-profiles",
            json={"name": "Fast", "video_codec": "h264", "container": "mp4", "crf": 28},
        )
        client.put("/api/performance-settings", json={"parallel_workers": 9})

        exported = client.get("/api/settings/app-settings/export").json()
        assert [t["display_name"] for t in exported["tags"]["ai_vocabulary"]] == ["Beach"]
        assert [t["display_name"] for t in exported["tags"]["user_defined"]] == ["Favorite"]
        assert exported["performance_settings"]["parallel_workers"] == 9

        # Re-importing into a fresh database recreates everything; tags
        # upsert by name so a second import in place doesn't duplicate them.
        monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test2.db")
        monkeypatch.setattr(db_module, "_engine", None)
        with TestClient(app) as client2:
            r = client2.post("/api/settings/app-settings/import", json=exported)
            assert r.status_code == 200
            body = r.json()
            assert body["tags_upserted"] == 2
            assert body["profiles_created"] == 1
            assert set(body["settings_applied"]) == {
                "conversion_settings",
                "preview_settings",
                "playback_settings",
                "tagging_settings",
                "backup_settings",
                "interface_settings",
                "performance_settings",
            }

            assert client2.get("/api/performance-settings").json()["parallel_workers"] == 9
            ai_tags = client2.get("/api/tags").json()["tags"]
            assert ai_tags[0]["display_name"] == "Beach"
            assert ai_tags[0]["color"] == "#123456"
            profiles = client2.get("/api/conversion-profiles").json()["profiles"]
            assert [p["name"] for p in profiles] == ["Fast"]

            # Re-import: tags upsert in place instead of duplicating.
            client2.post("/api/settings/app-settings/import", json=exported)
            assert len(client2.get("/api/tags").json()["tags"]) == 1
