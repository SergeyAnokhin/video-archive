"""Provider entry CRUD tests (`app/provider_entries.py`): the user-managed,
priority-ordered list that replaced the old fixed-4-row `provider_configs`
table. HTTP-level concerns (masking over the wire, export, model listing
errors) live in `test_tagging_router.py`; this file exercises the service
layer directly.
"""

from __future__ import annotations

import pytest

from app import provider_entries, secrets_store


def test_create_entry_assigns_incrementing_sort_order(engine):
    first = provider_entries.create_entry(engine, {"provider_type": "gemini"})
    second = provider_entries.create_entry(engine, {"provider_type": "mistral"})
    assert first["sort_order"] == 0
    assert second["sort_order"] == 1

    entries = provider_entries.list_entries(engine)
    assert [e["id"] for e in entries] == [first["id"], second["id"]]


def test_create_entry_defaults_display_name_from_type_and_model(engine):
    entry = provider_entries.create_entry(engine, {"provider_type": "gemini", "vision_model": "gemini-2.5-flash"})
    assert entry["display_name"] == "gemini/gemini-2.5-flash"


def test_create_entry_rejects_unknown_provider_type(engine):
    with pytest.raises(provider_entries.UnknownProviderTypeError):
        provider_entries.create_entry(engine, {"provider_type": "not-a-provider"})


def test_create_entry_stores_api_key_and_masks_it(engine):
    entry = provider_entries.create_entry(engine, {"provider_type": "openrouter", "api_key": "sk-test-1234"})
    assert "api_key" not in entry
    assert entry["has_api_key"] is True
    assert entry["key_suffix"] == "1234"


def test_multiple_entries_of_same_provider_type_share_one_key(engine):
    a = provider_entries.create_entry(engine, {"provider_type": "gemini", "api_key": "sk-aaaa"})
    b = provider_entries.create_entry(engine, {"provider_type": "gemini", "api_key": "sk-bbbb"})
    assert a["id"] != b["id"]
    entries = provider_entries.list_entries(engine)
    assert {e["provider_type"] for e in entries} == {"gemini"}
    assert [e["key_suffix"] for e in entries] == ["bbbb", "bbbb"]


def test_entry_without_own_key_uses_provider_key(engine):
    secrets_store.set_provider_api_key("mistral", "sk-shared-4321")
    entry = provider_entries.create_entry(engine, {"provider_type": "mistral"})
    assert entry["has_api_key"] is True
    assert entry["key_suffix"] == "4321"


def test_entry_notes_are_stored_and_updated(engine):
    entry = provider_entries.create_entry(engine, {"provider_type": "gemini", "notes": "good at night scenes"})
    assert entry["notes"] == "good at night scenes"
    updated = provider_entries.update_entry(engine, entry["id"], {"notes": "slow"})
    assert updated["notes"] == "slow"


def test_migrate_api_keys_picks_highest_priority_key_and_flags_conflict(engine):
    low = provider_entries.create_entry(engine, {"provider_type": "gemini"})
    high = provider_entries.create_entry(engine, {"provider_type": "gemini"})
    same = provider_entries.create_entry(engine, {"provider_type": "mistral"})
    provider_entries.reorder_entries(engine, [high["id"], low["id"], same["id"]])
    secrets_store.set_entry_api_key(low["id"], "sk-low")
    secrets_store.set_entry_api_key(high["id"], "sk-high")
    secrets_store.set_entry_api_key(same["id"], "sk-mistral")

    with engine.begin() as conn:
        provider_entries.migrate_api_keys(conn)

    assert secrets_store.get_provider_api_key("gemini") == "sk-high"
    assert secrets_store.get_provider_api_key("mistral") == "sk-mistral"
    # Old keys are kept; only gemini had a different one left behind.
    assert secrets_store.get_entry_api_key(low["id"]) == "sk-low"
    gemini_ids = provider_entries.entry_ids_by_type(engine, "gemini")
    assert secrets_store.legacy_entry_keys_differ("gemini", gemini_ids) is True
    assert secrets_store.legacy_entry_keys_differ("mistral", [same["id"]]) is False

    provider_entries.delete_legacy_entry_keys(engine, "gemini")
    assert secrets_store.legacy_entry_keys_differ("gemini", gemini_ids) is False
    assert secrets_store.get_provider_api_key("gemini") == "sk-high"


def test_update_entry_changes_fields_and_rotates_key(engine):
    entry = provider_entries.create_entry(engine, {"provider_type": "mistral", "api_key": "sk-old"})
    updated = provider_entries.update_entry(
        engine,
        entry["id"],
        {
            "display_name": "My Mistral",
            "enabled": False,
            "vision_model": "pixtral-large",
            "text_model": None,
            "batch_enabled": True,
            "api_key": "sk-new-5678",
        },
    )
    assert updated["display_name"] == "My Mistral"
    assert updated["enabled"] is False
    assert updated["vision_model"] == "pixtral-large"
    assert updated["batch_enabled"] is True
    assert updated["key_suffix"] == "5678"


def test_update_entry_returns_none_for_unknown_id(engine):
    assert provider_entries.update_entry(engine, "missing", {"display_name": "x"}) is None


def test_delete_entry_removes_row_and_secret(engine):
    entry = provider_entries.create_entry(engine, {"provider_type": "openrouter", "api_key": "sk-test"})
    assert provider_entries.delete_entry(engine, entry["id"]) is True
    assert provider_entries.get_entry(engine, entry["id"]) is None
    assert provider_entries.delete_entry(engine, entry["id"]) is False


def test_reorder_entries_rewrites_sort_order(engine):
    a = provider_entries.create_entry(engine, {"provider_type": "gemini"})
    b = provider_entries.create_entry(engine, {"provider_type": "mistral"})
    c = provider_entries.create_entry(engine, {"provider_type": "openrouter"})

    reordered = provider_entries.reorder_entries(engine, [c["id"], a["id"], b["id"]])
    assert [e["id"] for e in reordered] == [c["id"], a["id"], b["id"]]
    assert [e["sort_order"] for e in reordered] == [0, 1, 2]


def test_reorder_entries_rejects_mismatched_id_set(engine):
    a = provider_entries.create_entry(engine, {"provider_type": "gemini"})
    provider_entries.create_entry(engine, {"provider_type": "mistral"})

    with pytest.raises(ValueError):
        provider_entries.reorder_entries(engine, [a["id"], "not-a-real-id"])
