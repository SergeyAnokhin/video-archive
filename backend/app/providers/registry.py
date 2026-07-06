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


class ProviderNotConfiguredError(Exception):
    pass


def score_tags_with_provider(engine, provider_name: str, images: list[bytes], tags: list[str]) -> list[int]:
    client = _CLIENTS.get(provider_name)
    if client is None:
        raise ProviderNotConfiguredError(f"Unknown provider: {provider_name}")

    config = provider_configs.get_provider(engine, provider_name)
    if config is None or not config["enabled"]:
        raise ProviderNotConfiguredError(f"Provider is not enabled: {provider_name}")

    api_key = secrets_store.get_provider_api_key(provider_name)
    if not api_key:
        raise ProviderNotConfiguredError(f"No API key configured for provider: {provider_name}")

    return client(images, tags, config["vision_model"], api_key)


__all__ = ["score_tags_with_provider", "ProviderNotConfiguredError", "ProviderError"]
