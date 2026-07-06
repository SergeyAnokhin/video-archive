"""AI provider configuration (Specification §18, Settings §6, API §13).

The four V1 provider targets are a fixed set (unlike, say, conversion
profiles): rows are seeded once and only ever updated, never created or
deleted through the API. Only non-secret fields (enabled flag, model
choices, batch preference) live in `provider_configs`; the API key itself is
written to/read from the local secrets file (`app/secrets_store.py`) and is
never returned to the frontend — only whether one is currently set.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from app import secrets_store

PROVIDERS = ("openrouter", "gemini", "fal", "mistral")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class UnknownProviderError(Exception):
    pass


def _row_to_dict(row) -> dict:
    return {
        "provider_name": row.provider_name,
        "enabled": bool(row.enabled),
        "vision_model": row.vision_model,
        "text_model": row.text_model,
        "batch_enabled": bool(row.batch_enabled),
        "has_api_key": secrets_store.has_provider_api_key(row.provider_name),
        "updated_at": row.updated_at,
    }


def list_providers(engine) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM provider_configs ORDER BY provider_name")).all()
    return [_row_to_dict(row) for row in rows]


def get_provider(engine, provider_name: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM provider_configs WHERE provider_name = :name"), {"name": provider_name}
        ).fetchone()
    return _row_to_dict(row) if row else None


def update_provider(engine, provider_name: str, data: dict) -> dict | None:
    if provider_name not in PROVIDERS:
        raise UnknownProviderError(f"Unknown provider: {provider_name}")
    if get_provider(engine, provider_name) is None:
        return None

    if data.get("api_key"):
        secrets_store.set_provider_api_key(provider_name, data["api_key"])

    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE provider_configs
                SET enabled = :enabled, vision_model = :vision_model, text_model = :text_model,
                    batch_enabled = :batch_enabled, updated_at = :now
                WHERE provider_name = :name
                """
            ),
            {
                "enabled": bool(data.get("enabled", False)),
                "vision_model": data.get("vision_model"),
                "text_model": data.get("text_model"),
                "batch_enabled": bool(data.get("batch_enabled", False)),
                "now": now,
                "name": provider_name,
            },
        )
    return get_provider(engine, provider_name)


def seed_default_providers(conn) -> None:
    """Idempotently insert the four fixed provider rows. Called once from
    `init_db()` right after migration 6 creates the table."""
    now = _now()
    for provider_name in PROVIDERS:
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO provider_configs
                    (provider_name, enabled, vision_model, text_model, batch_enabled, updated_at)
                VALUES (:name, 0, NULL, NULL, 0, :now)
                """
            ),
            {"name": provider_name, "now": now},
        )
