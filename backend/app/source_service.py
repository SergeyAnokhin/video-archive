from __future__ import annotations

import socket
import uuid
from dataclasses import dataclass
from pathlib import Path

from .db import connection
from .errors import ApiError
from .secrets import SecretStore
from .time_utils import utc_now


SUPPORTED_PROTOCOLS = {"local", "smb", "ftp", "sftp", "webdav"}
LOCAL_SOURCE_PROTOCOL_SENTINEL = "__local__"
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
        protocol = "local" if row["protocol"] == "smb" and row["host"] == LOCAL_SOURCE_PROTOCOL_SENTINEL else row["protocol"]
        host = "" if protocol == "local" else row["host"]
        return {
            "id": row["id"],
            "name": row["name"],
            "protocol": protocol,
            "host": host,
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
        now = utc_now()
        current_source = self.get_active_source()
        password = payload.password
        stored_protocol = "smb" if payload.protocol == "local" else payload.protocol
        stored_host = LOCAL_SOURCE_PROTOCOL_SENTINEL if payload.protocol == "local" else payload.host
        if password is None and current_source is not None and current_source["has_password"]:
            active_secret_ref = self._get_active_secret_ref()
            password = self._secret_store.get(active_secret_ref)

        username_ref, secret_ref = self._secret_store.upsert_source_credentials(
            source_id,
            payload.username,
            password,
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
                    stored_protocol,
                    stored_host,
                    payload.port,
                    payload.root_path,
                    username_ref,
                    secret_ref,
                    now,
                    now,
                ),
            )

        saved = self.get_active_source()
        if saved is None:
            raise RuntimeError(
                f"Active source row {source_id} could not be reloaded after save. "
                f"stored_protocol={stored_protocol!r} stored_host={stored_host!r} root_path={payload.root_path!r}"
            )
        if saved["id"] != source_id:
            raise RuntimeError(
                f"Active source mismatch after save. expected_id={source_id!r} got_id={saved['id']!r} "
                f"stored_protocol={stored_protocol!r} stored_host={stored_host!r} root_path={payload.root_path!r}"
            )
        return saved

    def _get_active_secret_ref(self) -> str | None:
        with connection(self._database_path) as conn:
            row = conn.execute(
                """
                SELECT secret_ref
                FROM sources
                WHERE is_active = 1
                LIMIT 1
                """
            ).fetchone()
        return None if row is None else row["secret_ref"]

    def test_connection(self, payload: SourcePayload, connector=None) -> dict:
        root_path = Path(payload.root_path)
        root_accessible = root_path.exists() and root_path.is_dir()
        if payload.protocol == "local":
            return {
                "ok": root_accessible,
                "protocol": payload.protocol,
                "host": payload.host,
                "port": None,
                "root_path": payload.root_path,
                "root_accessible": root_accessible,
                "message": (
                    "Local root path is accessible."
                    if root_accessible
                    else "Local root path is not accessible on this machine yet."
                ),
            }

        connector = connector or _test_socket_connection
        port = payload.port or DEFAULT_PORTS[payload.protocol]
        connector(payload.host, port)
        return {
            "ok": root_accessible,
            "protocol": payload.protocol,
            "host": payload.host,
            "port": port,
            "root_path": payload.root_path,
            "root_accessible": root_accessible,
            "message": (
                "TCP connection succeeded and the root path is accessible."
                if root_accessible
                else "TCP connection succeeded, but the root path is not accessible on this machine yet."
            ),
        }

    def reconnect_active_source(self, connector=None) -> dict:
        source = self.get_active_source()
        if source is None:
            raise ApiError("source_not_configured", "No active source is configured.", status=400)

        payload = SourcePayload(
            name=source["name"],
            protocol=source["protocol"],
            host=source["host"],
            port=source["port"],
            root_path=source["root_path"],
            username=source["username"],
            password=None,
        )
        result = self.test_connection(payload, connector=connector)
        if result["ok"]:
            now = utc_now()
            with connection(self._database_path) as conn, conn:
                conn.execute(
                    "UPDATE sources SET last_connected_at = ?, updated_at = ? WHERE id = ?",
                    (now, now, source["id"]),
                )
            result["last_connected_at"] = now
        return result

    def list_local_directories(self, raw_path: str | None) -> dict:
        normalized = _normalize_local_directory_path(raw_path)
        if not normalized:
            return {
                "path": "",
                "parent_path": None,
                "directories": [{"name": drive, "path": drive} for drive in _list_windows_drives()],
                "favorites": self._build_local_directory_favorites(),
            }

        candidate = Path(normalized).expanduser()
        if not candidate.is_absolute():
            raise ApiError("invalid_path", "Local directory browsing requires an absolute path.", status=400)
        if not candidate.exists() or not candidate.is_dir():
            raise ApiError("directory_not_found", "Selected local directory is not available.", status=404)

        resolved = candidate.resolve()
        directories = sorted(
            [entry for entry in resolved.iterdir() if entry.is_dir()],
            key=lambda entry: entry.name.lower(),
        )
        return {
            "path": str(resolved),
            "parent_path": _parent_directory_path(resolved),
            "directories": [{"name": entry.name, "path": str(entry.resolve())} for entry in directories],
            "favorites": self._build_local_directory_favorites(),
        }

    def _build_local_directory_favorites(self) -> list[dict]:
        candidates: list[tuple[str, str, Path]] = []
        backend_dir = self._database_path.parent.parent
        repo_dir = backend_dir.parent
        test_archive_dir = repo_dir / "test-data" / "VideoArchive"
        local_data_dir = self._database_path.parent

        candidates.extend(
            [
                ("repo-test-archive", "repo_test_archive", test_archive_dir),
                ("backend-folder", "backend_folder", backend_dir),
                ("backend-local-data", "backend_local_data", local_data_dir),
            ]
        )

        favorites: list[dict] = []
        seen_paths: set[str] = set()
        for favorite_id, label_key, candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if not resolved.exists() or not resolved.is_dir():
                continue
            resolved_str = str(resolved)
            if resolved_str in seen_paths:
                continue
            seen_paths.add(resolved_str)
            favorites.append(
                {
                    "id": favorite_id,
                    "label_key": label_key,
                    "path": resolved_str,
                }
            )
        return favorites


def parse_source_payload(raw: dict) -> SourcePayload:
    if not isinstance(raw, dict):
        raise ApiError("invalid_request", "Request body must be a JSON object.", status=400)

    name = _require_non_empty_string(raw, "name")
    protocol = _require_non_empty_string(raw, "protocol").lower()
    host = LOCAL_SOURCE_PROTOCOL_SENTINEL if protocol == "local" else _require_non_empty_string(raw, "host")
    root_path = _require_non_empty_string(raw, "root_path")
    username = _optional_string(raw.get("username"))
    password = _optional_string(raw.get("password"))
    port = raw.get("port")

    if protocol not in SUPPORTED_PROTOCOLS:
        raise ApiError(
            "invalid_source_protocol",
            "Protocol must be one of: local, smb, ftp, sftp, webdav.",
            status=400,
        )

    if port is not None:
        if isinstance(port, bool) or not isinstance(port, int):
            raise ApiError("invalid_source_port", "Port must be an integer when provided.", status=400)
        if port < 1 or port > 65535:
            raise ApiError("invalid_source_port", "Port must be between 1 and 65535.", status=400)
        if protocol == "local":
            raise ApiError("invalid_source_port", "Local sources do not use a TCP port.", status=400)

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


def _list_windows_drives() -> list[str]:
    drives: list[str] = []
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        drive = f"{letter}:\\"
        if Path(drive).exists():
            drives.append(drive)
    return drives


def _parent_directory_path(path: Path) -> str | None:
    parent = path.parent
    if parent == path:
        return None
    return str(parent)


def _normalize_local_directory_path(raw_path: str | None) -> str:
    normalized = (raw_path or "").strip().strip('"')
    if not normalized:
        return ""

    trimmed = normalized.rstrip("\\/")
    if trimmed and not trimmed.endswith(":"):
        return trimmed
    return normalized
