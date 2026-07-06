"""Global backup settings endpoint (Settings §7, Specification §19)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from app import backup_settings as service
from app.db import get_engine

router = APIRouter()


class BackupSettingsRequest(BaseModel):
    retention_count: int = service.DEFAULT_RETENTION_COUNT


@router.get("/backup-settings")
def get_backup_settings():
    return service.get_settings(get_engine())


@router.put("/backup-settings")
def update_backup_settings(body: BackupSettingsRequest):
    return service.update_settings(get_engine(), body.model_dump())
