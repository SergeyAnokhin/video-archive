"""Application-settings export/import (user request): one bundle of every
setting that is shared app-wide and not tied to a specific source -- the tag
vocabulary (both the AI pool and the user-defined pool; ad-hoc per-file tags
are not included, since those describe individual files rather than app
configuration), conversion profiles, custom preview layout presets, and every
settings singleton (conversion/preview/playback/tagging/backup/interface/
performance).

Deliberately excluded: provider entries (`routers/providers.py` has its own
export/import -- kept separate since that one carries plaintext API keys and
needs its own confirmation warning) and sources/saved sources (connection
details and credentials are specific to one machine's disk or network share,
not portable app configuration).
"""

from __future__ import annotations

from datetime import datetime, timezone

from app import backup_settings, conversion_settings, interface_settings
from app import conversion_profiles as conversion_profiles_service
from app import performance_settings, playback_settings
from app import preview_layouts as preview_layouts_service
from app import preview_settings, tagging_settings
from app import tags as tags_service
from app.config import APP_VERSION

_SETTINGS_MODULES = {
    "conversion_settings": conversion_settings,
    "preview_settings": preview_settings,
    "playback_settings": playback_settings,
    "tagging_settings": tagging_settings,
    "backup_settings": backup_settings,
    "interface_settings": interface_settings,
    "performance_settings": performance_settings,
}


def _strip(data: dict, *extra_keys: str) -> dict:
    excluded = {"id", "created_at", "updated_at", *extra_keys}
    return {key: value for key, value in data.items() if key not in excluded}


def build_export_payload(engine) -> dict:
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "app_version": APP_VERSION,
        "tags": {
            "ai_vocabulary": [_strip(tag) for tag in tags_service.list_tags(engine)],
            "user_defined": [_strip(tag) for tag in tags_service.list_tags(engine, category="user")],
        },
        "conversion_profiles": [_strip(profile) for profile in conversion_profiles_service.list_profiles(engine)],
        "preview_layouts": [
            _strip(preset, "is_builtin")
            for preset in preview_layouts_service.list_presets(engine)
            if not preset["is_builtin"]
        ],
        **{key: _strip(module.get_settings(engine)) for key, module in _SETTINGS_MODULES.items()},
    }


def apply_import(engine, data: dict) -> dict:
    tags_upserted = 0
    tags_payload = data.get("tags") or {}
    for pool, pool_kwargs in (
        ("ai_vocabulary", {"is_ai_vocabulary": True}),
        ("user_defined", {"is_user_defined": True}),
    ):
        for item in tags_payload.get(pool, []):
            # Upsert by name (unlike provider-entries import, which always
            # creates a fresh row): re-importing the same vocabulary after
            # recoloring a tag should sync the color, not pile up duplicates
            # that `create_tag`'s tag_key uniqueness would reject anyway.
            tag = tags_service.get_or_create_tag(engine, item["display_name"], **pool_kwargs)
            tags_service.update_tag(
                engine,
                tag["id"],
                {
                    "display_name": item["display_name"],
                    "is_active": item.get("is_active", True),
                    "sort_order": item.get("sort_order", 0),
                    "color": item.get("color"),
                },
            )
            tags_upserted += 1

    profiles_created = 0
    for item in data.get("conversion_profiles") or []:
        conversion_profiles_service.create_profile(engine, item)
        profiles_created += 1

    layouts_created = 0
    for item in data.get("preview_layouts") or []:
        preview_layouts_service.create_preset(engine, item)
        layouts_created += 1

    settings_applied = []
    for key, module in _SETTINGS_MODULES.items():
        settings_data = data.get(key)
        if settings_data is not None:
            module.update_settings(engine, settings_data)
            settings_applied.append(key)

    return {
        "tags_upserted": tags_upserted,
        "profiles_created": profiles_created,
        "layouts_created": layouts_created,
        "settings_applied": settings_applied,
    }
