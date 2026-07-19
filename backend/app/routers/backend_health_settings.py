"""Backend-health-indicator timeout settings endpoint (chat request
2026-07-19 follow-up)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import backend_health_settings as service
from app.db import get_engine

router = APIRouter()


class BackendHealthSettingsRequest(BaseModel):
    slow_timeout_seconds: int = Field(
        default=service.DEFAULT_SLOW_TIMEOUT_SECONDS,
        ge=service.MIN_SLOW_TIMEOUT_SECONDS,
        le=service.MAX_SLOW_TIMEOUT_SECONDS,
    )
    offline_timeout_seconds: int = Field(
        default=service.DEFAULT_OFFLINE_TIMEOUT_SECONDS,
        ge=service.MIN_OFFLINE_TIMEOUT_SECONDS,
        le=service.MAX_OFFLINE_TIMEOUT_SECONDS,
    )


@router.get("/backend-health-settings")
def get_backend_health_settings():
    return service.get_settings(get_engine())


@router.put("/backend-health-settings")
def update_backend_health_settings(body: BackendHealthSettingsRequest):
    return service.update_settings(get_engine(), body.model_dump())
