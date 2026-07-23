"""Raw log file listing/download (chat request): the backend runs on a
Kubernetes PVC the user has no direct disk access to, so `backend.log` and
`resource_usage.log` (see `app.resource_monitor`) are otherwise unreachable
after an OOM restart wipes the in-memory state. Lists whatever is actually
in `LOG_DIR` rather than hardcoding filenames, so rotated backups and any
future log file dropped there are downloadable with no further changes.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.logging_config import LOG_DIR

router = APIRouter()


def _resolve_log_file(filename: str) -> Path:
    # Reject anything that isn't a bare filename (no separators, no `..`)
    # before touching the filesystem, then confirm the resolved path still
    # lands inside LOG_DIR -- defense in depth against path traversal.
    if filename != Path(filename).name:
        raise HTTPException(status_code=400, detail="Invalid filename")

    log_dir = LOG_DIR.resolve()
    candidate = (log_dir / filename).resolve()
    if candidate.parent != log_dir or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Log file not found")
    return candidate


@router.get("/log-files")
def list_log_files() -> dict:
    log_dir = LOG_DIR.resolve()
    files = []
    if log_dir.is_dir():
        for entry in sorted(log_dir.iterdir()):
            if not entry.is_file():
                continue
            stat = entry.stat()
            files.append(
                {
                    "name": entry.name,
                    "size_bytes": stat.st_size,
                    "modified_at": stat.st_mtime,
                }
            )
    return {"files": files}


@router.get("/log-files/{filename}")
def download_log_file(filename: str):
    path = _resolve_log_file(filename)
    return FileResponse(path, filename=path.name, media_type="text/plain")
