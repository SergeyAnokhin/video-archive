"""Provider dispatch: resolves a provider entry (`app/provider_entries.py`)
to its client module and its stored (non-secret) model choice + secret API
key, and implements the priority-ordered fallback chain the tag job
(`app/jobs/tag.py`) uses across multiple enabled entries.
"""

from __future__ import annotations

from app import secrets_store
from app.providers import fal, gemini, mistral, openrouter
from app.providers.base import ProviderError

# These dicts capture each provider module's function *by reference* at
# import time. A test that does `monkeypatch.setattr(gemini, "score_tags",
# fake)` will not affect calls made through `_CLIENTS["gemini"]` -- that
# entry still points at the original function object. Patch the dict entry
# itself instead: `monkeypatch.setitem(registry._CLIENTS, "gemini", fake)`
# (same for `_BATCH_CLIENTS`/`_MODEL_LIST_CLIENTS`).
_CLIENTS = {
    "openrouter": openrouter.score_tags,
    "gemini": gemini.score_tags,
    "fal": fal.score_tags,
    "mistral": mistral.score_tags,
}

# Providers with a Batch API (Specification §12.3, Tech Stack "batch API
# support"); OpenRouter/FAL have no equivalent, so directory-scope tagging
# always falls back to per-file `score_tags_with_entry()` calls for those.
_BATCH_CLIENTS = {
    "gemini": gemini.submit_batch,
    "mistral": mistral.submit_batch,
}
_BATCH_POLL_CLIENTS = {"gemini": gemini.poll_batch, "mistral": mistral.poll_batch}

# Providers with a real model-listing API, for the "Load models" flow. FAL is
# intentionally excluded -- it has no fixed vision-chat schema and its
# model-listing API mixes every model type (image-gen, LoRA, audio, ...),
# not a clean vision-tagging subset (see `app/providers/fal.py`).
_MODEL_LIST_CLIENTS = {
    "openrouter": openrouter.list_models,
    "gemini": gemini.list_models,
    "mistral": mistral.list_models,
}


class ProviderNotConfiguredError(Exception):
    pass


class ModelListingNotSupportedError(Exception):
    pass


class AllProvidersFailedError(Exception):
    """Raised when every enabled provider entry failed for one tagging
    attempt. Callers (the tag job) treat this the same as any other
    per-file failure -- it fails that job item, never invents placeholder
    tags."""


def _resolve_entry_api_key(entry: dict) -> str:
    api_key = secrets_store.get_entry_api_key(entry["id"])
    if not api_key:
        raise ProviderNotConfiguredError(f"No API key configured for provider entry: {entry['display_name']}")
    return api_key


def score_tags_with_entry(engine, entry: dict, images: list[bytes], tags: list[str]) -> list[int]:
    client = _CLIENTS.get(entry["provider_type"])
    if client is None:
        raise ProviderNotConfiguredError(f"Unknown provider type: {entry['provider_type']}")
    if not entry["enabled"]:
        raise ProviderNotConfiguredError(f"Provider entry is not enabled: {entry['display_name']}")

    api_key = _resolve_entry_api_key(entry)
    return client(images, tags, entry["vision_model"], api_key)


def entry_supports_batch(entry: dict) -> bool:
    return entry["provider_type"] in _BATCH_CLIENTS


def score_tags_batch_with_entry(
    engine, entry: dict, items: list[tuple[str, list[bytes]]], tags: list[str]
) -> str:
    client = _BATCH_CLIENTS.get(entry["provider_type"])
    if client is None:
        raise ProviderNotConfiguredError(f"Provider entry does not support batch submission: {entry['display_name']}")

    api_key = _resolve_entry_api_key(entry)
    return client(items, tags, entry["vision_model"], api_key)


def poll_tags_batch_with_entry(engine, entry: dict, external_id: str, item_keys: list[str], tags: list[str]) -> tuple[bool, dict[str, list[int] | None]]:
    client = _BATCH_POLL_CLIENTS.get(entry["provider_type"])
    if client is None:
        raise ProviderNotConfiguredError(f"Provider entry does not support batch polling: {entry['display_name']}")
    return client(external_id, item_keys, tags, entry["vision_model"], _resolve_entry_api_key(entry))


def list_models_for_provider_type(provider_type: str, api_key: str) -> list[str]:
    client = _MODEL_LIST_CLIENTS.get(provider_type)
    if client is None:
        raise ModelListingNotSupportedError(f"Model listing is not supported for provider type: {provider_type}")
    return client(api_key)


def score_tags_with_fallback(
    engine, entries: list[dict], images: list[bytes], tags: list[str], dead_entry_ids: set[str]
) -> tuple[list[int], dict]:
    """Tries `entries` (already filtered to enabled, ordered by priority) in
    order, skipping any id already in `dead_entry_ids` and adding any entry
    that fails to it -- so a broken entry (bad key, quota) is tried at most
    once per job run, not once per remaining file. Returns the scores and
    the entry that produced them. Raises `AllProvidersFailedError` if every
    entry fails."""
    failures = []
    for entry in entries:
        if entry["id"] in dead_entry_ids:
            continue
        try:
            return score_tags_with_entry(engine, entry, images, tags), entry
        except (ProviderError, ProviderNotConfiguredError) as exc:
            failures.append(f"{entry['display_name']} ({entry['provider_type']}): {exc}")
            dead_entry_ids.add(entry["id"])
            continue

    raise AllProvidersFailedError("; ".join(failures) or "No enabled provider entries configured.")


__all__ = [
    "score_tags_with_entry",
    "entry_supports_batch",
    "score_tags_batch_with_entry",
    "poll_tags_batch_with_entry",
    "list_models_for_provider_type",
    "score_tags_with_fallback",
    "ProviderNotConfiguredError",
    "ModelListingNotSupportedError",
    "AllProvidersFailedError",
    "ProviderError",
]
