"""Backup and restore endpoints (API §14, Specification §19, Backup Format).

Creating and restoring a backup both run as jobs (`backup`/`restore` job
types, `scope_type: "maintenance"`) since they touch the source's technical
folder and, for SMB, involve a network round-trip (Job Model "Job Types").
Listing and deleting a backup package are fast metadata-only operations and
stay synchronous, same as conversion-profile CRUD.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app import backup
from app.db import get_engine
from app.jobs import service
from app.source_access import get_active_source_or_404
from app.sources import get_source_access

router = APIRouter()


def _backup_not_found_error(backup_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "backup_not_found", "message": f"Backup not found: {backup_id}"}},
    )


@router.get("/backups")
def list_backups():
    engine = get_engine()
    with engine.connect() as conn:
        source = get_active_source_or_404(conn)
    access = get_source_access(source)
    return {"backups": backup.list_backups(access)}


class CreateBackupRequest(BaseModel):
    include_secrets: bool = False


@router.post("/backups")
def create_backup(body: CreateBackupRequest):
    engine = get_engine()
    with engine.connect() as conn:
        get_active_source_or_404(conn)

    return service.create_job(
        engine,
        job_type="backup",
        scope_type="maintenance",
        scope_ref=None,
        parameters={"include_secrets": body.include_secrets},
    )


class RestoreBackupRequest(BaseModel):
    backup_id: str


@router.post("/backups/restore")
def restore_backup(body: RestoreBackupRequest):
    engine = get_engine()
    with engine.connect() as conn:
        source = get_active_source_or_404(conn)
    access = get_source_access(source)
    if not any(b["id"] == body.backup_id for b in backup.list_backups(access)):
        raise _backup_not_found_error(body.backup_id)

    return service.create_job(
        engine,
        job_type="restore",
        scope_type="maintenance",
        scope_ref=body.backup_id,
        parameters={"backup_id": body.backup_id},
    )


@router.delete("/backups/{backup_id}")
def delete_backup(backup_id: str):
    engine = get_engine()
    with engine.connect() as conn:
        source = get_active_source_or_404(conn)
    access = get_source_access(source)
    if not backup.delete_backup(access, backup_id):
        raise _backup_not_found_error(backup_id)
    return {"deleted": True}
