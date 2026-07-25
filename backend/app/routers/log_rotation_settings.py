"""Log-rotation settings endpoint (chat request)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import log_rotation_settings as service
from app.db import get_engine
from app.logging_config import apply_rotation_settings

router = APIRouter()


class LogRotationSettingsRequest(BaseModel):
    max_bytes: int = Field(
        default=service.DEFAULT_MAX_BYTES,
        ge=service.MIN_MAX_BYTES,
        le=service.MAX_MAX_BYTES,
    )
    backup_count: int = Field(
        default=service.DEFAULT_BACKUP_COUNT,
        ge=service.MIN_BACKUP_COUNT,
        le=service.MAX_BACKUP_COUNT,
    )


@router.get("/log-rotation-settings")
def get_log_rotation_settings():
    return service.get_settings(get_engine())


@router.put("/log-rotation-settings")
def update_log_rotation_settings(body: LogRotationSettingsRequest):
    updated = service.update_settings(get_engine(), body.model_dump())
    apply_rotation_settings(updated["max_bytes"], updated["backup_count"])
    return updated
