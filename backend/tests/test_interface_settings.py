"""Interface settings singleton tests (Stage 9, Settings §9; post-V1 preview
profiles): language + theme preset + the two preview-stylization profiles,
service-level round trip plus the HTTP endpoint.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.db as db_module
from app import interface_settings
from app.main import app


def _profile_payload(saturation: int) -> dict:
    payload = {}
    for profile in ("a", "b"):
        defaults = interface_settings.DEFAULT_PROFILE_A if profile == "a" else interface_settings.DEFAULT_PROFILE_B
        for field, value in defaults.items():
            payload[f"profile_{profile}_{field}"] = saturation if field == "saturation" else value
    return payload


def test_interface_settings_defaults_and_round_trip(engine):
    settings = interface_settings.get_settings(engine)
    assert settings["language"] == "en"
    assert settings["theme_preset"] == "strict"
    assert settings["profile_a_saturation"] == 100
    assert settings["profile_a_blur"] == 0
    assert settings["profile_b_saturation"] == 20
    assert settings["profile_b_blur"] == 16
    assert settings["search_tag_limit"] == 10
    assert settings["search_file_limit"] == 10
    assert settings["search_dir_limit"] == 10

    updated = interface_settings.update_settings(
        engine,
        {
            "language": "ru",
            "theme_preset": "playful",
            **_profile_payload(50),
            "search_tag_limit": 5,
            "search_file_limit": 25,
            "search_dir_limit": 3,
        },
    )
    assert updated["language"] == "ru"
    assert updated["theme_preset"] == "playful"
    assert updated["profile_a_saturation"] == 50
    assert updated["profile_b_saturation"] == 50
    assert updated["search_tag_limit"] == 5
    assert updated["search_file_limit"] == 25
    assert updated["search_dir_limit"] == 3
    assert interface_settings.get_settings(engine)["theme_preset"] == "playful"


def test_interface_settings_over_http(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.get("/api/interface-settings")
        assert r.status_code == 200
        body = r.json()
        assert body["language"] == "en"
        assert body["theme_preset"] == "strict"
        assert body["profile_a_saturation"] == 100
        assert body["profile_b_blur"] == 16
        assert body["search_tag_limit"] == 10

        r = client.put(
            "/api/interface-settings",
            json={"language": "ru", "theme_preset": "playful", **_profile_payload(0), "search_file_limit": 30},
        )
        assert r.status_code == 200
        assert r.json()["language"] == "ru"
        assert r.json()["theme_preset"] == "playful"
        assert r.json()["profile_a_saturation"] == 0
        assert r.json()["profile_b_saturation"] == 0
        assert r.json()["search_file_limit"] == 30

        # out-of-range search limits are rejected (SEARCH_LIMIT_RANGE)
        r = client.put("/api/interface-settings", json={**_profile_payload(0), "search_tag_limit": 0})
        assert r.status_code == 422

        assert client.get("/api/interface-settings").json()["theme_preset"] == "playful"

        # out-of-range values are rejected (ge/le constraints from PROFILE_RANGES)
        r = client.put("/api/interface-settings", json={**_profile_payload(0), "profile_a_blur": 999})
        assert r.status_code == 422
