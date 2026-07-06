"""Source configuration for the `local` and `smb` protocols (Specification
§5, API §2). `webdav` remains reserved for an optional later stage.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from app import secrets_store
from app.config import BACKEND_DIR
from app.db import get_engine
from app.scan import scan_source, scan_source_access
from app.sources import get_source_access
from app.sources.smb_backend import test_connection as smb_test_connection

router = APIRouter()

SUPPORTED_PROTOCOLS = ("local", "smb")


class SourceRequest(BaseModel):
    name: str
    protocol: str
    root_path: str
    host: str | None = None
    port: int | None = None
    username: str | None = None
    password: str | None = None


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
        "host": row.host,
        "port": row.port,
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
                "message": f"Supported protocols: {', '.join(SUPPORTED_PROTOCOLS)}.",
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
    if body.protocol == "local":
        path = _resolve_local_path(body.root_path)
        if not path.exists():
            return {"ok": False, "message": f"Path does not exist: {path}"}
        if not path.is_dir():
            return {"ok": False, "message": f"Path is not a directory: {path}"}
        return {"ok": True, "message": None}

    if body.protocol == "smb":
        if not body.host:
            return {"ok": False, "message": "Host is required for an SMB source."}
        ok, message = smb_test_connection(body.host, body.port, body.root_path, body.username, body.password)
        return {"ok": ok, "message": message}

    return {"ok": False, "message": f"Supported protocols: {', '.join(SUPPORTED_PROTOCOLS)}."}


@router.put("/source")
def put_source(body: SourceRequest):
    if body.protocol not in SUPPORTED_PROTOCOLS:
        raise _unsupported_protocol_error()

    engine = get_engine()
    now = datetime.now(timezone.utc).isoformat()
    new_id = str(uuid.uuid4())

    if body.protocol == "local":
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
        root_path = str(path)
        host, port, username_ref, secret_ref = None, None, None, None
    else:
        if not body.host:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "host_required", "message": "Host is required for an SMB source."}},
            )
        root_path = (body.root_path or "").strip("/\\")
        host, port = body.host, body.port
        username_ref, secret_ref = secrets_store.SOURCE_USERNAME_REF, secrets_store.SOURCE_SECRET_REF

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
                INSERT INTO sources
                    (id, name, protocol, host, port, root_path, username_ref, secret_ref,
                     is_active, created_at, updated_at, last_connected_at)
                VALUES (:id, :name, :protocol, :host, :port, :root_path, :username_ref, :secret_ref,
                        1, :now, :now, :now)
                """
            ),
            {
                "id": new_id,
                "name": body.name,
                "protocol": body.protocol,
                "host": host,
                "port": port,
                "root_path": root_path,
                "username_ref": username_ref,
                "secret_ref": secret_ref,
                "now": now,
            },
        )

    if body.protocol == "smb":
        if body.username or body.password:
            secrets_store.set_source_credentials(body.username or "", body.password or "")
        with engine.connect() as conn:
            new_row = conn.execute(text("SELECT * FROM sources WHERE id = :id"), {"id": new_id}).fetchone()
        scan_source_access(engine, new_id, get_source_access(new_row))
    else:
        scan_source(engine, new_id, path)

    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM sources WHERE id = :id"), {"id": new_id}).fetchone()

    # Backup discovery arrives with Stage 8; no backups can exist yet.
    return {**_source_row_to_dict(row), "detected_backups": []}


@router.post("/source/reconnect")
def reconnect_source():
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "no_source_configured", "message": "No active source is configured."}},
        )

    if row.protocol == "local":
        # Local sources need no reconnect/network-refresh behavior
        # (Specification §5); a rescan is sufficient to detect changes.
        return {"ok": True, "message": None}

    access = get_source_access(row)
    try:
        access.is_dir("")
    except Exception as exc:  # noqa: BLE001 - surfaced to the user as a plain message
        return {"ok": False, "message": str(exc)}

    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE sources SET last_connected_at = :now, updated_at = :now WHERE id = :id"),
            {"now": now, "id": row.id},
        )
    return {"ok": True, "message": None}
