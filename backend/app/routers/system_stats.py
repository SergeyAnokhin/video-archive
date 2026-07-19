import time

import psutil
from fastapi import APIRouter

from app.sources import smb_stats

router = APIRouter()

_process = psutil.Process()
# First call always returns 0.0 -- prime it at import time so the first real
# request already reflects usage since process start, not since the request.
_process.cpu_percent(interval=None)
# psutil reports a multi-threaded process's CPU time relative to a single
# core (so it can exceed 100% on a multi-core box) -- divide by core count to
# get a friendly 0-100% share of total system CPU for the frontend gauge.
_CPU_COUNT = psutil.cpu_count() or 1


@router.get("/system/stats")
def get_system_stats() -> dict:
    memory = _process.memory_info()
    return {
        "cpu_percent": _process.cpu_percent(interval=None) / _CPU_COUNT,
        "memory_rss_bytes": memory.rss,
        "memory_percent": _process.memory_percent(),
        "smb_bytes_read_total": smb_stats.get_total_bytes_read(),
        "timestamp": time.time(),
    }
