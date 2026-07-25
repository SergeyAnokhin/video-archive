"""CPU/memory/network history for the Settings -> Performance chart
(chat request 2026-07-25). See `app/resource_monitor_history.py`."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter

from app import resource_monitor_history as service
from app.db import get_engine

router = APIRouter()


@router.get("/resource-monitor-history")
def get_resource_monitor_history(range: Literal["30m", "4h", "12h", "24h"] = "24h"):
    return service.get_history(get_engine(), service.ALLOWED_RANGE_SECONDS[range])
