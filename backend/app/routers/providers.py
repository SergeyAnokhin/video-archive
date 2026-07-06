"""AI provider settings endpoints (API §13, Specification §18): the four
fixed provider rows are pre-seeded and only ever updated, never created or
deleted. API keys are write-only from the frontend's perspective — this
router never echoes a stored key back, only `has_api_key`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import provider_configs as service
from app.db import get_engine

router = APIRouter()


class ProviderUpdateRequest(BaseModel):
    enabled: bool = False
    vision_model: str | None = None
    text_model: str | None = None
    batch_enabled: bool = False
    api_key: str | None = None


def _not_found_error(provider_name: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "provider_not_found", "message": f"Unknown provider: {provider_name}"}},
    )


@router.get("/settings/providers")
def list_providers():
    return {"providers": service.list_providers(get_engine())}


@router.put("/settings/providers/{provider_name}")
def update_provider(provider_name: str, body: ProviderUpdateRequest):
    try:
        provider = service.update_provider(get_engine(), provider_name, body.model_dump())
    except service.UnknownProviderError:
        raise _not_found_error(provider_name)
    if provider is None:
        raise _not_found_error(provider_name)
    return provider
