"""Global interface settings endpoint (Settings §9): UI language + theme
preset."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import interface_settings as service
from app.db import get_engine

router = APIRouter()


class InterfaceSettingsRequest(BaseModel):
    language: Literal["en", "ru"] = service.DEFAULT_LANGUAGE
    theme_preset: Literal["strict", "playful", "casino"] = service.DEFAULT_THEME_PRESET


@router.get("/interface-settings")
def get_interface_settings():
    return service.get_settings(get_engine())


@router.put("/interface-settings")
def update_interface_settings(body: InterfaceSettingsRequest):
    return service.update_settings(get_engine(), body.model_dump())
