"""Preview layout preset endpoints (API §5): CRUD over the preset gallery
plus a stateless live-preview endpoint used by the Preview Settings page's
construction-set editor.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import preview_layouts as service
from app.db import get_engine

router = APIRouter()


class EnlargedTileInput(BaseModel):
    row: int
    col: int
    span: int


class PresetRequest(BaseModel):
    name: str
    grid_rows: int
    grid_cols: int
    timeline_flow: str = "row"
    identity_diversity_enabled: bool = True
    layout_definition: list[EnlargedTileInput] = []
    is_default: bool = False


class LayoutPreviewRequest(BaseModel):
    grid_rows: int
    grid_cols: int
    layout_definition: list[EnlargedTileInput] = []
    timeline_flow: str = "row"
    identity_diversity_enabled: bool = True


def _not_found_error(preset_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "code": "preview_layout_preset_not_found",
                "message": f"Preview layout preset not found: {preset_id}",
            }
        },
    )


def _protected_error(exc: service.PresetProtectedError) -> HTTPException:
    return HTTPException(status_code=409, detail={"error": {"code": "preset_protected", "message": str(exc)}})


def _validation_error(exc: service.LayoutValidationError) -> HTTPException:
    return HTTPException(status_code=400, detail={"error": {"code": "invalid_layout", "message": str(exc)}})


@router.get("/preview-layouts")
def list_preview_layouts():
    return {"presets": service.list_presets(get_engine())}


@router.post("/preview-layouts")
def create_preview_layout(body: PresetRequest):
    data = body.model_dump()
    try:
        return service.create_preset(get_engine(), data)
    except service.LayoutValidationError as exc:
        raise _validation_error(exc)


@router.put("/preview-layouts/{preset_id}")
def update_preview_layout(preset_id: str, body: PresetRequest):
    data = body.model_dump()
    try:
        preset = service.update_preset(get_engine(), preset_id, data)
    except service.LayoutValidationError as exc:
        raise _validation_error(exc)
    except service.PresetProtectedError as exc:
        raise _protected_error(exc)
    if preset is None:
        raise _not_found_error(preset_id)
    return preset


@router.delete("/preview-layouts/{preset_id}")
def delete_preview_layout(preset_id: str):
    try:
        deleted = service.delete_preset(get_engine(), preset_id)
    except service.PresetProtectedError as exc:
        raise _protected_error(exc)
    if not deleted:
        raise _not_found_error(preset_id)
    return {"deleted": True}


@router.post("/preview-layouts/preview")
def preview_layout_geometry(body: LayoutPreviewRequest):
    enlarged = [t.model_dump() for t in body.layout_definition]
    try:
        tiles = service.compute_layout_tiles(body.grid_rows, body.grid_cols, enlarged)
    except service.LayoutValidationError as exc:
        raise _validation_error(exc)
    return {
        "grid_rows": body.grid_rows,
        "grid_cols": body.grid_cols,
        "tiles": tiles,
        "frame_count": len(tiles),
    }
