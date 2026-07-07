"""Immediate folder contents endpoint (API §3, §9, UI Screens §1)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy import text

from app.db import get_engine
from app.media import FOLDER_PREVIEW_FILENAME, ORIGINAL_MARKER, VARIANT_MARKER
from app.source_access import get_active_source_or_404
from app.sources import get_source_access
from app.status import compute_directory_status

router = APIRouter()


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
        "is_variant": VARIANT_MARKER in row.file_name,
        "is_original": ORIGINAL_MARKER in row.file_name,
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
                "SELECT relative_path, name, has_folder_preview FROM directories "
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
                "has_folder_preview": bool(row.has_folder_preview),
            }
            if include_status:
                entry["status"] = compute_directory_status(conn, source.id, row.relative_path)
            directories.append(entry)

        file_rows = conn.execute(
            text(
                """
                SELECT id, file_name, extension, size_bytes, modified_at, is_video_supported,
                       has_preview_asset, converted_at, tagged_at
                FROM files
                WHERE directory_id = :dir_id AND is_video_supported = 1
                ORDER BY file_name COLLATE NOCASE
                """
            ),
            {"dir_id": directory_row.id},
        ).all()
        files = [_file_row_to_dict(row) for row in file_rows]

    return {"path": path, "directories": directories, "files": files}


@router.get("/directories/preview.gif")
def get_directory_preview_gif(path: str = Query(default="")):
    engine = get_engine()
    with engine.connect() as conn:
        source = get_active_source_or_404(conn)

    access = get_source_access(source)
    preview_rel = f"{path}/{FOLDER_PREVIEW_FILENAME}" if path else FOLDER_PREVIEW_FILENAME
    if not access.exists(preview_rel):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "preview_not_found", "message": "No folder preview for this directory."}},
        )
    if access.protocol == "local":
        return FileResponse(access.direct_path(preview_rel), media_type="image/gif")
    return Response(content=access.read_bytes(preview_rel), media_type="image/gif")
