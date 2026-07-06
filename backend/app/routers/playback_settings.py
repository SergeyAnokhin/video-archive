"""Global playback settings endpoint (Settings §4, Specification §11.5)."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import playback_settings as service
from app.db import get_engine

router = APIRouter()


class PlaybackSettingsRequest(BaseModel):
    mode: Literal["stream", "direct_link"] = service.DEFAULT_MODE


@router.get("/playback-settings")
def get_playback_settings():
    return service.get_settings(get_engine())


@router.put("/playback-settings")
def update_playback_settings(body: PlaybackSettingsRequest):
    return service.update_settings(get_engine(), body.model_dump())
