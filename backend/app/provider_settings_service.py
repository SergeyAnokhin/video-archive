from __future__ import annotations

import json
import uuid
from pathlib import Path
from urllib import error, parse, request

from .db import connection
from .errors import ApiError
from .secrets import SecretStore
from .time_utils import utc_now


PROVIDER_SECTION = "providers"
SUPPORTED_PROVIDERS = ("openrouter", "gemini", "fal", "mistral")
PROVIDER_LABELS = {
    "openrouter": "OpenRouter",
    "gemini": "Google Gemini",
    "fal": "FAL",
    "mistral": "Mistral",
}
DEFAULT_PROVIDER_VALUES = {
    "openrouter": {"vision_model": "", "text_model": "", "prefer_batch": True},
    "gemini": {"vision_model": "gemini-2.0-flash", "text_model": "", "prefer_batch": True},
    "fal": {"vision_model": "", "text_model": "", "prefer_batch": True},
    "mistral": {"vision_model": "pixtral-large-latest", "text_model": "", "prefer_batch": True},
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
                self._secret_store.upsert_provider_api_key(provider["id"], api_key)
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

    def resolve_provider(self, provider_id: str | None = None, provider_name: str | None = None) -> dict:
        providers = self.get_settings()
        if provider_id:
            provider = next((entry for entry in providers if entry["id"] == provider_id), None)
            if provider is None:
                raise ApiError("provider_not_found", f"Provider entry '{provider_id}' does not exist.", status=400)
            if not provider["enabled"]:
                raise ApiError("provider_not_enabled", f"Provider entry '{provider['label']}' is not enabled.", status=400)
            return provider

        enabled = [entry for entry in providers if entry["enabled"]]
        if provider_name:
            provider = next((entry for entry in enabled if entry["provider"] == provider_name), None)
            if provider is None:
                raise ApiError(
                    "provider_not_configured",
                    f"No enabled provider entry is configured for provider '{provider_name}'.",
                    status=400,
                )
            return provider

        if not enabled:
            raise ApiError("provider_not_configured", "Enable and configure at least one AI provider before tagging.", status=400)
        return enabled[0]

    def get_runtime_provider(self, provider_id: str | None = None, provider_name: str | None = None) -> dict:
        provider = dict(self.resolve_provider(provider_id=provider_id, provider_name=provider_name))
        provider["api_key"] = self._secret_store.get_provider_api_key(provider["id"], legacy_provider_name=provider["provider"])
        if not provider["api_key"]:
            raise ApiError("provider_api_key_missing", f"Provider entry '{provider['label']}' does not have an API key configured.", status=400)
        return provider

    def list_models(self, *, provider_name: str, api_key: str) -> list[dict]:
        if provider_name not in SUPPORTED_PROVIDERS:
            raise ApiError("provider_not_supported", f"Provider '{provider_name}' is not supported.", status=400)
        normalized_key = api_key.strip()
        if not normalized_key:
            raise ApiError("provider_api_key_missing", "Enter an API key before loading models.", status=400)

        if provider_name == "openrouter":
            return self._list_openrouter_models(normalized_key)
        if provider_name == "gemini":
            return self._list_gemini_models(normalized_key)
        if provider_name == "mistral":
            return self._list_mistral_models(normalized_key)
        if provider_name == "fal":
            return []
        raise ApiError("provider_not_supported", f"Provider '{provider_name}' is not supported.", status=400)

    def _merge_provider_payload(self, payload: object) -> list[dict]:
        if payload is None:
            payload = []
        if not isinstance(payload, list):
            raise ApiError("invalid_request", "Provider settings payload must be an array.", status=400)

        merged = []
        for index, entry in enumerate(payload):
            merged.append(self._normalize_provider_entry(entry, index=index))

        return merged

    def _normalize_provider_entry(self, entry: object, *, index: int) -> dict:
        if not isinstance(entry, dict):
            raise ApiError("invalid_request", "Each provider settings entry must be a JSON object.", status=400)

        provider_name = entry.get("provider")
        if provider_name not in SUPPORTED_PROVIDERS:
            raise ApiError("invalid_request", "Provider must be one of openrouter, gemini, fal, or mistral.", status=400)

        defaults = DEFAULT_PROVIDER_VALUES[provider_name]
        entry_id = entry.get("id")
        if entry_id is None:
            entry_id = provider_name if self._is_legacy_entry(entry) else str(uuid.uuid4())
        if not isinstance(entry_id, str) or not entry_id.strip():
            raise ApiError("invalid_request", f"Provider '{provider_name}' field 'id' must be a non-empty string.", status=400)

        label = entry.get("label")
        if label is None:
            label = entry.get("name")
        if label is None:
            label = PROVIDER_LABELS[provider_name]
        if not isinstance(label, str):
            raise ApiError("invalid_request", f"Provider '{provider_name}' field 'label' must be a string.", status=400)
        normalized_label = label.strip() or PROVIDER_LABELS[provider_name]

        enabled = entry.get("enabled", False)
        if not isinstance(enabled, bool):
            raise ApiError("invalid_request", f"Provider '{provider_name}' field 'enabled' must be a boolean.", status=400)

        prefer_batch = entry.get("prefer_batch", defaults["prefer_batch"])
        if not isinstance(prefer_batch, bool):
            raise ApiError("invalid_request", f"Provider '{provider_name}' field 'prefer_batch' must be a boolean.", status=400)

        vision_model = entry.get("vision_model", defaults["vision_model"])
        text_model = entry.get("text_model", defaults["text_model"])
        api_key = entry.get("api_key")
        if api_key is not None and not isinstance(api_key, str):
            raise ApiError("invalid_request", f"Provider '{provider_name}' field 'api_key' must be a string when provided.", status=400)
        if not isinstance(vision_model, str):
            raise ApiError("invalid_request", f"Provider '{provider_name}' field 'vision_model' must be a string.", status=400)
        if not isinstance(text_model, str):
            raise ApiError("invalid_request", f"Provider '{provider_name}' field 'text_model' must be a string.", status=400)

        stored_key = self._secret_store.get_provider_api_key(entry_id, legacy_provider_name=provider_name)
        return {
            "id": entry_id.strip(),
            "order_index": index,
            "provider": provider_name,
            "label": normalized_label,
            "enabled": enabled,
            "vision_model": vision_model.strip(),
            "text_model": text_model.strip(),
            "prefer_batch": prefer_batch,
            "api_key": api_key,
            "api_key_configured": bool(stored_key),
        }

    def _is_legacy_entry(self, entry: dict) -> bool:
        return "id" not in entry and set(entry.keys()).issubset(
            {"provider", "enabled", "vision_model", "text_model", "prefer_batch", "api_key", "api_key_configured"}
        )

    def _list_openrouter_models(self, api_key: str) -> list[dict]:
        payload = self._request_json(
            url="https://openrouter.ai/api/v1/models",
            method="GET",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise ApiError("provider_models_invalid_response", "OpenRouter did not return a model list.", status=502)
        models = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = row.get("id")
            if not isinstance(model_id, str) or not model_id.strip():
                continue
            models.append(
                {
                    "id": model_id,
                    "label": row.get("name") if isinstance(row.get("name"), str) and row.get("name").strip() else model_id,
                    "description": row.get("description") if isinstance(row.get("description"), str) else "",
                }
            )
        return sorted(models, key=lambda item: item["label"].lower())

    def _list_gemini_models(self, api_key: str) -> list[dict]:
        models = []
        page_token = ""
        while True:
            params = {"key": api_key}
            if page_token:
                params["pageToken"] = page_token
            payload = self._request_json(
                url=f"https://generativelanguage.googleapis.com/v1beta/models?{parse.urlencode(params)}",
                method="GET",
                headers={},
            )
            rows = payload.get("models")
            if not isinstance(rows, list):
                raise ApiError("provider_models_invalid_response", "Gemini did not return a model list.", status=502)
            for row in rows:
                if not isinstance(row, dict):
                    continue
                raw_name = row.get("name")
                if not isinstance(raw_name, str) or not raw_name.startswith("models/"):
                    continue
                supported = row.get("supportedGenerationMethods")
                if isinstance(supported, list) and "generateContent" not in supported:
                    continue
                model_id = raw_name.removeprefix("models/")
                models.append(
                    {
                        "id": model_id,
                        "label": row.get("displayName") if isinstance(row.get("displayName"), str) and row.get("displayName").strip() else model_id,
                        "description": row.get("description") if isinstance(row.get("description"), str) else "",
                    }
                )
            page_token = payload.get("nextPageToken") if isinstance(payload.get("nextPageToken"), str) else ""
            if not page_token:
                break
        return sorted(models, key=lambda item: item["label"].lower())

    def _list_mistral_models(self, api_key: str) -> list[dict]:
        payload = self._request_json(
            url="https://api.mistral.ai/v1/models",
            method="GET",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        rows = payload.get("data")
        if not isinstance(rows, list):
            raise ApiError("provider_models_invalid_response", "Mistral did not return a model list.", status=502)
        models = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            model_id = row.get("id")
            if not isinstance(model_id, str) or not model_id.strip():
                continue
            models.append(
                {
                    "id": model_id,
                    "label": row.get("name") if isinstance(row.get("name"), str) and row.get("name").strip() else model_id,
                    "description": row.get("description") if isinstance(row.get("description"), str) else "",
                }
            )
        return sorted(models, key=lambda item: item["label"].lower())

    def _request_json(self, *, url: str, method: str, headers: dict[str, str]) -> dict:
        req = request.Request(url, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ApiError("provider_models_http_error", f"Provider model request failed: {detail or exc.reason}", status=502) from exc
        except error.URLError as exc:
            raise ApiError("provider_models_unreachable", f"Provider model request failed: {exc.reason}", status=502) from exc
        except json.JSONDecodeError as exc:
            raise ApiError("provider_models_invalid_response", "Provider returned invalid JSON while loading models.", status=502) from exc
