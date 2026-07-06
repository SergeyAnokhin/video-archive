"""Provider dispatch: resolves a configured provider name to its client
module and its stored (non-secret) model choice + secret API key.
"""

from __future__ import annotations

from app import provider_configs, secrets_store
from app.providers import fal, gemini, mistral, openrouter
from app.providers.base import ProviderError

_CLIENTS = {
    "openrouter": openrouter.score_tags,
    "gemini": gemini.score_tags,
    "fal": fal.score_tags,
    "mistral": mistral.score_tags,
}

# Providers with a Batch API (Specification §12.3, Tech Stack "batch API
# support"); OpenRouter/FAL have no equivalent, so directory-scope tagging
# always falls back to per-file `score_tags_with_provider()` calls for those.
_BATCH_CLIENTS = {
    "gemini": gemini.submit_batch,
    "mistral": mistral.submit_batch,
}


class ProviderNotConfiguredError(Exception):
    pass


def _resolve_provider_config(engine, provider_name: str) -> tuple[dict, str]:
    config = provider_configs.get_provider(engine, provider_name)
    if config is None or not config["enabled"]:
        raise ProviderNotConfiguredError(f"Provider is not enabled: {provider_name}")

    api_key = secrets_store.get_provider_api_key(provider_name)
    if not api_key:
        raise ProviderNotConfiguredError(f"No API key configured for provider: {provider_name}")

    return config, api_key


def score_tags_with_provider(engine, provider_name: str, images: list[bytes], tags: list[str]) -> list[int]:
    client = _CLIENTS.get(provider_name)
    if client is None:
        raise ProviderNotConfiguredError(f"Unknown provider: {provider_name}")

    config, api_key = _resolve_provider_config(engine, provider_name)
    return client(images, tags, config["vision_model"], api_key)


def provider_supports_batch(provider_name: str) -> bool:
    return provider_name in _BATCH_CLIENTS


def score_tags_batch_with_provider(
    engine, provider_name: str, items: list[tuple[str, list[bytes]]], tags: list[str]
) -> dict[str, list[int] | None]:
    client = _BATCH_CLIENTS.get(provider_name)
    if client is None:
        raise ProviderNotConfiguredError(f"Provider does not support batch submission: {provider_name}")

    config, api_key = _resolve_provider_config(engine, provider_name)
    return client(items, tags, config["vision_model"], api_key)


__all__ = [
    "score_tags_with_provider",
    "provider_supports_batch",
    "score_tags_batch_with_provider",
    "ProviderNotConfiguredError",
    "ProviderError",
]
