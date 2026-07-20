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
from app.source_switch import switch_active_source
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
    direct_access_enabled: bool = False


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
        "direct_access_enabled": bool(getattr(row, "direct_access_enabled", False)),
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
    """Configure a source and switch to it. If the currently active source
    has the same `(protocol, root_path)` -- the same underlying data -- this
    is a reconnect: `host`/`port`/credentials/`direct_access_enabled`/`name`
    are updated on that same row in place, no backup/wipe/rescan (see
    `switch_active_source()`'s `already_active` handling). A pre-flight
    connection check runs first so a bad host/password surfaces as a clean
    400 instead of an unhandled exception from deeper in the switch.
    Otherwise, if `(protocol, host, port, root_path)` matches a previously
    saved (but inactive) source, that saved row is reused (and its
    credentials/name updated) instead of creating a duplicate -- resubmitting
    the same connection is how a saved source is renamed or has its
    credentials refreshed. Switching itself (backup of whatever was active,
    wipe, auto-restore of the new source's own data, enqueuing the
    reconciling rescan job when it's a genuine switch) is handled by
    `switch_active_source()`, shared with `POST /sources/{id}/activate`."""
    if body.protocol not in SUPPORTED_PROTOCOLS:
        raise _unsupported_protocol_error()

    engine = get_engine()
    now = datetime.now(timezone.utc).isoformat()

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
        host, port = None, None
    else:
        if not body.host:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "host_required", "message": "Host is required for an SMB source."}},
            )
        root_path = (body.root_path or "").strip("/\\")
        host, port = body.host, body.port

    # Only meaningful for smb: ignored (always stored off) for local, which
    # has no UNC/OS-session concept in the first place.
    direct_access_enabled = bool(body.direct_access_enabled) if body.protocol == "smb" else False

    with engine.connect() as conn:
        active_row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()
        is_reconnect = (
            active_row is not None and active_row.protocol == body.protocol and active_row.root_path == root_path
        )
        if is_reconnect:
            existing = active_row
        else:
            existing = conn.execute(
                text(
                    """
                    SELECT * FROM sources
                    WHERE protocol = :protocol AND root_path = :root_path
                      AND COALESCE(host, '') = COALESCE(:host, '') AND COALESCE(port, -1) = COALESCE(:port, -1)
                    """
                ),
                {"protocol": body.protocol, "root_path": root_path, "host": host, "port": port},
            ).fetchone()

    if is_reconnect and body.protocol == "smb":
        test_username = body.username or None
        test_password = body.password or None
        if not test_username and not test_password:
            test_username, test_password = secrets_store.get_source_credentials_for(
                existing.username_ref, existing.secret_ref
            )
        ok, message = smb_test_connection(host, port, root_path, test_username, test_password)
        if not ok:
            raise HTTPException(
                status_code=400,
                detail={"error": {"code": "connection_failed", "message": message}},
            )

    if existing is not None:
        source_id = existing.id
        username_ref, secret_ref = existing.username_ref, existing.secret_ref
        if body.protocol == "smb" and (body.username or body.password):
            username_ref, secret_ref = secrets_store.set_source_credentials_for(
                source_id, body.username or "", body.password or ""
            )
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE sources SET name = :name, host = :host, port = :port, "
                    "username_ref = :username_ref, secret_ref = :secret_ref, "
                    "direct_access_enabled = :direct_access_enabled, "
                    "updated_at = :now WHERE id = :id"
                ),
                {
                    "name": body.name,
                    "host": host,
                    "port": port,
                    "username_ref": username_ref,
                    "secret_ref": secret_ref,
                    "direct_access_enabled": direct_access_enabled,
                    "now": now,
                    "id": source_id,
                },
            )
    else:
        source_id = str(uuid.uuid4())
        username_ref, secret_ref = None, None
        if body.protocol == "smb":
            username_ref, secret_ref = secrets_store.set_source_credentials_for(
                source_id, body.username or "", body.password or ""
            )
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sources
                        (id, name, protocol, host, port, root_path, username_ref, secret_ref,
                         direct_access_enabled, is_active, created_at, updated_at, last_connected_at)
                    VALUES (:id, :name, :protocol, :host, :port, :root_path, :username_ref, :secret_ref,
                            :direct_access_enabled, 0, :now, :now, :now)
                    """
                ),
                {
                    "id": source_id,
                    "name": body.name,
                    "protocol": body.protocol,
                    "host": host,
                    "port": port,
                    "root_path": root_path,
                    "username_ref": username_ref,
                    "secret_ref": secret_ref,
                    "direct_access_enabled": direct_access_enabled,
                    "now": now,
                },
            )

    with engine.connect() as conn:
        new_row = conn.execute(text("SELECT * FROM sources WHERE id = :id"), {"id": source_id}).fetchone()

    result = switch_active_source(engine, new_row)
    return {
        **_source_row_to_dict(result["row"]),
        "detected_backups": result["detected_backups"],
        "auto_restored": result["auto_restored"],
        "scan_job": result["scan_job"],
    }


def _get_active_source_row(conn):
    row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "no_source_configured", "message": "No active source is configured."}},
        )
    return row


def _check_connection_status(row) -> dict:
    """Shared by `GET /source/status` and `POST /source/reconnect`: whether
    the source is currently reachable and, for `smb`, whether the
    direct-access fast path is actually in effect right now (as opposed to
    just enabled)."""
    if row.protocol == "local":
        return {"ok": True, "message": None, "direct_access_enabled": False, "direct_access_active": None}

    access = get_source_access(row)
    try:
        access.is_dir("")
    except Exception as exc:  # noqa: BLE001 - surfaced to the user as a plain message
        return {
            "ok": False,
            "message": str(exc),
            "direct_access_enabled": bool(row.direct_access_enabled),
            "direct_access_active": None,
        }

    return {
        "ok": True,
        "message": None,
        "direct_access_enabled": bool(row.direct_access_enabled),
        "direct_access_active": access.direct_access_status(),
    }


@router.get("/source/status")
def get_source_status():
    """Read-only connection status for the active source -- unlike
    `POST /source/reconnect`, this never writes to the database, so it's
    safe to call passively (e.g. every time Settings opens) rather than only
    on an explicit user action."""
    engine = get_engine()
    with engine.connect() as conn:
        row = _get_active_source_row(conn)
    return _check_connection_status(row)


@router.post("/source/reconnect")
def reconnect_source():
    engine = get_engine()
    with engine.connect() as conn:
        row = _get_active_source_row(conn)

    status = _check_connection_status(row)
    if row.protocol == "local" or not status["ok"]:
        return status

    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE sources SET last_connected_at = :now, updated_at = :now WHERE id = :id"),
            {"now": now, "id": row.id},
        )
    return status
