from fastapi import APIRouter, Request

from app.db import get_schema_version

router = APIRouter()


@router.get("/app/info")
def get_app_info(request: Request) -> dict:
    ffmpeg_status = request.app.state.ffmpeg_status

    return {
        "app_version": request.app.state.app_version,
        # No source is configured yet; source management arrives in Stage 2.
        "source": None,
        "database": {
            "status": "ok",
            "schema_version": get_schema_version(),
        },
        # No job queue yet; jobs arrive in Stage 3.
        "queue": {"current_job": None},
        "ffmpeg": {
            "available": ffmpeg_status.available,
            "version": ffmpeg_status.version,
            "path": ffmpeg_status.path,
        },
    }
