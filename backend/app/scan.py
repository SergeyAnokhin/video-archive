"""Filesystem scan for the active source (Specification §6.1).

Walks the source root (`local` filesystem or an `smb` share, via
`app/sources/access.py`), upserts `directories`/`files` rows, detects preview
assets, and removes rows for files/directories that no longer exist.
`discover_filesystem()` and the `upsert_*` helpers are also reused by the
Stage 3 `rescan` job (`app/jobs/rescan.py`) to refresh a single directory
subtree with per-file job-item granularity instead of one whole-source scan.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import Engine, text

from app.media import FOLDER_PREVIEW_FILENAME, SUPPORTED_IMAGE_EXTENSIONS, SUPPORTED_VIDEO_EXTENSIONS
from app.sources import SourceAccess
from app.sources.local_backend import LocalBackend


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extension_of(name: str) -> str:
    return Path(name).suffix.lstrip(".").lower()


def _stem_of(name: str) -> str:
    return Path(name).stem


@dataclass(frozen=True)
class ScanResult:
    directories_count: int
    files_count: int
    video_files_count: int


def discover_filesystem(
    access: SourceAccess, subtree_rel: str = ""
) -> tuple[dict[str, tuple[str, str | None, bool]], dict[str, dict]]:
    """Walk `subtree_rel` (the source root by default, or a subtree of it via
    `access`) and return the directories/files found there, keyed by path
    relative to the source root.
    """
    touched_dirs: dict[str, tuple[str, str | None, bool]] = {}
    touched_files: dict[str, dict] = {}

    for rel_dir, parent_rel, entries in access.walk(subtree_rel):
        filenames = [e.name for e in entries if not e.is_dir]
        lower_names = {name.lower() for name in filenames}
        video_stems_lower = {
            _stem_of(name).lower()
            for name in filenames
            if _extension_of(name) in SUPPORTED_VIDEO_EXTENSIONS
        }
        has_folder_preview = FOLDER_PREVIEW_FILENAME in lower_names

        dir_name = rel_dir.rsplit("/", 1)[-1] if rel_dir else access.root_name()
        touched_dirs[rel_dir] = (dir_name, parent_rel, has_folder_preview)

        for entry in entries:
            if entry.is_dir:
                continue
            filename = entry.name
            if filename.lower() == FOLDER_PREVIEW_FILENAME:
                continue
            ext = _extension_of(filename)
            stem = _stem_of(filename)

            if ext in ("jpg", "jpeg") and stem.lower() in video_stems_lower:
                # Matched video's own preview asset, not an independent item.
                continue

            rel_file = f"{rel_dir}/{filename}" if rel_dir else filename
            is_video = ext in SUPPORTED_VIDEO_EXTENSIONS
            is_image = ext in SUPPORTED_IMAGE_EXTENSIONS
            has_preview = is_video and f"{stem.lower()}.jpg" in lower_names

            touched_files[rel_file] = {
                "directory_rel": rel_dir,
                "file_name": filename,
                "extension": ext,
                "size_bytes": entry.stat.size,
                "modified_at": entry.stat.modified_at,
                "is_video_supported": is_video,
                "is_image_supported": is_image,
                "has_preview_asset": has_preview,
            }

    return touched_dirs, touched_files


def scan_source(engine: Engine, source_id: str, root_path: Path) -> ScanResult:
    """Scan a `local` source. SMB sources are scanned through
    `scan_source_access()` instead (see `app/routers/source.py`)."""
    root_path = Path(root_path).resolve()
    access = SourceAccess(LocalBackend(root_path), "local")
    return scan_source_access(engine, source_id, access)


def scan_source_access(engine: Engine, source_id: str, access: SourceAccess) -> ScanResult:
    touched_dirs, touched_files = discover_filesystem(access)

    now = _now()
    with engine.begin() as conn:
        dir_ids = _sync_directories(conn, source_id, touched_dirs, now)
        _sync_files(conn, source_id, dir_ids, touched_files, now)
        conn.execute(
            text("UPDATE sources SET last_scan_at = :now, updated_at = :now WHERE id = :id"),
            {"now": now, "id": source_id},
        )

    video_count = sum(1 for attrs in touched_files.values() if attrs["is_video_supported"])
    return ScanResult(
        directories_count=len(touched_dirs),
        files_count=len(touched_files),
        video_files_count=video_count,
    )


def upsert_directory(
    conn,
    source_id: str,
    rel_path: str,
    name: str,
    parent_rel: str | None,
    has_folder_preview: bool,
    now: str,
    existing_id: str | None = None,
) -> str:
    if existing_id:
        conn.execute(
            text(
                """
                UPDATE directories
                SET name = :name, parent_relative_path = :parent_rel,
                    has_folder_preview = :has_preview, last_scanned_at = :now, updated_at = :now
                WHERE id = :id
                """
            ),
            {
                "name": name,
                "parent_rel": parent_rel,
                "has_preview": has_folder_preview,
                "now": now,
                "id": existing_id,
            },
        )
        return existing_id

    new_id = str(uuid.uuid4())
    conn.execute(
        text(
            """
            INSERT INTO directories
                (id, source_id, relative_path, name, parent_relative_path,
                 has_folder_preview, last_scanned_at, created_at, updated_at)
            VALUES (:id, :sid, :rel, :name, :parent_rel, :has_preview, :now, :now, :now)
            """
        ),
        {
            "id": new_id,
            "sid": source_id,
            "rel": rel_path,
            "name": name,
            "parent_rel": parent_rel,
            "has_preview": has_folder_preview,
            "now": now,
        },
    )
    return new_id


def upsert_file(
    conn,
    source_id: str,
    directory_id: str,
    rel_path: str,
    attrs: dict,
    now: str,
    existing_id: str | None = None,
) -> str:
    if existing_id:
        conn.execute(
            text(
                """
                UPDATE files
                SET directory_id = :dir_id, file_name = :file_name, extension = :ext,
                    size_bytes = :size, modified_at = :modified_at,
                    is_video_supported = :is_video, is_image_supported = :is_image,
                    has_preview_asset = :has_preview,
                    last_scanned_at = :now, updated_at = :now
                WHERE id = :id
                """
            ),
            {
                "dir_id": directory_id,
                "file_name": attrs["file_name"],
                "ext": attrs["extension"],
                "size": attrs["size_bytes"],
                "modified_at": attrs["modified_at"],
                "is_video": attrs["is_video_supported"],
                "is_image": attrs["is_image_supported"],
                "has_preview": attrs["has_preview_asset"],
                "now": now,
                "id": existing_id,
            },
        )
        return existing_id

    new_id = str(uuid.uuid4())
    conn.execute(
        text(
            """
            INSERT INTO files
                (id, source_id, directory_id, relative_path, file_name, extension,
                 size_bytes, modified_at, discovered_at, last_scanned_at,
                 is_video_supported, is_image_supported, has_preview_asset, created_at, updated_at)
            VALUES
                (:id, :sid, :dir_id, :rel, :file_name, :ext,
                 :size, :modified_at, :now, :now,
                 :is_video, :is_image, :has_preview, :now, :now)
            """
        ),
        {
            "id": new_id,
            "sid": source_id,
            "dir_id": directory_id,
            "rel": rel_path,
            "file_name": attrs["file_name"],
            "ext": attrs["extension"],
            "size": attrs["size_bytes"],
            "modified_at": attrs["modified_at"],
            "now": now,
            "is_video": attrs["is_video_supported"],
            "is_image": attrs["is_image_supported"],
            "has_preview": attrs["has_preview_asset"],
        },
    )
    return new_id


def _sync_directories(
    conn,
    source_id: str,
    touched_dirs: dict[str, tuple[str, str | None, bool]],
    now: str,
) -> dict[str, str]:
    existing = conn.execute(
        text("SELECT id, relative_path FROM directories WHERE source_id = :sid"),
        {"sid": source_id},
    ).all()
    existing_ids = {row.relative_path: row.id for row in existing}

    dir_ids: dict[str, str] = {}
    for rel_path, (name, parent_rel, has_folder_preview) in touched_dirs.items():
        dir_ids[rel_path] = upsert_directory(
            conn, source_id, rel_path, name, parent_rel, has_folder_preview, now,
            existing_id=existing_ids.get(rel_path),
        )

    stale = [{"sid": source_id, "rel": rel} for rel in existing_ids if rel not in touched_dirs]
    if stale:
        conn.execute(text("DELETE FROM directories WHERE source_id = :sid AND relative_path = :rel"), stale)

    return dir_ids


def _sync_files(
    conn,
    source_id: str,
    dir_ids: dict[str, str],
    touched_files: dict[str, dict],
    now: str,
) -> None:
    existing = conn.execute(
        text("SELECT id, relative_path FROM files WHERE source_id = :sid"),
        {"sid": source_id},
    ).all()
    existing_ids = {row.relative_path: row.id for row in existing}

    for rel_path, attrs in touched_files.items():
        directory_id = dir_ids[attrs["directory_rel"]]
        upsert_file(
            conn, source_id, directory_id, rel_path, attrs, now,
            existing_id=existing_ids.get(rel_path),
        )

    stale = [{"sid": source_id, "rel": rel} for rel in existing_ids if rel not in touched_files]
    if stale:
        conn.execute(text("DELETE FROM files WHERE source_id = :sid AND relative_path = :rel"), stale)
