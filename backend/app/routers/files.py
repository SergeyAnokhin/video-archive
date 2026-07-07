"""File listing and detail endpoints (API §3, §9)."""

from __future__ import annotations

from datetime import datetime, timezone
from math import gcd
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import text

from app import conversion, similarity
from app.conversion_profiles import get_profile
from app.db import get_engine
from app.media import ORIGINAL_MARKER, VARIANT_MARKER, preview_gif_relative_path
from app.source_access import get_active_source_or_404
from app.sources import get_source_access

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        "is_variant": VARIANT_MARKER in row.file_name,
        "is_original": ORIGINAL_MARKER in row.file_name,
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
        "is_variant": VARIANT_MARKER in row.file_name,
        "is_original": ORIGINAL_MARKER in row.file_name,
    }


@router.get("/files/{file_id}/media-info")
def get_file_media_info(file_id: str):
    """On-demand technical info (codec/resolution/bitrate/etc.) for the file
    info panel. Not persisted: ffprobe runs fresh on each request, mirroring
    how `conversion.probe_media()` is already used elsewhere (jobs/convert.py,
    tagging.py, similarity.py) rather than adding a DB column + rescan."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT f.relative_path, f.last_conversion_profile_id, s.*
                FROM files f
                JOIN sources s ON s.id = f.source_id
                WHERE f.id = :id AND s.is_active = 1
                """
            ),
            {"id": file_id},
        ).fetchone()
        if row is None:
            raise _file_not_found_error(file_id)
        profile = get_profile(engine, row.last_conversion_profile_id) if row.last_conversion_profile_id else None

    access = get_source_access(row)
    info = conversion.probe_media(Path(access.direct_path(row.relative_path)))

    aspect_ratio = None
    if info and info.get("width") and info.get("height"):
        divisor = gcd(info["width"], info["height"])
        aspect_ratio = f"{info['width'] // divisor}:{info['height'] // divisor}"

    return {
        "width": info.get("width") if info else None,
        "height": info.get("height") if info else None,
        "aspect_ratio": aspect_ratio,
        "video_codec": info.get("video_codec_name") if info else None,
        "format_name": info.get("format_name") if info else None,
        "duration": info.get("duration") if info else None,
        "bit_rate": info.get("bit_rate") if info else None,
        "conversion_profile": profile,
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


def _file_with_source_lookup(conn, file_id: str):
    # f.id is deliberately excluded from the select list: s.* also carries an
    # `id` column (the source's), and the caller already has file_id in hand
    # (mirrors the same avoidance in _preview_lookup() above).
    return conn.execute(
        text(
            """
            SELECT f.relative_path, f.file_name, f.directory_id, f.source_id, s.*
            FROM files f
            JOIN sources s ON s.id = f.source_id
            WHERE f.id = :id AND s.is_active = 1
            """
        ),
        {"id": file_id},
    ).fetchone()


@router.delete("/files/{file_id}")
def delete_file(file_id: str):
    engine = get_engine()
    with engine.begin() as conn:
        row = _file_with_source_lookup(conn, file_id)
        if row is None:
            raise _file_not_found_error(file_id)

        access = get_source_access(row)
        if access.exists(row.relative_path):
            access.remote_remove(row.relative_path)

        jpg_rel = str(PurePosixPath(row.relative_path).with_suffix(".jpg"))
        if access.exists(jpg_rel):
            access.remote_remove(jpg_rel)

        gif_rel = preview_gif_relative_path(row.relative_path)
        if access.exists(gif_rel):
            access.remote_remove(gif_rel)

        conn.execute(text("DELETE FROM file_tags WHERE file_id = :id"), {"id": file_id})
        conn.execute(text("DELETE FROM file_similarity_signatures WHERE file_id = :id"), {"id": file_id})
        conn.execute(text("DELETE FROM files WHERE id = :id"), {"id": file_id})

    return {"deleted": True}


class MoveFileRequest(BaseModel):
    target_directory: str = ""


@router.post("/files/{file_id}/move")
def move_file(file_id: str, body: MoveFileRequest):
    engine = get_engine()
    with engine.begin() as conn:
        row = _file_with_source_lookup(conn, file_id)
        if row is None:
            raise _file_not_found_error(file_id)

        target_dir_row = conn.execute(
            text("SELECT id FROM directories WHERE source_id = :sid AND relative_path = :path"),
            {"sid": row.source_id, "path": body.target_directory},
        ).fetchone()
        if target_dir_row is None:
            raise HTTPException(
                status_code=404,
                detail={
                    "error": {
                        "code": "directory_not_found",
                        "message": f"Directory not found: {body.target_directory}",
                    }
                },
            )

        new_rel = f"{body.target_directory}/{row.file_name}" if body.target_directory else row.file_name
        if new_rel == row.relative_path:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "same_location", "message": "File is already in this folder."}},
            )

        collision = conn.execute(
            text("SELECT id FROM files WHERE source_id = :sid AND relative_path = :path"),
            {"sid": row.source_id, "path": new_rel},
        ).fetchone()
        if collision is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": {
                        "code": "destination_collision",
                        "message": "A file with this name already exists in the destination folder.",
                    }
                },
            )

        access = get_source_access(row)
        access.remote_rename(row.relative_path, new_rel)

        old_jpg_rel = str(PurePosixPath(row.relative_path).with_suffix(".jpg"))
        new_jpg_rel = str(PurePosixPath(new_rel).with_suffix(".jpg"))
        if access.exists(old_jpg_rel):
            access.remote_rename(old_jpg_rel, new_jpg_rel)

        old_gif_rel = preview_gif_relative_path(row.relative_path)
        new_gif_rel = preview_gif_relative_path(new_rel)
        if access.exists(old_gif_rel):
            access.remote_rename(old_gif_rel, new_gif_rel)

        conn.execute(
            text(
                """
                UPDATE files
                SET relative_path = :new_rel, directory_id = :dir_id, updated_at = :now
                WHERE id = :id
                """
            ),
            {"new_rel": new_rel, "dir_id": target_dir_row.id, "now": _now(), "id": file_id},
        )

        updated = conn.execute(
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

    return {
        "id": updated.id,
        "relative_path": updated.relative_path,
        "directory_path": updated.directory_path,
        "file_name": updated.file_name,
        "extension": updated.extension,
        "size_bytes": updated.size_bytes,
        "modified_at": updated.modified_at,
        "is_video_supported": bool(updated.is_video_supported),
        "converted_at": updated.converted_at,
        "has_preview_asset": bool(updated.has_preview_asset),
        "tagged_at": updated.tagged_at,
        "is_variant": VARIANT_MARKER in updated.file_name,
        "is_original": ORIGINAL_MARKER in updated.file_name,
    }
