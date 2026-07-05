from __future__ import annotations

import json
from pathlib import Path

from .db import connection
from .errors import ApiError
from .secrets import SecretStore
from .time_utils import utc_now


PROVIDER_SECTION = "providers"
SUPPORTED_PROVIDERS = ("openrouter", "gemini", "fal", "mistral")

DEFAULT_PROVIDER_CONFIGS = {
    "openrouter": {
        "provider": "openrouter",
        "enabled": False,
        "vision_model": "",
        "text_model": "",
        "prefer_batch": True,
    },
    "gemini": {
        "provider": "gemini",
        "enabled": False,
        "vision_model": "gemini-2.0-flash",
        "text_model": "",
        "prefer_batch": True,
    },
    "fal": {
        "provider": "fal",
        "enabled": False,
        "vision_model": "",
        "text_model": "",
        "prefer_batch": True,
    },
    "mistral": {
        "provider": "mistral",
        "enabled": False,
        "vision_model": "pixtral-large-latest",
        "text_model": "",
        "prefer_batch": True,
    },
}


class ProviderSettingsService:
    def __init__(self, database_path: Path, secret_store: SecretStore) -> None:
        self._database_path = database_path
        self._secret_store = secret_store

    def get_settings(self) -> list[dict]:
        with connection(self._database_path) as conn:
            row = conn.execute("SELECT payload FROM app_settings WHERE section = ?", (PROVIDER_SECTION,)).fetchone()
        payload = [] if row is None else json.loads(row["payload"])
        return self._merge_provider_payload(payload)

    def update_settings(self, payload: list[dict]) -> list[dict]:
        providers = self._merge_provider_payload(payload)
        now = utc_now()
        stored_payload = []
        for provider in providers:
            api_key = provider.pop("api_key", None)
            if api_key is not None:
                self._secret_store.upsert_provider_api_key(provider["provider"], api_key)
            stored_payload.append(provider)

        with connection(self._database_path) as conn, conn:
            conn.execute(
                """
                INSERT INTO app_settings (section, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(section) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at
                """,
                (PROVIDER_SECTION, json.dumps(stored_payload), now, now),
            )
        return self.get_settings()

    def resolve_provider(self, provider_name: str | None = None) -> dict:
        providers = self.get_settings()
        if provider_name:
            provider = next((entry for entry in providers if entry["provider"] == provider_name), None)
            if provider is None:
                raise ApiError("provider_not_supported", f"Provider '{provider_name}' is not supported.", status=400)
            if not provider["enabled"]:
                raise ApiError("provider_not_enabled", f"Provider '{provider_name}' is not enabled.", status=400)
            return provider

        enabled = [entry for entry in providers if entry["enabled"]]
        if not enabled:
            raise ApiError("provider_not_configured", "Enable and configure at least one AI provider before tagging.", status=400)
        return enabled[0]

    def get_runtime_provider(self, provider_name: str | None = None) -> dict:
        provider = dict(self.resolve_provider(provider_name))
        provider["api_key"] = self._secret_store.get_provider_api_key(provider["provider"])
        if not provider["api_key"]:
            raise ApiError("provider_api_key_missing", f"Provider '{provider['provider']}' does not have an API key configured.", status=400)
        return provider

    def _merge_provider_payload(self, payload: object) -> list[dict]:
        if payload is None:
            payload = []
        if not isinstance(payload, list):
            raise ApiError("invalid_request", "Provider settings payload must be an array.", status=400)

        incoming = {}
        for entry in payload:
            if not isinstance(entry, dict):
                raise ApiError("invalid_request", "Each provider settings entry must be a JSON object.", status=400)
            provider_name = entry.get("provider")
            if provider_name not in SUPPORTED_PROVIDERS:
                raise ApiError("invalid_request", "Provider must be one of openrouter, gemini, fal, or mistral.", status=400)
            incoming[provider_name] = entry

        merged: list[dict] = []
        for provider_name in SUPPORTED_PROVIDERS:
            base = dict(DEFAULT_PROVIDER_CONFIGS[provider_name])
            raw = incoming.get(provider_name, {})
            enabled = raw.get("enabled", base["enabled"])
            if not isinstance(enabled, bool):
                raise ApiError("invalid_request", f"Provider '{provider_name}' field 'enabled' must be a boolean.", status=400)
            prefer_batch = raw.get("prefer_batch", base["prefer_batch"])
            if not isinstance(prefer_batch, bool):
                raise ApiError("invalid_request", f"Provider '{provider_name}' field 'prefer_batch' must be a boolean.", status=400)
            vision_model = raw.get("vision_model", base["vision_model"])
            text_model = raw.get("text_model", base["text_model"])
            api_key = raw.get("api_key")
            if api_key is not None and not isinstance(api_key, str):
                raise ApiError("invalid_request", f"Provider '{provider_name}' field 'api_key' must be a string when provided.", status=400)
            if not isinstance(vision_model, str):
                raise ApiError("invalid_request", f"Provider '{provider_name}' field 'vision_model' must be a string.", status=400)
            if not isinstance(text_model, str):
                raise ApiError("invalid_request", f"Provider '{provider_name}' field 'text_model' must be a string.", status=400)

            merged.append(
                {
                    "provider": provider_name,
                    "enabled": enabled,
                    "vision_model": vision_model.strip(),
                    "text_model": text_model.strip(),
                    "prefer_batch": prefer_batch,
                    "api_key": api_key,
                    "api_key_configured": bool(self._secret_store.get_provider_api_key(provider_name)),
                }
            )
        return merged
