"""Global interface settings endpoint (Settings §9): UI language, theme
preset, and the two preview-stylization profiles."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, create_model

from app import interface_settings as service
from app.db import get_engine

router = APIRouter()

_profile_fields = {
    f"profile_{profile}_{field}": (
        int,
        Field(
            default=(service.DEFAULT_PROFILE_A if profile == "a" else service.DEFAULT_PROFILE_B)[field],
            ge=service.PROFILE_RANGES[field][0],
            le=service.PROFILE_RANGES[field][1],
        ),
    )
    for profile in ("a", "b")
    for field in service.PROFILE_FIELDS
}

_search_limit_fields = {
    field: (
        int,
        Field(
            default=service.DEFAULT_SEARCH_LIMITS[field],
            ge=service.SEARCH_LIMIT_RANGE[0],
            le=service.SEARCH_LIMIT_RANGE[1],
        ),
    )
    for field in service.SEARCH_LIMIT_FIELDS
}

InterfaceSettingsRequest = create_model(
    "InterfaceSettingsRequest",
    __base__=BaseModel,
    language=(Literal["en", "ru"], service.DEFAULT_LANGUAGE),
    theme_preset=(
        Literal["strict", "playful", "casino", "neon", "toxic", "cyber", "vivid", "mono"],
        service.DEFAULT_THEME_PRESET,
    ),
    **_profile_fields,
    **_search_limit_fields,
)


@router.get("/interface-settings")
def get_interface_settings():
    return service.get_settings(get_engine())


@router.put("/interface-settings")
def update_interface_settings(body: InterfaceSettingsRequest):  # type: ignore[valid-type]
    return service.update_settings(get_engine(), body.model_dump())
