"""Conversion profile endpoints (API §4)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import conversion_profiles as service
from app.db import get_engine

router = APIRouter()


class ProfileRequest(BaseModel):
    name: str
    is_default: bool = False
    video_codec: str = service.DEFAULT_VIDEO_CODEC
    container: str = service.DEFAULT_CONTAINER
    max_dimension: int | None = None
    crf: int = service.DEFAULT_CRF
    drop_audio: bool = True
    hardware_accel: str = service.DEFAULT_HARDWARE_ACCEL
    preset: str = service.DEFAULT_PRESET
    extra_encoder_args: dict | None = None


def _not_found_error(profile_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "code": "conversion_profile_not_found",
                "message": f"Conversion profile not found: {profile_id}",
            }
        },
    )


@router.get("/conversion-profiles")
def list_conversion_profiles():
    return {"profiles": service.list_profiles(get_engine())}


@router.post("/conversion-profiles")
def create_conversion_profile(body: ProfileRequest):
    return service.create_profile(get_engine(), body.model_dump())


@router.put("/conversion-profiles/{profile_id}")
def update_conversion_profile(profile_id: str, body: ProfileRequest):
    profile = service.update_profile(get_engine(), profile_id, body.model_dump())
    if profile is None:
        raise _not_found_error(profile_id)
    return profile


@router.delete("/conversion-profiles/{profile_id}")
def delete_conversion_profile(profile_id: str):
    if not service.delete_profile(get_engine(), profile_id):
        raise _not_found_error(profile_id)
    return {"deleted": True}
