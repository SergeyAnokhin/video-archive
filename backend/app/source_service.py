from __future__ import annotations

import socket
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .db import connection
from .errors import ApiError
from .secrets import SecretStore


SUPPORTED_PROTOCOLS = {"smb", "ftp", "sftp", "webdav"}
DEFAULT_PORTS = {
    "smb": 445,
    "ftp": 21,
    "sftp": 22,
    "webdav": 80,
}


@dataclass(frozen=True)
class SourcePayload:
    name: str
    protocol: str
    host: str
    port: int | None
    root_path: str
    username: str | None
    password: str | None


class SourceService:
    def __init__(self, database_path: Path, secret_store: SecretStore) -> None:
        self._database_path = database_path
        self._secret_store = secret_store

    def get_active_source(self) -> dict | None:
        with connection(self._database_path) as conn:
            row = conn.execute(
                """
                SELECT id, name, protocol, host, port, root_path, username_ref, secret_ref,
                       created_at, updated_at, last_connected_at, last_scan_at
                FROM sources
                WHERE is_active = 1
                LIMIT 1
                """
            ).fetchone()

        if row is None:
            return None

        username = self._secret_store.get(row["username_ref"])
        has_password = self._secret_store.get(row["secret_ref"]) is not None
        return {
            "id": row["id"],
            "name": row["name"],
            "protocol": row["protocol"],
            "host": row["host"],
            "port": row["port"],
            "root_path": row["root_path"],
            "username": username,
            "has_password": has_password,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_connected_at": row["last_connected_at"],
            "last_scan_at": row["last_scan_at"],
        }

    def replace_active_source(self, payload: SourcePayload) -> dict:
        source_id = str(uuid.uuid4())
        now = _utc_now()
        username_ref, secret_ref = self._secret_store.upsert_source_credentials(
            source_id,
            payload.username,
            payload.password,
        )

        with connection(self._database_path) as conn, conn:
            conn.execute("UPDATE sources SET is_active = 0, updated_at = ? WHERE is_active = 1", (now,))
            conn.execute(
                """
                INSERT INTO sources (
                    id, name, protocol, host, port, root_path, username_ref, secret_ref,
                    is_active, created_at, updated_at, last_connected_at, last_scan_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, NULL, NULL)
                """,
                (
                    source_id,
                    payload.name,
                    payload.protocol,
                    payload.host,
                    payload.port,
                    payload.root_path,
                    username_ref,
                    secret_ref,
                    now,
                    now,
                ),
            )

        return self.get_active_source() or {}

    def test_connection(self, payload: SourcePayload, connector=None) -> dict:
        connector = connector or _test_socket_connection
        port = payload.port or DEFAULT_PORTS[payload.protocol]
        connector(payload.host, port)
        return {
            "ok": True,
            "protocol": payload.protocol,
            "host": payload.host,
            "port": port,
            "message": "TCP connection succeeded.",
        }


def parse_source_payload(raw: dict) -> SourcePayload:
    if not isinstance(raw, dict):
        raise ApiError("invalid_request", "Request body must be a JSON object.", status=400)

    name = _require_non_empty_string(raw, "name")
    protocol = _require_non_empty_string(raw, "protocol").lower()
    host = _require_non_empty_string(raw, "host")
    root_path = _require_non_empty_string(raw, "root_path")
    username = _optional_string(raw.get("username"))
    password = _optional_string(raw.get("password"))
    port = raw.get("port")

    if protocol not in SUPPORTED_PROTOCOLS:
        raise ApiError(
            "invalid_source_protocol",
            "Protocol must be one of: smb, ftp, sftp, webdav.",
            status=400,
        )

    if port is not None:
        if isinstance(port, bool) or not isinstance(port, int):
            raise ApiError("invalid_source_port", "Port must be an integer when provided.", status=400)
        if port < 1 or port > 65535:
            raise ApiError("invalid_source_port", "Port must be between 1 and 65535.", status=400)

    return SourcePayload(
        name=name,
        protocol=protocol,
        host=host,
        port=port,
        root_path=root_path,
        username=username,
        password=password,
    )


def _require_non_empty_string(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ApiError("invalid_request", f"Field '{key}' must be a non-empty string.", status=400)
    return value.strip()


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ApiError("invalid_request", "Optional source credentials must be strings.", status=400)
    normalized = value.strip()
    return normalized or None


def _test_socket_connection(host: str, port: int) -> None:
    try:
        with socket.create_connection((host, port), timeout=5):
            return
    except OSError as exc:
        raise ApiError(
            "source_connection_failed",
            f"Unable to reach remote source at {host}:{port}.",
            status=400,
        ) from exc


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
