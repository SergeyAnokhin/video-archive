"""Global performance settings endpoint (post-V1, user request)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import performance_settings as service
from app.db import get_engine

router = APIRouter()


class PerformanceSettingsRequest(BaseModel):
    parallel_workers: int = Field(
        default=service.DEFAULT_PARALLEL_WORKERS,
        ge=service.MIN_PARALLEL_WORKERS,
        le=service.MAX_PARALLEL_WORKERS,
    )
    eta_window_minutes: int = Field(
        default=service.DEFAULT_ETA_WINDOW_MINUTES,
        ge=service.MIN_ETA_WINDOW_MINUTES,
        le=service.MAX_ETA_WINDOW_MINUTES,
    )


@router.get("/performance-settings")
def get_performance_settings():
    return service.get_settings(get_engine())


@router.put("/performance-settings")
def update_performance_settings(body: PerformanceSettingsRequest):
    return service.update_settings(get_engine(), body.model_dump())
