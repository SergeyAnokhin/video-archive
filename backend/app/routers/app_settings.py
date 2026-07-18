"""Application-settings export/import endpoints: a bundle of every app-wide
setting not tied to a specific source or provider credentials. See
`app/app_settings.py` for what's included/excluded and the import logic.
"""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel

from app import app_settings as service
from app.db import get_engine

router = APIRouter()


class AppSettingsImportRequest(BaseModel):
    tags: dict | None = None
    conversion_profiles: list[dict] | None = None
    preview_layouts: list[dict] | None = None
    conversion_settings: dict | None = None
    preview_settings: dict | None = None
    playback_settings: dict | None = None
    tagging_settings: dict | None = None
    backup_settings: dict | None = None
    interface_settings: dict | None = None
    performance_settings: dict | None = None


@router.get("/settings/app-settings/export")
def export_app_settings():
    payload = service.build_export_payload(get_engine())
    return Response(
        content=json.dumps(payload, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=app-settings-export.json"},
    )


@router.post("/settings/app-settings/import")
def import_app_settings(body: AppSettingsImportRequest):
    return service.apply_import(get_engine(), body.model_dump())
