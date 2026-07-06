from fastapi import APIRouter, Request
from sqlalchemy import text

from app.db import get_engine, get_schema_version
from app.jobs import service as jobs_service

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
