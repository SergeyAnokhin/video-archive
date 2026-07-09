"""Global preview settings endpoint (Settings §3, Specification §9.2, §10)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import preview_settings as service
from app.db import get_engine

router = APIRouter()


class PreviewSettingsRequest(BaseModel):
    aspect_ratio: Literal["standard", "phone-portrait", "phone-landscape", "ultra-wide", "custom"] = (
        service.DEFAULT_ASPECT_RATIO
    )
    aspect_ratio_custom_width: int | None = None
    aspect_ratio_custom_height: int | None = None
    folder_preview_frame_count: int = service.DEFAULT_FOLDER_PREVIEW_FRAME_COUNT
    gif_max_width: int = service.DEFAULT_GIF_MAX_WIDTH
    gif_colors: int = service.DEFAULT_GIF_COLORS
    animated_source_mode: Literal["frame", "clip"] = service.DEFAULT_ANIMATED_SOURCE_MODE
    animated_segment_seconds: float = service.DEFAULT_ANIMATED_SEGMENT_SECONDS
    animated_transition: Literal["cut", "crossfade"] = service.DEFAULT_ANIMATED_TRANSITION


@router.get("/preview-settings")
def get_preview_settings():
    return service.get_settings(get_engine())


@router.put("/preview-settings")
def update_preview_settings(body: PreviewSettingsRequest):
    return service.update_settings(get_engine(), body.model_dump())
