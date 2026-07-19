"""Saved-sources list, switching, and preview-asset management (user
request): lets several archives (e.g. a local test folder and a remote SMB
share) be configured once and switched between without losing each one's own
data. `PUT /source` (see `app/routers/source.py`) still owns configuring a
new/existing source's connection details; this router covers listing what's
saved, activating one of them, forgetting one, and clearing the active
source's animated preview GIFs.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from app import preview_assets, secrets_store
from app.db import get_engine
from app.routers.source import _source_row_to_dict
from app.source_switch import switch_active_source
from app.sources import get_source_access

router = APIRouter()

_EMPTY_PREVIEW_STATS = {"size_bytes": 0, "file_count": 0}


def _get_source_or_404(conn, source_id: str):
    row = conn.execute(text("SELECT * FROM sources WHERE id = :id"), {"id": source_id}).fetchone()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "source_not_found", "message": f"Source not found: {source_id}"}},
        )
    return row


def _preview_stats(row) -> dict:
    """Live stats require a connection, so they're only meaningful for the
    active source -- an inactive saved source may be offline (SMB) and isn't
    worth connecting to just to populate a Settings list."""
    if not row.is_active:
        return _EMPTY_PREVIEW_STATS
    try:
        return preview_assets.stats_for_active_source(get_source_access(row))
    except Exception:  # noqa: BLE001 - best-effort; a transient connection issue shouldn't break the list
        return _EMPTY_PREVIEW_STATS


@router.get("/sources")
def list_sources():
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM sources ORDER BY is_active DESC, updated_at DESC")).fetchall()
    return {
        "sources": [{**_source_row_to_dict(row), "preview_cache": _preview_stats(row)} for row in rows]
    }


@router.post("/sources/{source_id}/activate")
def activate_source(source_id: str):
    engine = get_engine()
    with engine.connect() as conn:
        row = _get_source_or_404(conn, source_id)

    result = switch_active_source(engine, row)
    return {
        **_source_row_to_dict(result["row"]),
        "detected_backups": result["detected_backups"],
        "auto_restored": result["auto_restored"],
        "scan_job": result["scan_job"],
    }


@router.delete("/sources/{source_id}")
def forget_source(source_id: str):
    engine = get_engine()
    with engine.connect() as conn:
        row = _get_source_or_404(conn, source_id)

    if row.is_active:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "active_source",
                    "message": "Switch to a different source before forgetting the active one.",
                }
            },
        )

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM sources WHERE id = :id"), {"id": source_id})
    if row.protocol == "smb":
        secrets_store.delete_source_credentials_for(row.username_ref, row.secret_ref)
    return {"deleted": True}


@router.delete("/sources/{source_id}/preview-cache")
def clear_source_preview_cache(source_id: str):
    engine = get_engine()
    with engine.connect() as conn:
        row = _get_source_or_404(conn, source_id)

    if not row.is_active:
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "not_active_source",
                    "message": "Only the active source's preview GIFs can be cleared.",
                }
            },
        )

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE files SET has_preview_asset = 0, preview_generated_at = NULL WHERE source_id = :id"
            ),
            {"id": source_id},
        )
        conn.execute(
            text(
                "UPDATE directories SET has_folder_preview = 0, folder_preview_generated_at = NULL "
                "WHERE source_id = :id"
            ),
            {"id": source_id},
        )

    preview_assets.clear_for_active_source(get_source_access(row))
    return {"cleared": True}
