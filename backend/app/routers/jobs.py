"""Job endpoints (API §6-8): CRUD, cancellation, restart, the `rescan` job
trigger, and the `convert` job triggers (directory and file scope, including
the file-scope variant-comparison sweep). Preview/tag job endpoints arrive
with their own stages.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from app import conversion_profiles, preview_layouts, provider_configs, tagging_settings, tags as tags_service
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


def _profile_not_found_error(profile_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "code": "conversion_profile_not_found",
                "message": f"Conversion profile not found: {profile_id}",
            }
        },
    )


class ConvertDirectoryRequest(BaseModel):
    path: str = ""
    profile_id: str
    mode: Literal["production", "test"] = "production"
    skip_processed: bool = True


@router.post("/jobs/convert-directory")
def convert_directory(body: ConvertDirectoryRequest):
    engine = get_engine()
    if conversion_profiles.get_profile(engine, body.profile_id) is None:
        raise _profile_not_found_error(body.profile_id)

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
        job_type="convert",
        scope_type="directory" if body.path else "source",
        scope_ref=body.path or None,
        parameters={
            "path": body.path,
            "profile_id": body.profile_id,
            "mode": body.mode,
            "skip_processed": body.skip_processed,
        },
    )


class VariantOverride(BaseModel):
    max_dimension: int | None = None
    crf: int | None = None
    video_codec: str | None = None


class ConvertFileRequest(BaseModel):
    file_id: str
    profile_id: str
    mode: Literal["production", "test"] = "production"
    skip_processed: bool = True
    variants: list[VariantOverride] | None = None


@router.post("/jobs/convert-file")
def convert_file(body: ConvertFileRequest):
    engine = get_engine()
    if conversion_profiles.get_profile(engine, body.profile_id) is None:
        raise _profile_not_found_error(body.profile_id)

    if body.variants and body.mode != "test":
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "variants_require_test_mode",
                    "message": "Variant comparison is only allowed with mode: test.",
                }
            },
        )

    with engine.connect() as conn:
        get_active_source_or_404(conn)
        file_row = conn.execute(text("SELECT id FROM files WHERE id = :id"), {"id": body.file_id}).fetchone()
        if file_row is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "file_not_found", "message": f"File not found: {body.file_id}"}},
            )

    return service.create_job(
        engine,
        job_type="convert",
        scope_type="file",
        scope_ref=body.file_id,
        parameters={
            "file_id": body.file_id,
            "profile_id": body.profile_id,
            "mode": body.mode,
            "skip_processed": body.skip_processed,
            "variants": [v.model_dump(exclude_none=True) for v in body.variants] if body.variants else None,
        },
    )


def _preset_not_found_error(preset_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={
            "error": {
                "code": "preview_layout_preset_not_found",
                "message": f"Preview layout preset not found: {preset_id}",
            }
        },
    )


class PreviewDirectoryRequest(BaseModel):
    path: str = ""
    layout_preset_id: str | None = None
    skip_processed: bool = True


@router.post("/jobs/preview-directory")
def preview_directory(body: PreviewDirectoryRequest):
    engine = get_engine()
    if body.layout_preset_id and preview_layouts.get_preset(engine, body.layout_preset_id) is None:
        raise _preset_not_found_error(body.layout_preset_id)

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
        job_type="preview",
        scope_type="directory" if body.path else "source",
        scope_ref=body.path or None,
        parameters={
            "path": body.path,
            "layout_preset_id": body.layout_preset_id,
            "skip_processed": body.skip_processed,
        },
    )


class PreviewFileRequest(BaseModel):
    file_id: str
    layout_preset_id: str | None = None


@router.post("/jobs/preview-file")
def preview_file(body: PreviewFileRequest):
    engine = get_engine()
    if body.layout_preset_id and preview_layouts.get_preset(engine, body.layout_preset_id) is None:
        raise _preset_not_found_error(body.layout_preset_id)

    with engine.connect() as conn:
        get_active_source_or_404(conn)
        file_row = conn.execute(text("SELECT id FROM files WHERE id = :id"), {"id": body.file_id}).fetchone()
        if file_row is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "file_not_found", "message": f"File not found: {body.file_id}"}},
            )

    return service.create_job(
        engine,
        job_type="preview",
        scope_type="file",
        scope_ref=body.file_id,
        parameters={"file_id": body.file_id, "layout_preset_id": body.layout_preset_id},
    )


def _resolve_tagging_provider(engine) -> str:
    """Picks the provider a tag job should use: the configured default if
    it's enabled, otherwise the first enabled provider. Raises 400 if none
    is enabled (Specification §18 — provider setup is a settings-time
    concern, not a per-job parameter)."""
    settings = tagging_settings.get_settings(engine)
    default_name = settings.get("default_provider")
    if default_name:
        config = provider_configs.get_provider(engine, default_name)
        if config and config["enabled"]:
            return default_name

    for config in provider_configs.list_providers(engine):
        if config["enabled"]:
            return config["provider_name"]

    raise HTTPException(
        status_code=400,
        detail={
            "error": {
                "code": "no_provider_configured",
                "message": "No AI provider is enabled. Configure one in Settings first.",
            }
        },
    )


def _require_tag_vocabulary(engine) -> None:
    if not tags_service.list_tags(engine, active_only=True):
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "empty_tag_vocabulary",
                    "message": "Add at least one active tag in settings before tagging.",
                }
            },
        )


class TagDirectoryRequest(BaseModel):
    path: str = ""
    skip_processed: bool = True


@router.post("/jobs/tag-directory")
def tag_directory(body: TagDirectoryRequest):
    engine = get_engine()
    provider_name = _resolve_tagging_provider(engine)
    _require_tag_vocabulary(engine)

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
        job_type="tag",
        scope_type="directory" if body.path else "source",
        scope_ref=body.path or None,
        parameters={"path": body.path, "skip_processed": body.skip_processed, "provider_name": provider_name},
    )


class TagFileRequest(BaseModel):
    file_id: str


@router.post("/jobs/tag-file")
def tag_file(body: TagFileRequest):
    engine = get_engine()
    provider_name = _resolve_tagging_provider(engine)
    _require_tag_vocabulary(engine)

    with engine.connect() as conn:
        get_active_source_or_404(conn)
        file_row = conn.execute(text("SELECT id FROM files WHERE id = :id"), {"id": body.file_id}).fetchone()
        if file_row is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "file_not_found", "message": f"File not found: {body.file_id}"}},
            )

    return service.create_job(
        engine,
        job_type="tag",
        scope_type="file",
        scope_ref=body.file_id,
        parameters={"file_id": body.file_id, "provider_name": provider_name},
    )
