"""Immediate folder contents endpoint (API §3, §9, UI Screens §1)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text

from app import directory_ops, preview_cache
from app.db import get_engine
from app.media import ORIGINAL_MARKER, VARIANT_MARKER, compute_variant_tags
from app.source_access import get_active_source_or_404
from app.status import compute_directory_status

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


def _file_row_to_dict(row) -> dict:
    return {
        "id": row.id,
        "file_name": row.file_name,
        "extension": row.extension,
        "size_bytes": row.size_bytes,
        "modified_at": row.modified_at,
        "is_video_supported": bool(row.is_video_supported),
        "has_preview_asset": bool(row.has_preview_asset),
        "converted_at": row.converted_at,
        "tagged_at": row.tagged_at,
        "duration_seconds": row.duration_seconds,
        "is_variant": VARIANT_MARKER in row.file_name,
        "is_original": ORIGINAL_MARKER in row.file_name,
        "variant_tags": [],
    }


@router.get("/directories/children")
def get_directory_children(
    path: str = Query(default=""),
    include_status: bool = Query(default=False),
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
            directories.append(entry)

        file_rows = conn.execute(
            text(
                """
                SELECT id, relative_path, file_name, extension, size_bytes, modified_at, is_video_supported,
                       has_preview_asset, converted_at, tagged_at, duration_seconds
                FROM files
                WHERE directory_id = :dir_id AND is_video_supported = 1
                ORDER BY file_name COLLATE NOCASE
                """
            ),
            {"dir_id": directory_row.id},
        ).all()
        files = [_file_row_to_dict(row) for row in file_rows]
        variant_tags = compute_variant_tags([(row.id, row.relative_path) for row in file_rows])
        for entry in files:
            entry["variant_tags"] = variant_tags.get(entry["id"], [])

    return {"path": path, "directories": directories, "files": files}


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


@router.get("/directories/preview.gif")
def get_directory_preview_gif(path: str = Query(default="")):
    engine = get_engine()
    with engine.connect() as conn:
        source = get_active_source_or_404(conn)

    # Served from the local preview cache (`app/preview_cache.py`, user
    # request) rather than the source itself.
    folder_gif = preview_cache.folder_gif_path(source.id, path)
    if not folder_gif.exists():
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "preview_not_found", "message": "No folder preview for this directory."}},
        )
    return FileResponse(folder_gif, media_type="image/gif")
