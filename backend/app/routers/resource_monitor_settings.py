"""Resource-usage monitoring settings endpoint (chat request)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import resource_monitor_settings as service
from app.db import get_engine

router = APIRouter()


class ResourceMonitorSettingsRequest(BaseModel):
    enabled: bool = Field(default=service.DEFAULT_ENABLED)
    interval_seconds: int = Field(
        default=service.DEFAULT_INTERVAL_SECONDS,
        ge=service.MIN_INTERVAL_SECONDS,
        le=service.MAX_INTERVAL_SECONDS,
    )


@router.get("/resource-monitor-settings")
def get_resource_monitor_settings():
    return service.get_settings(get_engine())


@router.put("/resource-monitor-settings")
def update_resource_monitor_settings(body: ResourceMonitorSettingsRequest):
    return service.update_settings(get_engine(), body.model_dump())
