"""Job endpoints (API §6-7): CRUD, cancellation, restart, and the `rescan`
job trigger. Conversion/preview/tag job endpoints arrive with their own
stages.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from app.db import get_engine
from app.jobs import service
from app.source_access import get_active_source_or_404

router = APIRouter()


def _not_found_error(job_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "job_not_found", "message": f"Job not found: {job_id}"}},
    )


def _conflict_error(exc: service.JobConflictError) -> HTTPException:
    return HTTPException(status_code=409, detail={"error": {"code": exc.code, "message": exc.message}})


@router.get("/jobs")
def list_jobs(
    status: str | None = Query(default=None),
    job_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    engine = get_engine()
    jobs = service.list_jobs(engine, status=status, job_type=job_type, limit=limit, offset=offset)
    return {"jobs": jobs}


@router.get("/jobs/{job_id}")
def get_job(job_id: str):
    job = service.get_job(get_engine(), job_id)
    if job is None:
        raise _not_found_error(job_id)
    return job


@router.get("/jobs/{job_id}/items")
def get_job_items(job_id: str):
    engine = get_engine()
    if service.get_job(engine, job_id) is None:
        raise _not_found_error(job_id)
    return {"items": service.get_job_items(engine, job_id)}


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    engine = get_engine()
    try:
        job = service.cancel_job(engine, job_id)
    except service.JobConflictError as exc:
        raise _conflict_error(exc)
    if job is None:
        raise _not_found_error(job_id)
    return job


@router.post("/jobs/{job_id}/restart")
def restart_job(job_id: str):
    engine = get_engine()
    try:
        job = service.restart_job(engine, job_id)
    except service.JobConflictError as exc:
        raise _conflict_error(exc)
    if job is None:
        raise _not_found_error(job_id)
    return job


@router.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    engine = get_engine()
    try:
        deleted = service.delete_job(engine, job_id)
    except service.JobConflictError as exc:
        raise _conflict_error(exc)
    if not deleted:
        raise _not_found_error(job_id)
    return {"deleted": True}


@router.delete("/jobs")
def delete_finished_jobs():
    count = service.delete_finished_jobs(get_engine())
    return {"deleted_count": count}


class RescanDirectoryRequest(BaseModel):
    path: str = ""


@router.post("/jobs/rescan-directory")
def rescan_directory(body: RescanDirectoryRequest):
    engine = get_engine()
    with engine.connect() as conn:
        source = get_active_source_or_404(conn)
        if body.path:
            dir_row = conn.execute(
                text("SELECT id FROM directories WHERE source_id = :sid AND relative_path = :path"),
                {"sid": source.id, "path": body.path},
            ).fetchone()
            if dir_row is None:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "error": {
                            "code": "directory_not_found",
                            "message": f"Directory not found: {body.path}",
                        }
                    },
                )

    return service.create_job(
        engine,
        job_type="rescan",
        scope_type="directory" if body.path else "source",
        scope_ref=body.path or None,
        parameters={"path": body.path},
    )
