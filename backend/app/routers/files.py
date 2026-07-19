"""File listing and detail endpoints (API §3, §9)."""

from __future__ import annotations

from math import gcd
from pathlib import PurePosixPath

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import text

from app import conversion, file_ops, similarity
from app.conversion_profiles import get_profile
from app.db import get_engine
from app.media import (
    ORIGINAL_MARKER,
    VARIANT_MARKER,
    compute_variant_tags,
    file_row_to_dict,
    preview_gif_relative_path,
    resolve_variant_preview_flags,
    variant_base_stem,
)
from app.source_access import get_active_source_or_404
from app.sources import get_source_access
from app.tags import (
    assign_file_tag,
    assign_user_defined_tag,
    get_or_create_tag,
    list_top_tags_for_files,
    remove_file_tag,
    resolve_tag_color,
)

router = APIRouter()

# HTTP status per app/file_ops.py error code.
_FILE_OP_STATUS = {
    "file_not_found": 404,
    "directory_not_found": 404,
    "same_location": 400,
    "destination_collision": 409,
}


def _file_op_http_error(err: file_ops.FileOperationError) -> HTTPException:
    return HTTPException(
        status_code=_FILE_OP_STATUS[err.code],
        detail={"error": {"code": err.code, "message": err.message}},
    )


def _file_not_found_error(file_id: str) -> HTTPException:
    return HTTPException(
        status_code=404,
        detail={"error": {"code": "file_not_found", "message": f"File not found: {file_id}"}},
    )


@router.get("/files")
def list_files(
    directory: str = Query(default=""),
    recursive: bool = Query(default=False),
    video_only: bool = Query(default=False),
    search: str | None = Query(default=None),
    tags: str | None = Query(default=None, description="Comma-separated tag keys; matches any of them"),
    tag_search: str | None = Query(default=None, description="Substring match against tag keys; matches any tag containing it"),
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

        # Default listing is scoped to actual library content (video or
        # image) so it never surfaces arbitrary scanned-but-unsupported
        # files; `video_only` narrows further to video alone (used by
        # `recentlyViewed.ts`'s video-only preview-style sampling).
        clauses.append("(is_video_supported = 1 OR is_image_supported = 1)")
        if video_only:
            clauses.append("is_video_supported = 1")

        if search:
            clauses.append("file_name LIKE :search")
            params["search"] = f"%{search}%"

        if tag_search and tag_search.strip():
            clauses.append(
                "id IN (SELECT ft.file_id FROM file_tags ft JOIN tag_catalog tc ON tc.id = ft.tag_id "
                "WHERE tc.tag_key LIKE :tag_search)"
            )
            params["tag_search"] = f"%{tag_search.strip().lower()}%"

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
                SELECT id, directory_id, relative_path, file_name, extension, size_bytes, modified_at,
                       is_video_supported, is_image_supported, has_preview_asset, converted_at, tagged_at
                FROM files
                WHERE {where_sql}
                ORDER BY relative_path COLLATE NOCASE
                LIMIT :limit OFFSET :offset
                """
            ),
            params,
        ).all()

    files = [file_row_to_dict(row, relative_path=row.relative_path) for row in rows]
    variant_tags = compute_variant_tags([(row.id, row.relative_path) for row in rows])
    ai_tags = list_top_tags_for_files(engine, [row.id for row in rows])
    preview_flags = resolve_variant_preview_flags(
        [(row.id, row.directory_id, row.file_name, row.has_preview_asset) for row in rows]
    )
    for entry in files:
        entry["variant_tags"] = variant_tags.get(entry["id"], [])
        entry["ai_tags"] = ai_tags.get(entry["id"], [])
        entry["has_preview_asset"] = preview_flags.get(entry["id"], entry["has_preview_asset"])

    return {"files": files}


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
        "is_image_supported": bool(row.is_image_supported),
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
    tagging.py, similarity.py) rather than adding a DB column + rescan.

    Probes a `local_copy()` rather than `direct_path()`: ffprobe is an
    external OS process, so for an SMB source a raw UNC `direct_path()`
    string is only reachable through the app's own in-process `smbclient`
    session, not by an external process using the OS's own SMB stack --
    ffprobe would fail immediately and this endpoint would silently return
    every field empty (bug report: file info panel showed size but nothing
    else for a file whose preview had already been generated via
    `local_copy()`, which does work)."""
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
    with access.local_copy(row.relative_path) as local_path:
        info = conversion.probe_media(local_path)

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


def _preview_lookup(conn, file_id: str):
    row = conn.execute(
        text(
            """
            SELECT f.relative_path, f.file_name, f.directory_id, f.has_preview_asset,
                   f.preview_generated_at, s.*
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


def _preview_source_row(conn, row):
    """The row whose on-disk preview assets should back `row`'s preview:
    itself normally, or its original sibling for a variant-sweep output,
    which never gets its own preview generated (Specification §8.3) — the
    variant is visually near-identical to the original it was tuned from, so
    reusing that preview beats showing a broken thumbnail (user request)."""
    base_stem = variant_base_stem(row.file_name)
    if base_stem is None:
        return row
    original = conn.execute(
        text(
            """
            SELECT relative_path, file_name FROM files
            WHERE directory_id = :dir_id AND file_name LIKE :prefix
              AND file_name NOT LIKE '%.variant-%'
            ORDER BY file_name
            LIMIT 1
            """
        ),
        {"dir_id": row.directory_id, "prefix": f"{base_stem}.%"},
    ).fetchone()
    return original if original is not None else row


@router.get("/files/{file_id}/preview")
def get_file_preview_metadata(file_id: str):
    with get_engine().connect() as conn:
        row = _preview_lookup(conn, file_id)
        if row is None:
            raise _file_not_found_error(file_id)
        source_row = _preview_source_row(conn, row)
    access = get_source_access(row)
    collage_rel = str(PurePosixPath(source_row.relative_path).with_suffix(".jpg"))
    return {
        "has_preview_asset": bool(row.has_preview_asset) and access.exists(collage_rel),
        "preview_generated_at": row.preview_generated_at,
    }


@router.get("/files/{file_id}/preview.jpg")
def get_file_preview_image(file_id: str):
    with get_engine().connect() as conn:
        row = _preview_lookup(conn, file_id)
        if row is None:
            raise _file_not_found_error(file_id)
        source_row = _preview_source_row(conn, row)

    access = get_source_access(row)
    collage_rel = str(PurePosixPath(source_row.relative_path).with_suffix(".jpg"))
    if not access.exists(collage_rel):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "preview_not_found", "message": "No preview asset for this file."}},
        )
    return Response(content=access.read_bytes(collage_rel), media_type="image/jpeg")


@router.get("/files/{file_id}/preview.gif")
def get_file_preview_gif(file_id: str):
    """Animated GIF companion to the JPEG collage (user request), used for
    grid/list-view hover previews. Lives in the source's own technical
    folder, same as the collage (`app/media.py`'s `preview_gif_relative_path`)."""
    with get_engine().connect() as conn:
        row = _preview_lookup(conn, file_id)
        if row is None:
            raise _file_not_found_error(file_id)
        source_row = _preview_source_row(conn, row)

    access = get_source_access(row)
    gif_rel = preview_gif_relative_path(source_row.relative_path)
    if not access.exists(gif_rel):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "preview_not_found", "message": "No GIF preview for this file."}},
        )
    return Response(content=access.read_bytes(gif_rel), media_type="image/gif")


@router.get("/files/{file_id}/similar")
def get_similar_files(file_id: str):
    """Approximate near-duplicate lookup (Specification §13): optional and
    secondary, so an empty list (no signature yet, or nothing within the
    distance threshold) is a normal, non-error response. A standalone image
    never runs through the preview job that computes a video's signature as
    a side effect (post-V1, user request -- "similar images"), so its
    signature is computed lazily here on first request if missing."""
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                SELECT f.source_id, f.relative_path, f.is_image_supported, s.*
                FROM files f JOIN sources s ON s.id = f.source_id
                WHERE f.id = :id AND s.is_active = 1
                """
            ),
            {"id": file_id},
        ).fetchone()
        if row is None:
            raise _file_not_found_error(file_id)
        has_signature = (
            conn.execute(
                text("SELECT 1 FROM file_similarity_signatures WHERE file_id = :id"), {"id": file_id}
            ).fetchone()
            is not None
        )

    if not has_signature and row.is_image_supported:
        try:
            access = get_source_access(row)
            with access.local_copy(row.relative_path) as image_path:
                signature = similarity.compute_image_signature(image_path)
            if signature is not None:
                similarity.store_signature(engine, file_id, signature)
        except Exception:  # noqa: BLE001 - best-effort only, see docstring
            pass

    with engine.connect() as conn:
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
                SELECT tc.id AS tag_id, tc.display_name, tc.color, ft.score, ft.provider_name, ft.model_name,
                       ft.assigned_at
                FROM file_tags ft
                JOIN tag_catalog tc ON tc.id = ft.tag_id
                WHERE ft.file_id = :file_id AND ft.score > 0
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
                "color": resolve_tag_color(row.tag_id, row.color),
                "score": row.score,
                "provider_name": row.provider_name,
                "model_name": row.model_name,
                "assigned_at": row.assigned_at,
            }
            for row in rows
        ]
    }


class AssignTagRequest(BaseModel):
    tag_id: str | None = None
    display_name: str | None = None


@router.post("/files/{file_id}/tags")
def add_file_tag(file_id: str, body: AssignTagRequest):
    """Manually assign a tag to a file (user request -- editable tags in
    `FileInfoPanel`): either an existing vocabulary entry by `tag_id`, or a
    typed `display_name` that's matched against the existing vocabulary
    (case/whitespace-insensitive) or created as a new entry if no match
    exists. See `tags.assign_file_tag()` for the full-confidence/`manual`
    provider convention this uses."""
    engine = get_engine()
    with engine.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM files WHERE id = :id"), {"id": file_id}).fetchone()
    if exists is None:
        raise _file_not_found_error(file_id)

    if body.tag_id:
        tag_id = body.tag_id
    elif body.display_name and body.display_name.strip():
        tag_id = get_or_create_tag(engine, body.display_name)["id"]
    else:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "tag_required", "message": "tag_id or display_name is required."}},
        )

    assign_file_tag(engine, file_id, tag_id)
    return {"assigned": True}


@router.post("/files/{file_id}/tags/user-defined")
def add_user_defined_file_tag(file_id: str, body: AssignTagRequest):
    """Dedicated picker endpoint (user request) for the user-defined tag
    pool, distinct from `POST /files/{id}/tags`'s free-text add: an existing
    `tag_id` is attached as-is, a typed `display_name` creates (or promotes)
    a genuine user-defined tag rather than an ad-hoc one -- see
    `tags.assign_user_defined_tag()`."""
    engine = get_engine()
    with engine.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM files WHERE id = :id"), {"id": file_id}).fetchone()
    if exists is None:
        raise _file_not_found_error(file_id)

    if body.tag_id:
        assigned = assign_user_defined_tag(engine, file_id, tag_id=body.tag_id)
        if assigned is None:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "tag_not_found", "message": f"Tag not found: {body.tag_id}"}},
            )
    elif body.display_name and body.display_name.strip():
        assign_user_defined_tag(engine, file_id, display_name=body.display_name)
    else:
        raise HTTPException(
            status_code=422,
            detail={"error": {"code": "tag_required", "message": "tag_id or display_name is required."}},
        )
    return {"assigned": True}


@router.delete("/files/{file_id}/tags/{tag_id}")
def delete_file_tag(file_id: str, tag_id: str):
    if not remove_file_tag(get_engine(), file_id, tag_id):
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "tag_assignment_not_found", "message": "Tag is not assigned to this file."}},
        )
    return {"deleted": True}


@router.delete("/files/{file_id}")
def delete_file(file_id: str):
    try:
        file_ops.delete_file(get_engine(), file_id)
    except file_ops.FileOperationError as err:
        raise _file_op_http_error(err)
    return {"deleted": True}


class MoveFileRequest(BaseModel):
    target_directory: str = ""


@router.post("/files/{file_id}/move")
def move_file(file_id: str, body: MoveFileRequest):
    try:
        updated = file_ops.move_file(get_engine(), file_id, body.target_directory)
    except file_ops.FileOperationError as err:
        raise _file_op_http_error(err)

    return {
        "id": updated.id,
        "relative_path": updated.relative_path,
        "directory_path": updated.directory_path,
        "file_name": updated.file_name,
        "extension": updated.extension,
        "size_bytes": updated.size_bytes,
        "modified_at": updated.modified_at,
        "is_video_supported": bool(updated.is_video_supported),
        "is_image_supported": bool(updated.is_image_supported),
        "converted_at": updated.converted_at,
        "has_preview_asset": bool(updated.has_preview_asset),
        "tagged_at": updated.tagged_at,
        "is_variant": VARIANT_MARKER in updated.file_name,
        "is_original": ORIGINAL_MARKER in updated.file_name,
    }
