import os

from fastapi import APIRouter, Request
from sqlalchemy import text

from app.db import get_engine, get_schema_version
from app.jobs import service as jobs_service
from app.network_info import get_lan_addresses

router = APIRouter()


def _active_source_summary() -> dict | None:
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()
    if row is None:
        return None
    return {
        "id": row.id,
        "name": row.name,
        "protocol": row.protocol,
        "root_path": row.root_path,
        "last_scan_at": row.last_scan_at,
    }


@router.get("/app/info")
def get_app_info(request: Request) -> dict:
    ffmpeg_status = request.app.state.ffmpeg_status

    return {
        "app_version": request.app.state.app_version,
        "source": _active_source_summary(),
        "database": {
            "status": "ok",
            "schema_version": get_schema_version(),
        },
        "queue": {"current_job": jobs_service.get_current_job_summary(get_engine())},
        "ffmpeg": {
            "available": ffmpeg_status.available,
            "version": ffmpeg_status.version,
            "path": ffmpeg_status.path,
        },
    }


@router.get("/app/network-info")
def get_network_info(request: Request) -> dict:
    # The backend port as the request itself arrived on -- correct even when
    # reached through the Vite dev-server proxy (which rewrites the Host
    # header to its target), so it stays right without needing its own env
    # var. The frontend port has no such signal to read from, so it falls
    # back to the same `PORT` env var (default 5173) `vite.config.ts` uses.
    backend_port = request.url.port or 8000
    frontend_port = int(os.environ.get("PORT", 5173))

    return {
        "lan_addresses": get_lan_addresses(),
        "frontend_port": frontend_port,
        "backend_port": backend_port,
    }
