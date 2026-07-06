"""File listing and detail endpoints (API §3, §9)."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import text

from app.db import get_engine
from app.source_access import get_active_source_or_404

router = APIRouter()


def _file_not_found_error(file_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "file_not_found", "message": f"File not found: {file_id}"}},
    )


def _file_row_to_dict(row) -> dict:
    return {
        "id": row.id,
        "relative_path": row.relative_path,
        "file_name": row.file_name,
        "extension": row.extension,
        "size_bytes": row.size_bytes,
        "modified_at": row.modified_at,
        "is_video_supported": bool(row.is_video_supported),
        "has_preview_asset": bool(row.has_preview_asset),
        "converted_at": row.converted_at,
        "tagged_at": row.tagged_at,
    }


@router.get("/files")
def list_files(
    directory: str = Query(default=""),
    recursive: bool = Query(default=False),
    video_only: bool = Query(default=False),
    search: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    engine = get_engine()
    with engine.connect() as conn:
        source = get_active_source_or_404(conn)

        clauses = ["source_id = :sid"]
        params: dict = {"sid": source.id, "limit": limit, "offset": offset}

        if directory:
            if recursive:
                clauses.append("relative_path LIKE :prefix")
                params["prefix"] = f"{directory}/%"
            else:
                dir_row = conn.execute(
                    text("SELECT id FROM directories WHERE source_id = :sid AND relative_path = :path"),
                    {"sid": source.id, "path": directory},
                ).fetchone()
                if dir_row is None:
                    raise HTTPException(
                        status_code=404,
                        detail={
                            "error": {
                                "code": "directory_not_found",
                                "message": f"Directory not found: {directory}",
                            }
                        },
                    )
                clauses.append("directory_id = :dir_id")
                params["dir_id"] = dir_row.id

        if video_only:
            clauses.append("is_video_supported = 1")

        if search:
            clauses.append("file_name LIKE :search")
            params["search"] = f"%{search}%"

        where_sql = " AND ".join(clauses)
        rows = conn.execute(
            text(
                f"""
                SELECT id, relative_path, file_name, extension, size_bytes, modified_at,
                       is_video_supported, has_preview_asset, converted_at, tagged_at
                FROM files
                WHERE {where_sql}
                ORDER BY relative_path COLLATE NOCASE
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        ).all()

    return {"files": [_file_row_to_dict(row) for row in rows]}


@router.get("/files/{file_id}")
def get_file(file_id: str):
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT f.*, d.relative_path AS directory_path
                FROM files f
                JOIN directories d ON d.id = f.directory_id
                WHERE f.id = :id
                """
            ),
            {"id": file_id},
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "file_not_found", "message": f"File not found: {file_id}"}},
        )

    return {
        "id": row.id,
        "relative_path": row.relative_path,
        "directory_path": row.directory_path,
        "file_name": row.file_name,
        "extension": row.extension,
        "size_bytes": row.size_bytes,
        "modified_at": row.modified_at,
        "discovered_at": row.discovered_at,
        "last_scanned_at": row.last_scanned_at,
        "is_video_supported": bool(row.is_video_supported),
        "converted_at": row.converted_at,
        "has_preview_asset": bool(row.has_preview_asset),
        "preview_generated_at": row.preview_generated_at,
        "tagged_at": row.tagged_at,
    }


def _preview_path(conn, file_id: str) -> tuple[Path, dict] | None:
    row = conn.execute(
        text(
            """
            SELECT f.relative_path, f.has_preview_asset, f.preview_generated_at, s.root_path
            FROM files f
            JOIN sources s ON s.id = f.source_id
            WHERE f.id = :id AND s.is_active = 1
            """
        ),
        {"id": file_id},
    ).fetchone()
    if row is None:
        return None
    preview_path = (Path(row.root_path) / row.relative_path).with_suffix(".jpg")
    return preview_path, {
        "has_preview_asset": bool(row.has_preview_asset),
        "preview_generated_at": row.preview_generated_at,
    }


@router.get("/files/{file_id}/preview")
def get_file_preview_metadata(file_id: str):
    with get_engine().connect() as conn:
        result = _preview_path(conn, file_id)
    if result is None:
        raise _file_not_found_error(file_id)
    preview_path, metadata = result
    return {
        "has_preview_asset": metadata["has_preview_asset"] and preview_path.exists(),
        "preview_generated_at": metadata["preview_generated_at"],
    }


@router.get("/files/{file_id}/preview.jpg")
def get_file_preview_image(file_id: str):
    with get_engine().connect() as conn:
        result = _preview_path(conn, file_id)
    if result is None:
        raise _file_not_found_error(file_id)
    preview_path, _metadata = result
    if not preview_path.exists():
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "preview_not_found", "message": "No preview asset for this file."}},
        )
    return FileResponse(preview_path, media_type="image/jpeg")
