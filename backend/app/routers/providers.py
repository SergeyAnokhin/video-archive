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
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app import model_pricing, provider_entries as service
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
    api_key: str | None = None


class ProviderEntryUpdateRequest(BaseModel):
    display_name: str
    enabled: bool = False
    vision_model: str | None = None
    text_model: str | None = None
    batch_enabled: bool = False
    api_key: str | None = None


class ProviderEntryImportItem(BaseModel):
    provider_type: str
    display_name: str | None = None
    enabled: bool = True
    vision_model: str | None = None
    text_model: str | None = None
    batch_enabled: bool = False
    api_key: str | None = None


class ProviderEntriesImportRequest(BaseModel):
    entries: list[ProviderEntryImportItem]


class ReorderRequest(BaseModel):
    ordered_ids: list[str]


class ModelListRequest(BaseModel):
    provider_type: str
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


@router.get("/settings/model-ratings")
def get_model_ratings():
    """Per-model like/dislike accuracy rating and apply-behavior KPI (user
    request -- know at a glance which model is worth picking), aggregated
    the same way pricing is (`provider_type`, `model_name`), for Tag Lab's
    model picker."""
    return {"ratings": tag_lab_feedback.get_all_model_stats(get_engine())}


@router.post("/settings/provider-entries")
def create_provider_entry(body: ProviderEntryCreateRequest):
    try:
        return service.create_entry(get_engine(), body.model_dump())
    except service.UnknownProviderTypeError as exc:
        raise HTTPException(status_code=400, detail={"error": {"code": "unknown_provider_type", "message": str(exc)}})


@router.put("/settings/provider-entries/{entry_id}")
def update_provider_entry(entry_id: str, body: ProviderEntryUpdateRequest):
    entry = service.update_entry(get_engine(), entry_id, body.model_dump())
    if entry is None:
        raise _not_found_error(entry_id)
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
    try:
        return {"models": registry.list_models_for_provider_type(body.provider_type, body.api_key)}
    except (registry.ModelListingNotSupportedError, registry.ProviderError) as exc:
        raise _list_models_error(exc)


@router.post("/settings/provider-entries/{entry_id}/models")
def list_models_for_entry(entry_id: str):
    engine = get_engine()
    entry = service.get_entry(engine, entry_id)
    if entry is None:
        raise _not_found_error(entry_id)
    api_key = secrets_store.get_entry_api_key(entry_id)
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail={"error": {"code": "no_api_key", "message": "This provider entry has no API key configured."}},
        )
    try:
        return {"models": registry.list_models_for_provider_type(entry["provider_type"], api_key)}
    except (registry.ModelListingNotSupportedError, registry.ProviderError) as exc:
        raise _list_models_error(exc)


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
                "sort_order": entry["sort_order"],
                "api_key": secrets_store.get_entry_api_key(entry["id"]),
            }
        )
    payload = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "app_version": APP_VERSION,
        "entries": entries,
    }
    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=provider-entries-export.json"},
    )


@router.post("/settings/provider-entries/import")
def import_provider_entries(body: ProviderEntriesImportRequest):
    engine = get_engine()
    created = []
    skipped = 0
    for item in body.entries:
        try:
            created.append(service.create_entry(engine, item.model_dump()))
        except service.UnknownProviderTypeError:
            skipped += 1
    return {"entries": created, "skipped": skipped}
