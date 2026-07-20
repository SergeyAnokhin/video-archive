"""Immediate folder contents endpoint (API §3, §9, UI Screens §1)."""

from __future__ import annotations

import logging
from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text

from app import directory_ops, orphan_previews
from app.db import get_engine
from app.media import compute_variant_tags, file_row_to_dict, folder_gif_relative_path, resolve_variant_preview_flags
from app.source_access import get_active_source_or_404
from app.sources import get_source_access
from app.status import compute_directory_status
from app.tags import list_top_tags_for_files, top_tags_for_directory_subtree

logger = logging.getLogger(__name__)

router = APIRouter()

# HTTP status per app/directory_ops.py error code.
_DIR_OP_STATUS = {
    "directory_not_found": 404,
    "invalid_name": 400,
    "destination_collision": 409,
    "directory_not_empty": 400,
}


def _dir_op_http_error(err: directory_ops.DirectoryOperationError) -> HTTPException:
    return HTTPException(
        status_code=_DIR_OP_STATUS[err.code],
        detail={"error": {"code": err.code, "message": err.message}},
    )


@router.get("/directories/children")
def get_directory_children(
    path: str = Query(default=""),
    include_status: bool = Query(default=False),
    include_top_tags: bool = Query(default=False),
):
    engine = get_engine()
    with engine.connect() as conn:
        source = get_active_source_or_404(conn)

        directory_row = conn.execute(
            text("SELECT id FROM directories WHERE source_id = :sid AND relative_path = :path"),
            {"sid": source.id, "path": path},
        ).fetchone()
        if directory_row is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "directory_not_found", "message": f"Directory not found: {path}"}},
            )

        subdir_rows = conn.execute(
            text(
                "SELECT relative_path, name, has_folder_preview, is_favorite FROM directories "
                "WHERE source_id = :sid AND parent_relative_path = :path "
                "ORDER BY name COLLATE NOCASE"
            ),
            {"sid": source.id, "path": path},
        ).all()

        directories = []
        for row in subdir_rows:
            entry = {
                "path": row.relative_path,
                "name": row.name,
                "is_favorite": bool(row.is_favorite),
                "has_folder_preview": bool(row.has_folder_preview),
            }
            if include_status:
                entry["status"] = compute_directory_status(conn, source.id, row.relative_path)
            if include_top_tags:
                entry["top_tags"] = top_tags_for_directory_subtree(conn, source.id, row.relative_path)
            directories.append(entry)

        file_rows = conn.execute(
            text(
                """
                SELECT id, relative_path, file_name, extension, size_bytes, modified_at, is_video_supported,
                       is_image_supported, has_preview_asset, converted_at, tagged_at, duration_seconds
                FROM files
                WHERE directory_id = :dir_id AND (is_video_supported = 1 OR is_image_supported = 1)
                ORDER BY file_name COLLATE NOCASE
                """
            ),
            {"dir_id": directory_row.id},
        ).all()
        files = [file_row_to_dict(row, duration_seconds=row.duration_seconds) for row in file_rows]
        variant_tags = compute_variant_tags([(row.id, row.relative_path) for row in file_rows])
        ai_tags = list_top_tags_for_files(engine, [row.id for row in file_rows])
        preview_flags = resolve_variant_preview_flags(
            [(row.id, directory_row.id, row.file_name, row.has_preview_asset) for row in file_rows]
        )
        for entry in files:
            entry["variant_tags"] = variant_tags.get(entry["id"], [])
            entry["ai_tags"] = ai_tags.get(entry["id"], [])
            entry["has_preview_asset"] = preview_flags.get(entry["id"], entry["has_preview_asset"])

    return {"path": path, "directories": directories, "files": files}


@router.get("/directories/search")
def search_directories(
    q: str = Query(min_length=1),
    limit: int = Query(default=20, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """Directory-name substring search (scoped library search, user request):
    matches folders whose own name contains `q`, across the whole source."""
    engine = get_engine()
    with engine.connect() as conn:
        source = get_active_source_or_404(conn)
        rows = conn.execute(
            text(
                "SELECT relative_path, name, has_folder_preview, is_favorite FROM directories "
                "WHERE source_id = :sid AND relative_path != '' AND LOWER(name) LIKE :q "
                "ORDER BY relative_path COLLATE NOCASE LIMIT :limit OFFSET :offset"
            ),
            {"sid": source.id, "q": f"%{q.strip().lower()}%", "limit": limit, "offset": offset},
        ).all()

    return {
        "directories": [
            {
                "path": row.relative_path,
                "name": row.name,
                "is_favorite": bool(row.is_favorite),
                "has_folder_preview": bool(row.has_folder_preview),
            }
            for row in rows
        ]
    }


class CreateDirectoryRequest(BaseModel):
    parent_path: str = ""
    name: str


@router.post("/directories")
def create_directory(body: CreateDirectoryRequest):
    try:
        row = directory_ops.create_directory(get_engine(), body.parent_path, body.name)
    except directory_ops.DirectoryOperationError as err:
        raise _dir_op_http_error(err)
    return {"path": row.relative_path, "name": row.name}


@router.delete("/directories")
def delete_directory(path: str = Query(default="")):
    try:
        directory_ops.delete_directory(get_engine(), path)
    except directory_ops.DirectoryOperationError as err:
        raise _dir_op_http_error(err)
    return {"deleted": True}


class SetFavoriteDirectoryRequest(BaseModel):
    path: str
    favorite: bool


@router.put("/directories/favorite")
def set_favorite_directory(body: SetFavoriteDirectoryRequest):
    try:
        row = directory_ops.set_favorite(get_engine(), body.path, body.favorite)
    except directory_ops.DirectoryOperationError as err:
        raise _dir_op_http_error(err)
    return {"path": row.relative_path, "name": row.name, "is_favorite": bool(row.is_favorite)}


@router.get("/directories/favorites")
def get_favorite_directories():
    return {"favorites": directory_ops.list_favorites(get_engine())}


def _directory_not_found_error(path: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "directory_not_found", "message": f"Directory not found: {path}"}},
    )


def _get_directory_or_404(conn, source_id: str, path: str):
    row = conn.execute(
        text("SELECT id FROM directories WHERE source_id = :sid AND relative_path = :path"),
        {"sid": source_id, "path": path},
    ).fetchone()
    if row is None:
        raise _directory_not_found_error(path)
    return row


@router.get("/directories/orphaned-previews")
def get_orphaned_previews(path: str = Query(default="")):
    """Dry-run for the "delete orphaned previews" action (user request):
    counts and samples `.jpg` collages in this directory that no known video
    row references, without deleting anything."""
    engine = get_engine()
    with engine.connect() as conn:
        source = get_active_source_or_404(conn)
        directory_row = _get_directory_or_404(conn, source.id, path)

    access = get_source_access(source)
    orphans = orphan_previews.find_orphaned_previews(engine, access, directory_row.id, path)
    return {
        "count": len(orphans),
        "sample": [PurePosixPath(rel_path).name for rel_path in orphans[:10]],
    }


class DeleteOrphanedPreviewsRequest(BaseModel):
    path: str = ""


@router.post("/directories/orphaned-previews/delete")
def delete_orphaned_previews(body: DeleteOrphanedPreviewsRequest):
    """Recomputes the orphan list server-side (rather than trusting a
    client-supplied file list from an earlier dry-run) and deletes each one,
    tolerating a single file's removal failure so it doesn't abort the rest
    of the batch."""
    engine = get_engine()
    with engine.connect() as conn:
        source = get_active_source_or_404(conn)
        directory_row = _get_directory_or_404(conn, source.id, body.path)

    access = get_source_access(source)
    orphans = orphan_previews.find_orphaned_previews(engine, access, directory_row.id, body.path)

    deleted_count = 0
    for rel_path in orphans:
        try:
            access.remote_remove(rel_path)
            deleted_count += 1
        except Exception as exc:  # noqa: BLE001 - one file's failure must not abort the batch
            logger.warning("Failed to delete orphaned preview %s: %s", rel_path, exc)

    return {"deleted_count": deleted_count}


@router.get("/directories/preview.gif")
def get_directory_preview_gif(path: str = Query(default="")):
    engine = get_engine()
    with engine.connect() as conn:
        source = get_active_source_or_404(conn)

    # Lives in the source's own technical folder, same as the collage
    # (`app/media.py`'s `folder_gif_relative_path`).
    access = get_source_access(source)
    gif_rel = folder_gif_relative_path(path)
    if not access.exists(gif_rel):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "preview_not_found", "message": "No folder preview for this directory."}},
        )
    return Response(content=access.read_bytes(gif_rel), media_type="image/gif")
