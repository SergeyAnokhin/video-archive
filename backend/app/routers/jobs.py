"""Job endpoints (API §6-9): CRUD, cancellation, pause/resume (post-V1 user
request — see `app/jobs/service.py`'s `PAUSABLE_JOB_TYPES`), restart, and the
trigger endpoints for every job type — `rescan`, `convert` (directory/file
scope, including the file-scope variant-comparison sweep), `preview`, `tag`,
and the Stage 8 maintenance actions `cleanup`/`optimize_db`. Backup/restore
triggers live in `app/routers/backups.py` instead, alongside backup
listing/deletion.
"""

from __future__ import annotations

import json
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from app import batch_submissions, conversion_profiles, conversion_script, preview_layouts, provider_entries, tags as tags_service
from app.db import get_engine
from app.jobs import service
from app.source_access import get_active_source_or_404
from app.sources import get_source_access

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


@router.get("/jobs/batch-submissions")
def list_active_batch_submissions():
    """Batch tagging submissions still `polling` (Gemini/Mistral only --
    user request "a button showing what batch jobs are currently in
    progress"). Registered ahead of `GET /jobs/{job_id}` below so it isn't
    shadowed by that path parameter. `items_json`/`tag_ids_json` are
    internal resume-plumbing, not shaped for a UI -- only `item_count` (a
    plain length) is surfaced instead."""
    submissions = batch_submissions.list_active(get_engine())
    return {
        "submissions": [
            {
                "id": row["id"],
                "job_id": row["job_id"],
                "provider_type": row["provider_type"],
                "model_name": row["model_name"],
                "item_count": len(json.loads(row["items_json"])),
                "status": row["status"],
                "created_at": row["created_at"],
            }
            for row in submissions
        ]
    }


@router.delete("/jobs/batch-submissions/{submission_id}")
def forget_batch_submission(submission_id: str):
    """"Forget locally" (user request) -- stops this app from polling the
    submission. Deliberately does not cancel it at the provider; its
    owning `tag` job is left to resolve on its own next poll, which will
    then see the submission gone and fall back to per-file tagging."""
    if not batch_submissions.forget(get_engine(), submission_id):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "batch_submission_not_found", "message": f"Unknown or already-resolved batch submission: {submission_id}"}},
        )
    return {"forgotten": True}


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


@router.post("/jobs/{job_id}/pause")
def pause_job(job_id: str):
    engine = get_engine()
    try:
        job = service.pause_job(engine, job_id)
    except service.JobConflictError as exc:
        raise _conflict_error(exc)
    if job is None:
        raise _not_found_error(job_id)
    return job


@router.post("/jobs/{job_id}/resume")
def resume_job(job_id: str):
    engine = get_engine()
    try:
        job = service.resume_job(engine, job_id)
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
    with_media_info: bool = False


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
        job_type="rescan_with_media_info" if body.with_media_info else "rescan",
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


class ScriptOverrides(BaseModel):
    video_codec: str | None = None
    crf: int | None = None
    max_dimension: int | None = None
    drop_audio: bool | None = None
    hardware_accel: str | None = None
    preset: str | None = None
    extra_encoder_args: list[str] | None = None


class GenerateConversionScriptRequest(BaseModel):
    path: str = ""
    profile_id: str
    overrides: ScriptOverrides | None = None


@router.post("/jobs/generate-conversion-script")
def generate_conversion_script(body: GenerateConversionScriptRequest):
    """Synchronous, read-only: builds a standalone PowerShell script text for
    the user to copy and run elsewhere (user request) -- unlike every other
    endpoint in this router, this never creates a job or touches any file."""
    engine = get_engine()
    profile = conversion_profiles.get_profile(engine, body.profile_id)
    if profile is None:
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

    access = get_source_access(source)
    relative_paths = conversion_script.enumerate_directory_files(engine, source.id, body.path)
    overrides = body.overrides.model_dump(exclude_none=True) if body.overrides else None
    script, container = conversion_script.generate_powershell_script(
        profile=profile,
        overrides=overrides,
        root_hint=access.direct_path(""),
        relative_paths=relative_paths,
    )
    return {"script": script, "file_count": len(relative_paths), "container": container}


class VariantOverride(BaseModel):
    max_dimension: int | None = None
    crf: int | None = None
    video_codec: str | None = None
    preset: str | None = None


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


def _require_enabled_provider(engine) -> None:
    """Raises 400 if no provider entry is enabled (Specification §18 —
    provider setup is a settings-time concern, not a per-job parameter).
    Which entry actually runs each file is resolved live by the worker via
    the priority-ordered fallback chain (`app/providers/registry.py`), not
    frozen here at job-creation time."""
    if not any(entry["enabled"] for entry in provider_entries.list_entries(engine)):
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
    _require_enabled_provider(engine)
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
        parameters={"path": body.path, "skip_processed": body.skip_processed},
    )


class TagFileRequest(BaseModel):
    file_id: str


@router.post("/jobs/tag-file")
def tag_file(body: TagFileRequest):
    engine = get_engine()
    _require_enabled_provider(engine)
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
        parameters={"file_id": body.file_id},
    )


@router.post("/jobs/cleanup-stale-records")
def cleanup_stale_records():
    engine = get_engine()
    with engine.connect() as conn:
        get_active_source_or_404(conn)

    return service.create_job(engine, job_type="cleanup", scope_type="maintenance", scope_ref=None, parameters={})


@router.post("/jobs/optimize-database")
def optimize_database():
    engine = get_engine()
    with engine.connect() as conn:
        get_active_source_or_404(conn)

    return service.create_job(
        engine, job_type="optimize_db", scope_type="maintenance", scope_ref=None, parameters={}
    )
