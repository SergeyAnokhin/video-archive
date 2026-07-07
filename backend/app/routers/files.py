"""File listing and detail endpoints (API §3, §9)."""

from __future__ import annotations

from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy import text

from app import similarity
from app.db import get_engine
from app.media import preview_gif_relative_path
from app.source_access import get_active_source_or_404
from app.sources import get_source_access

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
    tags: str | None = Query(default=None, description="Comma-separated tag keys; matches any of them"),
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

        if tags:
            tag_keys = [key.strip().lower() for key in tags.split(",") if key.strip()]
            if tag_keys:
                placeholders = ", ".join(f":tag_{i}" for i in range(len(tag_keys)))
                clauses.append(
                    "id IN (SELECT ft.file_id FROM file_tags ft JOIN tag_catalog tc ON tc.id = ft.tag_id "
                    f"WHERE tc.tag_key IN ({placeholders}))"
                )
                for i, key in enumerate(tag_keys):
                    params[f"tag_{i}"] = key

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


def _preview_rel(row) -> str:
    return str(PurePosixPath(row.relative_path).with_suffix(".jpg"))


def _preview_lookup(conn, file_id: str):
    row = conn.execute(
        text(
            """
            SELECT f.relative_path, f.has_preview_asset, f.preview_generated_at, s.*
            FROM files f
            JOIN sources s ON s.id = f.source_id
            WHERE f.id = :id AND s.is_active = 1
            """
        ),
        {"id": file_id},
    ).fetchone()
    if row is None:
        return None
    return row


@router.get("/files/{file_id}/preview")
def get_file_preview_metadata(file_id: str):
    with get_engine().connect() as conn:
        row = _preview_lookup(conn, file_id)
    if row is None:
        raise _file_not_found_error(file_id)
    access = get_source_access(row)
    return {
        "has_preview_asset": bool(row.has_preview_asset) and access.exists(_preview_rel(row)),
        "preview_generated_at": row.preview_generated_at,
    }


@router.get("/files/{file_id}/preview.jpg")
def get_file_preview_image(file_id: str):
    with get_engine().connect() as conn:
        row = _preview_lookup(conn, file_id)
    if row is None:
        raise _file_not_found_error(file_id)

    access = get_source_access(row)
    preview_rel = _preview_rel(row)
    if not access.exists(preview_rel):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "preview_not_found", "message": "No preview asset for this file."}},
        )
    if access.protocol == "local":
        return FileResponse(access.direct_path(preview_rel), media_type="image/jpeg")
    # SMB previews are small JPEGs; buffering the whole file in memory keeps
    # this endpoint simple instead of needing a streamed-download-then-serve
    # dance for an asset that's typically a few hundred KB.
    return Response(content=access.read_bytes(preview_rel), media_type="image/jpeg")


@router.get("/files/{file_id}/preview.gif")
def get_file_preview_gif(file_id: str):
    """Animated GIF companion to the JPEG collage (user request), used for
    grid/list-view hover previews. Stored in `.video-archive/previews/`
    rather than next to the video (`media.preview_gif_relative_path()`)."""
    with get_engine().connect() as conn:
        row = _preview_lookup(conn, file_id)
    if row is None:
        raise _file_not_found_error(file_id)

    access = get_source_access(row)
    gif_rel = preview_gif_relative_path(row.relative_path)
    if not access.exists(gif_rel):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "preview_not_found", "message": "No GIF preview for this file."}},
        )
    if access.protocol == "local":
        return FileResponse(access.direct_path(gif_rel), media_type="image/gif")
    return Response(content=access.read_bytes(gif_rel), media_type="image/gif")


@router.get("/files/{file_id}/similar")
def get_similar_files(file_id: str):
    """Approximate near-duplicate lookup (Specification §13): optional and
    secondary, so an empty list (no signature yet, or nothing within the
    distance threshold) is a normal, non-error response."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT source_id FROM files WHERE id = :id"), {"id": file_id}).fetchone()
        if row is None:
            raise _file_not_found_error(file_id)
        results = similarity.find_similar(engine, row.source_id, file_id)
    return {"similar": results}


@router.get("/files/{file_id}/tags")
def get_file_tags(file_id: str):
    with get_engine().connect() as conn:
        file_row = conn.execute(text("SELECT id FROM files WHERE id = :id"), {"id": file_id}).fetchone()
        if file_row is None:
            raise _file_not_found_error(file_id)
        rows = conn.execute(
            text(
                """
                SELECT tc.id AS tag_id, tc.display_name, ft.score, ft.provider_name, ft.model_name, ft.assigned_at
                FROM file_tags ft
                JOIN tag_catalog tc ON tc.id = ft.tag_id
                WHERE ft.file_id = :file_id
                ORDER BY ft.score DESC
                """
            ),
            {"file_id": file_id},
        ).all()

    return {
        "tags": [
            {
                "tag_id": row.tag_id,
                "display_name": row.display_name,
                "score": row.score,
                "provider_name": row.provider_name,
                "model_name": row.model_name,
                "assigned_at": row.assigned_at,
            }
            for row in rows
        ]
    }
