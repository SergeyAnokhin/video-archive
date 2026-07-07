"""Backup creation and restore (Specification §19, Backup Format).

A backup is a single zip package written into the source's technical folder
(`.video-archive/backups/`, Specification §5.3) via `SourceAccess`, so it
works the same way for `local` and `smb` sources and survives a local
metadata wipe (source switch) since it never leaves the source disk.

Package contents (see `docs/spec/backup-format.md`):

- `manifest.json`: backup id, timestamps, app/schema version, source name.
- `data.json`: the local metadata a source switch wipes (`directories`,
  `files`, `file_tags`) plus the global settings entities backup-format.md
  lists as included data (conversion profiles, tag vocabulary, preview/
  tagging/provider/playback/backup settings). Video files, preview collages,
  and job history are deliberately not included (backup-format.md "Excluded
  Data"; job history is short-lived 24h-retention data, not durable state).
- `secrets.env` (optional): a raw copy of the local secrets file, included
  only when the user explicitly opts in at backup time (`include_secrets`).

Restore is a full replace for the source-scoped tables (they belong to
*this* source only) and an upsert-by-id for the global settings tables (so a
restore never deletes a global entity the backup simply didn't know about).
"""

from __future__ import annotations

import json
import uuid
import zipfile
from datetime import datetime, timezone

from sqlalchemy import text

from app import backup_settings as backup_settings_service
from app import secrets_store
from app.config import APP_VERSION

BACKUP_DIR = ".video-archive/backups"
MANIFEST_NAME = "manifest.json"
DATA_NAME = "data.json"
SECRETS_NAME = "secrets.env"

# Tables restored with a full delete-then-reinsert scoped to the active
# source (their rows only ever make sense for one specific source).
_SOURCE_SCOPED_TABLES = ("directories", "files")

# Tables restored with an upsert-by-id (global settings, not tied to a
# source, so restoring must not wipe entries the backup didn't include).
_GLOBAL_SINGLE_TABLES = ("preview_settings", "tagging_settings", "playback_settings", "backup_settings")
_GLOBAL_MULTI_TABLES = ("conversion_profiles", "tag_catalog", "provider_entries", "preview_layout_presets")


class RestoreError(Exception):
    """Raised when a backup package is missing, invalid, or incompatible."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_timestamp(dt: datetime) -> str:
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _insert_or_replace(conn, table: str, row: dict) -> None:
    columns = list(row.keys())
    column_list = ", ".join(columns)
    placeholders = ", ".join(f":{c}" for c in columns)
    conn.execute(text(f"INSERT OR REPLACE INTO {table} ({column_list}) VALUES ({placeholders})"), row)


# --- listing --------------------------------------------------------------


def _read_manifest(access, rel_path: str) -> dict:
    with access.local_copy(rel_path) as local_path:
        with zipfile.ZipFile(local_path, "r") as zf:
            return json.loads(zf.read(MANIFEST_NAME))


def list_backups(access) -> list[dict]:
    """Backups found in the active source's technical folder, newest first.
    Returns `[]` (rather than erroring) when the folder doesn't exist yet."""
    entries = access.scandir(BACKUP_DIR)
    backups: list[dict] = []
    for entry in entries:
        if entry.is_dir or not entry.name.endswith(".zip"):
            continue
        rel_path = f"{BACKUP_DIR}/{entry.name}"
        try:
            manifest = _read_manifest(access, rel_path)
        except Exception:  # noqa: BLE001 - a corrupt/unreadable package is skipped, not fatal
            continue
        backups.append(
            {
                "id": entry.name[: -len(".zip")],
                "filename": entry.name,
                "size_bytes": entry.stat.size if entry.stat else None,
                **manifest,
            }
        )
    backups.sort(key=lambda b: b["created_at"], reverse=True)
    return backups


# --- create -----------------------------------------------------------------


def _collect_data(engine, source_id: str) -> dict:
    with engine.connect() as conn:
        directories = [dict(r._mapping) for r in conn.execute(
            text("SELECT * FROM directories WHERE source_id = :sid"), {"sid": source_id}
        )]
        files = [dict(r._mapping) for r in conn.execute(
            text("SELECT * FROM files WHERE source_id = :sid"), {"sid": source_id}
        )]
        file_tags = [dict(r._mapping) for r in conn.execute(
            text(
                "SELECT ft.* FROM file_tags ft JOIN files f ON ft.file_id = f.id WHERE f.source_id = :sid"
            ),
            {"sid": source_id},
        )]
        conversion_profiles = [dict(r._mapping) for r in conn.execute(text("SELECT * FROM conversion_profiles"))]
        preview_layout_presets = [
            dict(r._mapping)
            for r in conn.execute(text("SELECT * FROM preview_layout_presets WHERE is_builtin = 0"))
        ]
        preview_settings = [dict(r._mapping) for r in conn.execute(text("SELECT * FROM preview_settings"))]
        tag_catalog = [dict(r._mapping) for r in conn.execute(text("SELECT * FROM tag_catalog"))]
        tagging_settings = [dict(r._mapping) for r in conn.execute(text("SELECT * FROM tagging_settings"))]
        provider_entries = [dict(r._mapping) for r in conn.execute(text("SELECT * FROM provider_entries"))]
        playback_settings = [dict(r._mapping) for r in conn.execute(text("SELECT * FROM playback_settings"))]
        backup_settings_rows = [dict(r._mapping) for r in conn.execute(text("SELECT * FROM backup_settings"))]

    return {
        "directories": directories,
        "files": files,
        "file_tags": file_tags,
        "conversion_profiles": conversion_profiles,
        "preview_layout_presets": preview_layout_presets,
        "preview_settings": preview_settings,
        "tag_catalog": tag_catalog,
        "tagging_settings": tagging_settings,
        "provider_entries": provider_entries,
        "playback_settings": playback_settings,
        "backup_settings": backup_settings_rows,
    }


def create_backup(engine, access, source_row, include_secrets: bool = False) -> dict:
    backup_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    manifest = {
        "backup_id": backup_id,
        "created_at": now.isoformat(),
        "app_version": APP_VERSION,
        "schema_version": _schema_version(),
        "source_name": source_row.name,
        "includes_secrets": bool(include_secrets and secrets_store.SECRETS_PATH.exists()),
    }
    data = _collect_data(engine, source_row.id)
    filename = f"{_format_timestamp(now)}_{backup_id[:8]}.zip"

    with access.stage_output_dir(BACKUP_DIR) as stage_dir:
        local_zip = stage_dir / filename
        with zipfile.ZipFile(local_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2))
            zf.writestr(DATA_NAME, json.dumps(data))
            if manifest["includes_secrets"]:
                zf.write(secrets_store.SECRETS_PATH, SECRETS_NAME)
        access.commit_new_file(local_zip, f"{BACKUP_DIR}/{filename}")

    removed = _enforce_retention(engine, access)
    return {**manifest, "filename": filename, "removed_old_backups": removed}


def _schema_version() -> int:
    from app.db import SCHEMA_VERSION

    return SCHEMA_VERSION


def _enforce_retention(engine, access) -> int:
    settings = backup_settings_service.get_settings(engine)
    retention = max(1, settings["retention_count"])
    backups = list_backups(access)
    if len(backups) <= retention:
        return 0

    stale = backups[retention:]  # already sorted newest-first, so the tail is the oldest
    removed = 0
    for entry in stale:
        try:
            access.remote_remove(f"{BACKUP_DIR}/{entry['filename']}")
            removed += 1
        except Exception:  # noqa: BLE001 - best-effort cleanup, a failed delete isn't fatal
            pass
    return removed


# --- delete -----------------------------------------------------------------


def delete_backup(access, backup_id: str) -> bool:
    rel_path = f"{BACKUP_DIR}/{backup_id}.zip"
    if not access.exists(rel_path):
        return False
    access.remote_remove(rel_path)
    return True


# --- restore ------------------------------------------------------------


def restore_backup(engine, access, source_row, backup_id: str) -> dict:
    rel_path = f"{BACKUP_DIR}/{backup_id}.zip"
    if not access.exists(rel_path):
        raise RestoreError(f"Backup not found: {backup_id}")

    with access.local_copy(rel_path) as local_zip:
        with zipfile.ZipFile(local_zip, "r") as zf:
            names = zf.namelist()
            if MANIFEST_NAME not in names or DATA_NAME not in names:
                raise RestoreError("Backup package is invalid: missing manifest or data.")
            try:
                manifest = json.loads(zf.read(MANIFEST_NAME))
                data = json.loads(zf.read(DATA_NAME))
            except (json.JSONDecodeError, KeyError) as exc:
                raise RestoreError(f"Backup package is invalid: {exc}") from exc
            secrets_bytes = zf.read(SECRETS_NAME) if SECRETS_NAME in names else None

    schema_version = _schema_version()
    if manifest.get("schema_version", 0) > schema_version:
        raise RestoreError(
            f"Backup schema version {manifest.get('schema_version')} is newer than this app supports "
            f"({schema_version}); update the application before restoring."
        )

    source_id = source_row.id
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM file_tags WHERE file_id IN (SELECT id FROM files WHERE source_id = :sid)"),
            {"sid": source_id},
        )
        for table in _SOURCE_SCOPED_TABLES:
            conn.execute(text(f"DELETE FROM {table} WHERE source_id = :sid"), {"sid": source_id})

        for table in _SOURCE_SCOPED_TABLES:
            for row in data.get(table, []):
                _insert_or_replace(conn, table, {**row, "source_id": source_id})
        for row in data.get("file_tags", []):
            _insert_or_replace(conn, "file_tags", row)
        for table in _GLOBAL_MULTI_TABLES:
            for row in data.get(table, []):
                _insert_or_replace(conn, table, row)
        for table in _GLOBAL_SINGLE_TABLES:
            for row in data.get(table, []):
                _insert_or_replace(conn, table, row)

    if secrets_bytes is not None:
        secrets_store.SECRETS_PATH.write_bytes(secrets_bytes)

    counts = {key: len(value) for key, value in data.items()}
    return {"manifest": manifest, "counts": counts}
