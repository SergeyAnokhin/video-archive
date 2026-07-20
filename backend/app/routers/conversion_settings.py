"""Global conversion settings endpoint (user report)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import conversion_settings as service
from app.db import get_engine

router = APIRouter()


class ConversionSettingsRequest(BaseModel):
    min_size_reduction_percent: int = Field(
        default=service.DEFAULT_MIN_SIZE_REDUCTION_PERCENT,
        ge=service.MIN_MIN_SIZE_REDUCTION_PERCENT,
        le=service.MAX_MIN_SIZE_REDUCTION_PERCENT,
    )
    ffmpeg_timeout_seconds: int = Field(
        default=service.DEFAULT_FFMPEG_TIMEOUT_SECONDS,
        ge=service.MIN_FFMPEG_TIMEOUT_SECONDS,
        le=service.MAX_FFMPEG_TIMEOUT_SECONDS,
    )
    direct_write_enabled: bool = Field(default=service.DEFAULT_DIRECT_WRITE_ENABLED)


@router.get("/conversion-settings")
def get_conversion_settings():
    return service.get_settings(get_engine())


@router.put("/conversion-settings")
def update_conversion_settings(body: ConversionSettingsRequest):
    return service.update_settings(get_engine(), body.model_dump())
