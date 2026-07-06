"""Global tagging settings endpoint (Settings §5). Follows the same
dedicated-endpoint convention as `app/routers/preview_settings.py` rather
than the generic `/api/settings` placeholder (see `docs/code-map.md`
"Convention for future settings groups").
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import tagging_settings as service
from app.db import get_engine

router = APIRouter()


class TaggingSettingsRequest(BaseModel):
    sample_frame_count: int = service.DEFAULT_SAMPLE_FRAME_COUNT
    combine_into_collage: bool = service.DEFAULT_COMBINE_INTO_COLLAGE
    top_tag_count: int = service.DEFAULT_TOP_TAG_COUNT
    default_provider: str | None = None
    default_vision_model: str | None = None


@router.get("/tagging-settings")
def get_tagging_settings():
    return service.get_settings(get_engine())


@router.put("/tagging-settings")
def update_tagging_settings(body: TaggingSettingsRequest):
    return service.update_settings(get_engine(), body.model_dump())
