"""Source configuration for the `local` protocol (Specification §5, API §2).

SMB/WebDAV arrive in later stages (Roadmap Stage 7); this router accepts
only `protocol: "local"` for now.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app.config import BACKEND_DIR
from app.db import get_engine
from app.scan import scan_source

router = APIRouter()


class SourceRequest(BaseModel):
    name: str
    protocol: str
    root_path: str


def _resolve_local_path(root_path: str) -> Path:
    path = Path(root_path)
    if not path.is_absolute():
        path = BACKEND_DIR / path
    return path.resolve()


def _source_row_to_dict(row) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "protocol": row.protocol,
        "root_path": row.root_path,
        "is_active": bool(row.is_active),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "last_connected_at": row.last_connected_at,
        "last_scan_at": row.last_scan_at,
    }


def _unsupported_protocol_error() -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": {
                "code": "unsupported_protocol",
                "message": "Only the local protocol is supported until a later stage.",
            }
        },
    )


@router.get("/source")
def get_source():
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()
    return _source_row_to_dict(row) if row else None


@router.post("/source/test-connection")
def test_source_connection(body: SourceRequest):
    if body.protocol != "local":
        return {"ok": False, "message": "Only the local protocol is supported at this stage."}

    path = _resolve_local_path(body.root_path)
    if not path.exists():
        return {"ok": False, "message": f"Path does not exist: {path}"}
    if not path.is_dir():
        return {"ok": False, "message": f"Path is not a directory: {path}"}
    return {"ok": True, "message": None}


@router.put("/source")
def put_source(body: SourceRequest):
    if body.protocol != "local":
        raise _unsupported_protocol_error()

    path = _resolve_local_path(body.root_path)
    if not path.exists() or not path.is_dir():
        raise HTTPException(
            status_code=400,
            detail={
                "error": {
                    "code": "invalid_root_path",
                    "message": f"Path does not exist or is not a directory: {path}",
                }
            },
        )

    engine = get_engine()
    now = datetime.now(timezone.utc).isoformat()
    new_id = str(uuid.uuid4())

    with engine.begin() as conn:
        # Replacing the active source is destructive: the frontend warns
        # first, then the backend wipes all previous library metadata
        # (Specification §5.2).
        conn.execute(text("DELETE FROM files"))
        conn.execute(text("DELETE FROM directories"))
        conn.execute(text("DELETE FROM sources"))

        conn.execute(
            text(
                """
                INSERT INTO sources (id, name, protocol, root_path, is_active, created_at, updated_at)
                VALUES (:id, :name, :protocol, :root_path, 1, :now, :now)
                """
            ),
            {
                "id": new_id,
                "name": body.name,
                "protocol": body.protocol,
                "root_path": str(path),
                "now": now,
            },
        )

    scan_source(engine, new_id, path)

    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM sources WHERE id = :id"), {"id": new_id}).fetchone()

    # Backup discovery arrives with Stage 8; no backups can exist yet.
    return {**_source_row_to_dict(row), "detected_backups": []}
