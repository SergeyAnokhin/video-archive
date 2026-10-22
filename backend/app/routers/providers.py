"""AI provider entry endpoints (API §13, Specification §18): a user-managed,
priority-ordered list of provider entries (`app/provider_entries.py`) —
create/update/delete/reorder freely, unlike the old fixed-4-row shape.

API keys are write-only from the frontend's perspective everywhere except
`GET .../export`, which is an explicit, user-requested exception: the
exported file contains plaintext keys so the frontend must show a clear
warning before triggering the download. `POST .../import` reads that same
export shape back in, creating one new entry per item (invalid
`provider_type` values are skipped, not fatal, since a hand-edited file
shouldn't abort the whole batch).

The export/import also carries `model_pricing` (user request -- re-entering
per-model $/1M-token prices by hand after a restore was too tedious):
`model_pricing` rows are keyed by `(provider_type, model_name)`, not by
provider entry, so they're exported/imported as their own list alongside
`entries` and upserted independently of entry creation.

API keys are one per provider type (`secrets_store.get_provider_api_key()`),
managed through `/settings/providers/{type}/api-key`; an `api_key` sent with
an entry create/update still sets that shared key. The export carries them
as `provider_keys` (type -> key); an import also accepts the older
per-entry `api_key` field, used only when that type has no key yet.
`/settings/providers/...` also serves the cached, at-most-daily model
catalogs (`app/provider_catalog.py`).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app import model_pricing, provider_catalog, provider_entries as service
from app import provider_usage, secrets_store, tag_lab_feedback
from app.config import APP_VERSION
from app.db import get_engine
from app.providers import registry

router = APIRouter()


class ProviderEntryCreateRequest(BaseModel):
    provider_type: str
    display_name: str | None = None
    enabled: bool = True
    vision_model: str | None = None
    text_model: str | None = None
    batch_enabled: bool = False
    notes: str | None = None
    api_key: str | None = None


class ProviderEntryUpdateRequest(BaseModel):
    display_name: str
    enabled: bool = False
    vision_model: str | None = None
    text_model: str | None = None
    batch_enabled: bool = False
    # Left untouched when the request omits it (unlike the fields above).
    notes: str | None = None
    api_key: str | None = None


class ProviderEntryImportItem(BaseModel):
    provider_type: str
    display_name: str | None = None
    enabled: bool = True
    vision_model: str | None = None
    text_model: str | None = None
    batch_enabled: bool = False
    notes: str | None = None
    # Pre-"one key per provider" export format.
    api_key: str | None = None


class ModelPricingImportItem(BaseModel):
    provider_type: str
    model_name: str
    input_per_million: float | None = None
    output_per_million: float | None = None
    source: str = "manual"


class ProviderEntriesImportRequest(BaseModel):
    entries: list[ProviderEntryImportItem]
    model_pricing: list[ModelPricingImportItem] = []
    provider_keys: dict[str, str] = {}


class ReorderRequest(BaseModel):
    ordered_ids: list[str]


class ModelListRequest(BaseModel):
    provider_type: str
    # Falls back to the provider's stored key when omitted.
    api_key: str | None = None


class ProviderApiKeyRequest(BaseModel):
    api_key: str


class ModelPricingUpsertRequest(BaseModel):
    provider_type: str
    model_name: str
    input_per_million: float
    output_per_million: float


def _not_found_error(entry_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "provider_entry_not_found", "message": f"Unknown provider entry: {entry_id}"}},
    )


def _list_models_error(exc: Exception) -> HTTPException:
    return HTTPException(status_code=400, detail={"error": {"code": "model_listing_failed", "message": str(exc)}})


def _no_api_key_error(provider_type: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={"error": {"code": "no_api_key", "message": f"No API key configured for provider {provider_type}."}},
    )


def _check_provider_type(provider_type: str) -> None:
    if provider_type not in service.PROVIDER_TYPES:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "unknown_provider_type", "message": f"Unknown provider type: {provider_type}"}},
        )


def _providers_response(engine) -> dict:
    return {"providers": provider_catalog.list_provider_statuses(engine)}


@router.get("/settings/providers")
def list_providers():
    """Per-provider overview: shared key presence/suffix and the cached
    model catalog's size and freshness. Never makes a network call."""
    return _providers_response(get_engine())


@router.put("/settings/providers/{provider_type}/api-key")
def set_provider_api_key(provider_type: str, body: ProviderApiKeyRequest):
    """Sets the provider's one shared key and refreshes its catalog right
    away -- doubles as a key check (a bad key shows up as the catalog
    error; the key itself is still saved)."""
    _check_provider_type(provider_type)
    engine = get_engine()
    secrets_store.set_provider_api_key(provider_type, body.api_key)
    provider_catalog.refresh_catalog(engine, provider_type)
    return _providers_response(engine)


@router.delete("/settings/providers/{provider_type}/api-key")
def delete_provider_api_key(provider_type: str):
    _check_provider_type(provider_type)
    secrets_store.delete_provider_api_key(provider_type)
    return _providers_response(get_engine())


@router.delete("/settings/providers/{provider_type}/legacy-keys")
def delete_provider_legacy_keys(provider_type: str):
    """Drops the old per-entry keys the one-key-per-provider migration kept
    around (`legacy_key_conflict`), once the user has checked the key."""
    _check_provider_type(provider_type)
    engine = get_engine()
    service.delete_legacy_entry_keys(engine, provider_type)
    return _providers_response(engine)


@router.get("/settings/providers/{provider_type}/models")
def get_provider_models(provider_type: str):
    """The cached model catalog (with OpenRouter's prices), refreshed first
    if it's older than a day."""
    _check_provider_type(provider_type)
    return provider_catalog.get_catalog(get_engine(), provider_type)


@router.post("/settings/providers/refresh-catalogs")
def refresh_provider_catalogs(force: bool = False):
    """Refreshes every keyed provider's catalog that's older than a day, or
    all of them with `?force=true` (the manual "refresh now" button)."""
    engine = get_engine()
    provider_catalog.refresh_stale(engine, force=force)
    return _providers_response(engine)


@router.get("/settings/provider-entries")
def list_provider_entries():
    return {"entries": service.list_entries(get_engine())}


@router.get("/settings/provider-usage")
def get_provider_usage():
    """Aggregated AI-provider call stats (user request -- which models were
    used across the app, with token counts and an estimated cost where the
    provider exposes usage metadata), for the Settings usage panel."""
    return {"usage": provider_usage.get_usage_summary(get_engine())}


@router.get("/settings/model-pricing")
def get_model_pricing():
    """Editable, sourced $/1M-token pricing per (provider_type, model_name)
    (user request -- Tag Lab's cost estimate should be correctable, not just
    a hardcoded guess), for the Settings pricing table and Tag Lab's inline
    price display."""
    return {"prices": model_pricing.list_prices(get_engine())}


@router.put("/settings/model-pricing")
def upsert_model_pricing(body: ModelPricingUpsertRequest):
    return model_pricing.upsert_price(
        get_engine(), body.provider_type, body.model_name,
        body.input_per_million, body.output_per_million, "manual",
    )


@router.post("/settings/model-pricing/refresh-openrouter")
def refresh_model_pricing_from_openrouter():
    """Fetches live pricing from OpenRouter's public `/models` endpoint for
    every OpenRouter model currently configured on a provider entry, and
    upserts matches. Returns which model strings were/weren't found so the
    Settings UI can report it."""
    try:
        return model_pricing.refresh_openrouter_prices(get_engine())
    except registry.ProviderError as exc:
        raise HTTPException(
            status_code=400, detail={"error": {"code": "pricing_refresh_failed", "message": str(exc)}}
        )


@router.post("/settings/model-pricing/import-catalog")
def import_model_pricing_catalog(body: dict):
    """Bulk price update from an uploaded third-party pricing JSON (user
    request). `body` is that file's own top-level shape, passed through
    unparsed by the frontend -- see `model_pricing.import_catalog_prices()`
    for the matching/update rules."""
    try:
        return model_pricing.import_catalog_prices(get_engine(), body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": {"code": "invalid_catalog", "message": str(exc)}})


@router.get("/settings/model-ratings")
def get_model_ratings():
    """Per-model like/dislike accuracy rating and apply-behavior KPI (user
    request -- know at a glance which model is worth picking), aggregated
    the same way pricing is (`provider_type`, `model_name`), for Tag Lab's
    model picker."""
    return {"ratings": tag_lab_feedback.get_all_model_stats(get_engine())}


@router.post("/settings/provider-entries")
def create_provider_entry(body: ProviderEntryCreateRequest):
    engine = get_engine()
    try:
        entry = service.create_entry(engine, body.model_dump())
    except service.UnknownProviderTypeError as exc:
        raise HTTPException(status_code=400, detail={"error": {"code": "unknown_provider_type", "message": str(exc)}})
    provider_catalog.fill_missing_prices(engine, entry["provider_type"], [entry["vision_model"], entry["text_model"]])
    return entry


@router.put("/settings/provider-entries/{entry_id}")
def update_provider_entry(entry_id: str, body: ProviderEntryUpdateRequest):
    engine = get_engine()
    data = body.model_dump()
    if "notes" not in body.model_fields_set:
        del data["notes"]
    entry = service.update_entry(engine, entry_id, data)
    if entry is None:
        raise _not_found_error(entry_id)
    provider_catalog.fill_missing_prices(engine, entry["provider_type"], [entry["vision_model"], entry["text_model"]])
    return entry


@router.delete("/settings/provider-entries/{entry_id}")
def delete_provider_entry(entry_id: str):
    if not service.delete_entry(get_engine(), entry_id):
        raise _not_found_error(entry_id)
    return {"deleted": True}


@router.post("/settings/provider-entries/reorder")
def reorder_provider_entries(body: ReorderRequest):
    try:
        return {"entries": service.reorder_entries(get_engine(), body.ordered_ids)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": {"code": "invalid_reorder", "message": str(exc)}})


@router.post("/settings/provider-entries/models")
def list_models_for_draft(body: ModelListRequest):
    api_key = body.api_key or secrets_store.get_provider_api_key(body.provider_type)
    if not api_key:
        raise _no_api_key_error(body.provider_type)
    try:
        return {"models": registry.list_models_for_provider_type(body.provider_type, api_key)}
    except (registry.ModelListingNotSupportedError, registry.ProviderError) as exc:
        raise _list_models_error(exc)


@router.post("/settings/provider-entries/{entry_id}/models")
def list_models_for_entry(entry_id: str):
    engine = get_engine()
    entry = service.get_entry(engine, entry_id)
    if entry is None:
        raise _not_found_error(entry_id)
    provider_type = entry["provider_type"]
    if not entry["has_api_key"]:
        raise _no_api_key_error(provider_type)
    if provider_type not in provider_catalog.CATALOG_PROVIDER_TYPES:
        raise _list_models_error(
            registry.ModelListingNotSupportedError(f"Model listing is not supported for provider type: {provider_type}")
        )
    catalog = provider_catalog.get_catalog(engine, provider_type)
    if not catalog["models"] and catalog["error"]:
        raise _list_models_error(registry.ProviderError(catalog["error"]))
    return {"models": [model["model_id"] for model in catalog["models"]]}


@router.get("/settings/provider-entries/export")
def export_provider_entries():
    engine = get_engine()
    entries = []
    for entry in service.list_entries(engine):
        entries.append(
            {
                "provider_type": entry["provider_type"],
                "display_name": entry["display_name"],
                "enabled": entry["enabled"],
                "vision_model": entry["vision_model"],
                "text_model": entry["text_model"],
                "batch_enabled": entry["batch_enabled"],
                "notes": entry["notes"],
                "sort_order": entry["sort_order"],
            }
        )
    provider_keys = {
        provider_type: key
        for provider_type in service.PROVIDER_TYPES
        if (key := secrets_store.get_provider_api_key(provider_type))
    }
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "app_version": APP_VERSION,
        "provider_keys": provider_keys,
        "entries": entries,
        "model_pricing": model_pricing.list_prices(engine),
    }
    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=provider-entries-export.json"},
    )


@router.post("/settings/provider-entries/import")
def import_provider_entries(body: ProviderEntriesImportRequest):
    engine = get_engine()
    for provider_type, api_key in body.provider_keys.items():
        if provider_type in service.PROVIDER_TYPES and api_key:
            secrets_store.set_provider_api_key(provider_type, api_key)

    created = []
    skipped = 0
    for item in body.entries:
        data = item.model_dump()
        legacy_key = data.pop("api_key")
        try:
            created.append(service.create_entry(engine, data))
        except service.UnknownProviderTypeError:
            skipped += 1
            continue
        if legacy_key and not secrets_store.get_provider_api_key(item.provider_type):
            secrets_store.set_provider_api_key(item.provider_type, legacy_key)

    prices_imported = 0
    for price in body.model_pricing:
        if price.input_per_million is None or price.output_per_million is None:
            continue
        model_pricing.upsert_price(
            engine, price.provider_type, price.model_name,
            price.input_per_million, price.output_per_million, price.source,
        )
        prices_imported += 1

    return {"entries": created, "skipped": skipped, "prices_imported": prices_imported}
