"""AI provider entry CRUD (Specification §18, Settings §6, API §13).

Unlike the old fixed-4-row `provider_configs` table this replaces, provider
entries are a user-managed, priority-ordered list: any number of entries per
`provider_type` are allowed (e.g. two different Gemini keys/models), created
and deleted freely through the API. `sort_order` is the fallback priority —
the tag job (`app/jobs/tag.py`) tries enabled entries in ascending
`sort_order`, falling through to the next one on failure.

Only non-secret fields live in `provider_entries`; the API key itself is
written to/read from the local secrets file (`app/secrets_store.py`), keyed
by entry id, and is never returned to the frontend — only whether one is
currently set (`has_api_key`) and a masked suffix (`key_suffix`).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app import secrets_store

PROVIDER_TYPES = ("openrouter", "gemini", "fal", "mistral")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class UnknownProviderTypeError(Exception):
    pass


def _row_to_dict(row) -> dict:
    return {
        "id": row.id,
        "provider_type": row.provider_type,
        "display_name": row.display_name,
        "enabled": bool(row.enabled),
        "vision_model": row.vision_model,
        "text_model": row.text_model,
        "batch_enabled": bool(row.batch_enabled),
        "sort_order": row.sort_order,
        "has_api_key": secrets_store.has_entry_api_key(row.id),
        "key_suffix": secrets_store.get_entry_api_key_suffix(row.id),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_entries(engine) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM provider_entries ORDER BY sort_order, created_at")).all()
    return [_row_to_dict(row) for row in rows]


def get_entry(engine, entry_id: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM provider_entries WHERE id = :id"), {"id": entry_id}).fetchone()
    return _row_to_dict(row) if row else None


def create_entry(engine, data: dict) -> dict:
    provider_type = data.get("provider_type")
    if provider_type not in PROVIDER_TYPES:
        raise UnknownProviderTypeError(f"Unknown provider type: {provider_type}")

    entry_id = str(uuid.uuid4())
    now = _now()
    with engine.begin() as conn:
        next_order = conn.execute(text("SELECT COALESCE(MAX(sort_order), -1) + 1 FROM provider_entries")).scalar()
        conn.execute(
            text(
                """
                INSERT INTO provider_entries
                    (id, provider_type, display_name, enabled, vision_model, text_model,
                     batch_enabled, sort_order, created_at, updated_at)
                VALUES (:id, :provider_type, :display_name, :enabled, :vision_model, :text_model,
                        :batch_enabled, :sort_order, :now, :now)
                """
            ),
            {
                "id": entry_id,
                "provider_type": provider_type,
                "display_name": data.get("display_name") or f"{provider_type}/{data.get('vision_model') or '?'}",
                "enabled": bool(data.get("enabled", True)),
                "vision_model": data.get("vision_model"),
                "text_model": data.get("text_model"),
                "batch_enabled": bool(data.get("batch_enabled", False)),
                "sort_order": next_order,
                "now": now,
            },
        )
    if data.get("api_key"):
        secrets_store.set_entry_api_key(entry_id, data["api_key"])
    return get_entry(engine, entry_id)


def update_entry(engine, entry_id: str, data: dict) -> dict | None:
    existing = get_entry(engine, entry_id)
    if existing is None:
        return None

    merged = {**existing, **data}
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE provider_entries
                SET display_name = :display_name, enabled = :enabled, vision_model = :vision_model,
                    text_model = :text_model, batch_enabled = :batch_enabled, updated_at = :now
                WHERE id = :id
                """
            ),
            {
                "display_name": merged["display_name"],
                "enabled": bool(merged["enabled"]),
                "vision_model": merged["vision_model"],
                "text_model": merged["text_model"],
                "batch_enabled": bool(merged["batch_enabled"]),
                "now": now,
                "id": entry_id,
            },
        )
    if data.get("api_key"):
        secrets_store.set_entry_api_key(entry_id, data["api_key"])
    return get_entry(engine, entry_id)


def delete_entry(engine, entry_id: str) -> bool:
    with engine.begin() as conn:
        result = conn.execute(text("DELETE FROM provider_entries WHERE id = :id"), {"id": entry_id})
    if result.rowcount > 0:
        secrets_store.delete_entry_api_key(entry_id)
        return True
    return False


def reorder_entries(engine, ordered_ids: list[str]) -> list[dict]:
    with engine.begin() as conn:
        existing_ids = {row.id for row in conn.execute(text("SELECT id FROM provider_entries"))}
        if set(ordered_ids) != existing_ids:
            raise ValueError("Reorder list must contain exactly the current set of provider entry ids.")
        now = _now()
        for index, entry_id in enumerate(ordered_ids):
            conn.execute(
                text("UPDATE provider_entries SET sort_order = :order, updated_at = :now WHERE id = :id"),
                {"order": index, "now": now, "id": entry_id},
            )
    return list_entries(engine)
