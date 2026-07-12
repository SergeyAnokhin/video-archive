"""Global tagging settings endpoint (Settings §5). Follows the same
dedicated-endpoint convention as `app/routers/preview_settings.py` rather
than the generic `/api/settings` placeholder (see `docs/code-map.md`
"Convention for future settings groups").

Also exposes a stateless preview endpoint (`POST /tagging-settings/preview`)
so Settings → Tagging can show exactly what a given (possibly unsaved)
sample-frame-count/collage/resolution combination would send to the AI
provider, rendered from a real video rather than a synthetic mockup.
"""

from __future__ import annotations

import base64
from io import BytesIO

from fastapi import APIRouter, HTTPException
from PIL import Image
from pydantic import BaseModel
from sqlalchemy import text

from app import tagging
from app import tagging_settings as service
from app.db import get_engine
from app.sources import get_source_access

router = APIRouter()


class TaggingSettingsRequest(BaseModel):
    sample_frame_count: int = service.DEFAULT_SAMPLE_FRAME_COUNT
    combine_into_collage: bool = service.DEFAULT_COMBINE_INTO_COLLAGE
    top_tag_count: int = service.DEFAULT_TOP_TAG_COUNT
    image_resolution: int = service.DEFAULT_IMAGE_RESOLUTION


class TaggingPreviewRequest(BaseModel):
    file_id: str
    sample_frame_count: int
    combine_into_collage: bool
    image_resolution: int


@router.get("/tagging-settings")
def get_tagging_settings():
    return service.get_settings(get_engine())


@router.put("/tagging-settings")
def update_tagging_settings(body: TaggingSettingsRequest):
    return service.update_settings(get_engine(), body.model_dump())


@router.post("/tagging-settings/preview")
def preview_tagging_images(body: TaggingPreviewRequest):
    with get_engine().connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT f.relative_path, s.*
                FROM files f
                JOIN sources s ON s.id = f.source_id
                WHERE f.id = :id AND s.is_active = 1
                """
            ),
            {"id": body.file_id},
        ).fetchone()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "file_not_found", "message": f"File not found: {body.file_id}"}},
        )

    access = get_source_access(row)
    try:
        with access.local_copy(row.relative_path) as video_path:
            images = tagging.build_tagging_images(
                video_path, body.sample_frame_count, body.combine_into_collage, body.image_resolution
            )
    except tagging.TaggingInputError as exc:
        raise HTTPException(
            status_code=400, detail={"error": {"code": "tagging_preview_failed", "message": str(exc)}}
        )

    result = []
    for image_bytes in images:
        width, height = Image.open(BytesIO(image_bytes)).size
        data_url = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")
        result.append({"data_url": data_url, "width": width, "height": height})

    return {"images": result, "combine_into_collage": body.combine_into_collage}
