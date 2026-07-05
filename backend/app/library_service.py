from __future__ import annotations

import json
import os
import uuid
from pathlib import Path, PurePosixPath

from .db import connection
from .errors import ApiError
from .time_utils import utc_now


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".wmv"}


class LibraryService:
    def __init__(self, database_path: Path, source_service) -> None:
        self._database_path = database_path
        self._source_service = source_service

    def get_queue_summary(self) -> dict:
        with connection(self._database_path) as conn:
            queued_jobs = conn.execute("SELECT COUNT(*) AS count FROM jobs WHERE status = 'queued'").fetchone()["count"]
            running_jobs = conn.execute("SELECT COUNT(*) AS count FROM jobs WHERE status = 'running'").fetchone()["count"]

        status = "busy" if queued_jobs or running_jobs else "idle"
        return {
            "status": status,
            "queued_jobs": queued_jobs,
            "running_jobs": running_jobs,
        }

    def list_jobs(self, limit: int = 20) -> list[dict]:
        safe_limit = max(1, min(limit, 100))
        with connection(self._database_path) as conn:
            rows = conn.execute(
                """
                SELECT id, job_type, scope_type, scope_ref, status, parameters, started_at,
                       finished_at, summary_message, created_at, updated_at
                FROM jobs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()

        return [self._serialize_job_row(row) for row in rows]

    def get_tree(self) -> list[dict]:
        source = self._source_service.get_active_source()
        if source is None:
            return []

        with connection(self._database_path) as conn:
            directory_rows = conn.execute(
                """
                SELECT relative_path, name, parent_relative_path
                FROM directories
                WHERE source_id = ?
                ORDER BY relative_path
                """,
                (source["id"],),
            ).fetchall()
            file_rows = conn.execute(
                """
                SELECT directory_id, relative_path, is_video_supported, conversion_state, preview_state,
                       has_preview_assets
                FROM files
                WHERE source_id = ?
                """,
                (source["id"],),
            ).fetchall()

        nodes_by_path: dict[str, dict] = {}
        for row in directory_rows:
            path = row["relative_path"]
            nodes_by_path[path] = {
                "id": path or "root",
                "name": row["name"] or source["name"],
                "path": path,
                "parent_path": row["parent_relative_path"],
                "children": [],
                "indicators": {
                    "conversion": None,
                    "preview": None,
                },
            }

        if "" not in nodes_by_path:
            nodes_by_path[""] = {
                "id": "root",
                "name": source["name"],
                "path": "",
                "parent_path": None,
                "children": [],
                "indicators": {
                    "conversion": None,
                    "preview": None,
                },
            }

        aggregates = {
            path: {
                "conversion": {"total": 0, "done": 0, "in_progress": 0, "failed": 0},
                "preview": {"total": 0, "done": 0, "in_progress": 0, "failed": 0},
            }
            for path in nodes_by_path
        }

        for row in file_rows:
            if not row["is_video_supported"]:
                continue

            directory_path = _parent_path(row["relative_path"])
            for ancestor in _ancestor_paths(directory_path):
                if ancestor not in aggregates:
                    continue

                aggregates[ancestor]["conversion"]["total"] += 1
                conversion_state = row["conversion_state"]
                if conversion_state == "done":
                    aggregates[ancestor]["conversion"]["done"] += 1
                elif conversion_state == "in_progress":
                    aggregates[ancestor]["conversion"]["in_progress"] += 1
                elif conversion_state == "failed":
                    aggregates[ancestor]["conversion"]["failed"] += 1

                aggregates[ancestor]["preview"]["total"] += 1
                preview_state = row["preview_state"]
                if preview_state == "done" and row["has_preview_assets"]:
                    aggregates[ancestor]["preview"]["done"] += 1
                elif preview_state == "in_progress":
                    aggregates[ancestor]["preview"]["in_progress"] += 1
                elif preview_state == "failed":
                    aggregates[ancestor]["preview"]["failed"] += 1

        for path, node in nodes_by_path.items():
            node["indicators"]["conversion"] = _build_indicator(aggregates[path]["conversion"], "conversion")
            node["indicators"]["preview"] = _build_indicator(aggregates[path]["preview"], "preview")

        roots: list[dict] = []
        for path, node in sorted(nodes_by_path.items(), key=lambda item: (item[0].count("/"), item[0])):
            parent_path = node["parent_path"]
            if parent_path is None or parent_path not in nodes_by_path:
                roots.append(node)
                continue
            nodes_by_path[parent_path]["children"].append(node)

        return roots

    def list_files(self, directory: str = "") -> list[dict]:
        source = self._source_service.get_active_source()
        if source is None:
            return []

        normalized_directory = normalize_relative_path(directory)

        with connection(self._database_path) as conn:
            if normalized_directory:
                directory_row = conn.execute(
                    """
                    SELECT id
                    FROM directories
                    WHERE source_id = ? AND relative_path = ?
                    """,
                    (source["id"], normalized_directory),
                ).fetchone()
                if directory_row is None:
                    return []

                rows = conn.execute(
                    """
                    SELECT id, relative_path, path, file_name, extension, size_bytes, modified_at,
                           last_scanned_at, is_video_supported, conversion_state, preview_state,
                           has_preview_assets, last_error_code, last_error_message
                    FROM files
                    WHERE source_id = ? AND directory_id = ?
                    ORDER BY file_name COLLATE NOCASE
                    """,
                    (source["id"], directory_row["id"]),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, relative_path, path, file_name, extension, size_bytes, modified_at,
                           last_scanned_at, is_video_supported, conversion_state, preview_state,
                           has_preview_assets, last_error_code, last_error_message
                    FROM files
                    WHERE source_id = ? AND relative_path NOT LIKE '%/%'
                    ORDER BY file_name COLLATE NOCASE
                    """,
                    (source["id"],),
                ).fetchall()

        return [
            {
                "id": row["id"],
                "relative_path": row["relative_path"],
                "path": row["path"],
                "file_name": row["file_name"],
                "extension": row["extension"],
                "size_bytes": row["size_bytes"],
                "modified_at": row["modified_at"],
                "last_scanned_at": row["last_scanned_at"],
                "is_video_supported": bool(row["is_video_supported"]),
                "conversion_state": row["conversion_state"],
                "preview_state": row["preview_state"],
                "has_preview_assets": bool(row["has_preview_assets"]),
                "last_error_code": row["last_error_code"],
                "last_error_message": row["last_error_message"],
            }
            for row in rows
        ]

    def create_scan_job(self) -> dict:
        source = self._require_active_source()
        return self._run_scan_job(source=source, job_type="scan", scope_type="source", scope_ref=None, scan_path="")

    def create_rescan_job(self, relative_path: str) -> dict:
        source = self._require_active_source()
        normalized_path = normalize_relative_path(relative_path)
        if not normalized_path:
            return self._run_scan_job(
                source=source,
                job_type="rescan",
                scope_type="source",
                scope_ref="",
                scan_path="",
            )
        return self._run_scan_job(
            source=source,
            job_type="rescan",
            scope_type="directory",
            scope_ref=normalized_path,
            scan_path=normalized_path,
        )

    def run_reconnect_probe(self) -> dict:
        source = self._require_active_source()
        self._assert_root_directory_available(source["root_path"])
        return {"ok": True, "root_path": source["root_path"]}

    def _run_scan_job(self, source: dict, job_type: str, scope_type: str, scope_ref: str | None, scan_path: str) -> dict:
        now = utc_now()
        job_id = str(uuid.uuid4())
        parameters = json.dumps({"relative_path": scope_ref or "", "recursive": True})

        with connection(self._database_path) as conn, conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, job_type, scope_type, scope_ref, status, requested_by, parameters,
                    started_at, finished_at, summary_message, cancel_requested_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'running', NULL, ?, ?, NULL, NULL, NULL, ?, ?)
                """,
                (job_id, job_type, scope_type, scope_ref, parameters, now, now, now),
            )

        try:
            summary = self.scan_source(source, scan_path)
        except ApiError as exc:
            failed_at = utc_now()
            with connection(self._database_path) as conn, conn:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'failed', finished_at = ?, summary_message = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (failed_at, exc.message, failed_at, job_id),
                )
            raise

        finished_at = utc_now()
        message = f"Scanned {summary['directories_scanned']} directories and {summary['files_scanned']} files."
        with connection(self._database_path) as conn, conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'completed', finished_at = ?, summary_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (finished_at, message, finished_at, job_id),
            )
            conn.execute(
                "UPDATE sources SET last_scan_at = ?, updated_at = ? WHERE id = ?",
                (finished_at, finished_at, source["id"]),
            )

        with connection(self._database_path) as conn:
            row = conn.execute(
                """
                SELECT id, job_type, scope_type, scope_ref, status, parameters, started_at,
                       finished_at, summary_message, created_at, updated_at
                FROM jobs
                WHERE id = ?
                """,
                (job_id,),
            ).fetchone()
        return self._serialize_job_row(row)

    def scan_source(self, source: dict, scan_path: str) -> dict:
        root_path = self._assert_root_directory_available(source["root_path"])
        scan_root = root_path / Path(scan_path) if scan_path else root_path
        if not scan_root.exists() or not scan_root.is_dir():
            raise ApiError("directory_not_found", "Selected directory is no longer available in the source.", status=404)

        now = utc_now()
        discovered_directories: dict[str, dict] = {}
        discovered_files: dict[str, dict] = {}

        for current_root, dir_names, file_names in os.walk(scan_root):
            dir_names.sort()
            file_names.sort()
            current_path = Path(current_root)
            relative_directory = _to_relative_path(root_path, current_path)
            parent_relative_path = None if relative_directory == "" else _parent_path(relative_directory)
            discovered_directories[relative_directory] = {
                "relative_path": relative_directory,
                "name": _directory_display_name(current_path, source["name"], relative_directory),
                "parent_relative_path": parent_relative_path,
                "last_scanned_at": now,
            }

            for file_name in file_names:
                file_path = current_path / file_name
                stat_result = file_path.stat()
                relative_file = _to_relative_path(root_path, file_path)
                extension = file_path.suffix.lower()
                discovered_files[relative_file] = {
                    "relative_path": relative_file,
                    "directory_relative_path": relative_directory,
                    "path": str(file_path),
                    "file_name": file_name,
                    "extension": extension,
                    "size_bytes": int(stat_result.st_size),
                    "modified_at": _timestamp_from_stat(stat_result),
                    "last_scanned_at": now,
                    "is_video_supported": extension in VIDEO_EXTENSIONS,
                }

        subtree_prefix = normalize_relative_path(scan_path)

        if "" not in discovered_directories:
            discovered_directories[""] = {
                "relative_path": "",
                "name": _directory_display_name(root_path, source["name"], ""),
                "parent_relative_path": None,
                "last_scanned_at": now,
            }

        for ancestor in _ancestor_paths(subtree_prefix):
            if ancestor in discovered_directories:
                continue
            ancestor_path = root_path / Path(ancestor) if ancestor else root_path
            if not ancestor_path.exists() or not ancestor_path.is_dir():
                continue
            discovered_directories[ancestor] = {
                "relative_path": ancestor,
                "name": _directory_display_name(ancestor_path, source["name"], ancestor),
                "parent_relative_path": None if ancestor == "" else _parent_path(ancestor),
                "last_scanned_at": now,
            }

        with connection(self._database_path) as conn, conn:
            existing_directories = {
                row["relative_path"]: row
                for row in conn.execute(
                    """
                    SELECT id, relative_path
                    FROM directories
                    WHERE source_id = ? AND (
                        relative_path = ? OR
                        relative_path LIKE ?
                    )
                    """,
                    (source["id"], subtree_prefix, _prefix_like(subtree_prefix)),
                ).fetchall()
            }
            all_directory_rows = conn.execute(
                "SELECT id, relative_path FROM directories WHERE source_id = ?",
                (source["id"],),
            ).fetchall()
            directory_ids_by_path = {row["relative_path"]: row["id"] for row in all_directory_rows}
            existing_directory_paths = set(directory_ids_by_path)
            existing_files = {
                row["relative_path"]: row
                for row in conn.execute(
                    """
                    SELECT id, directory_id, relative_path, path, size_bytes, modified_at,
                           conversion_state, preview_state, has_preview_assets,
                           last_converted_at, preview_generated_at
                    FROM files
                    WHERE source_id = ? AND (
                        relative_path = ? OR
                        relative_path LIKE ?
                    )
                    """,
                    (source["id"], subtree_prefix, _prefix_like(subtree_prefix)),
                ).fetchall()
            }

            for relative_path, data in sorted(discovered_directories.items(), key=lambda item: (item[0].count("/"), item[0])):
                directory_id = directory_ids_by_path.get(relative_path, str(uuid.uuid4()))
                directory_ids_by_path[relative_path] = directory_id
                if relative_path in existing_directory_paths:
                    conn.execute(
                        """
                        UPDATE directories
                        SET name = ?, parent_relative_path = ?, last_scanned_at = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (
                            data["name"],
                            data["parent_relative_path"],
                            data["last_scanned_at"],
                            now,
                            directory_id,
                        ),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO directories (
                            id, source_id, relative_path, name, parent_relative_path,
                            last_scanned_at, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            directory_id,
                            source["id"],
                            relative_path,
                            data["name"],
                            data["parent_relative_path"],
                            data["last_scanned_at"],
                            now,
                            now,
                        ),
                    )

            for relative_path, data in discovered_files.items():
                existing = existing_files.get(relative_path)
                directory_id = directory_ids_by_path[data["directory_relative_path"]]
                changed = (
                    existing is None
                    or existing["path"] != data["path"]
                    or existing["size_bytes"] != data["size_bytes"]
                    or existing["modified_at"] != data["modified_at"]
                )

                if existing is None:
                    conn.execute(
                        """
                        INSERT INTO files (
                            id, source_id, directory_id, relative_path, path, file_name, extension,
                            size_bytes, modified_at, discovered_at, last_scanned_at, is_video_supported,
                            conversion_state, preview_state, last_conversion_profile_id, last_converted_at,
                            preview_generated_at, has_preview_assets, last_error_code, last_error_message,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'not_started', 'not_started',
                                  NULL, NULL, NULL, 0, NULL, NULL, ?, ?)
                        """,
                        (
                            str(uuid.uuid4()),
                            source["id"],
                            directory_id,
                            data["relative_path"],
                            data["path"],
                            data["file_name"],
                            data["extension"],
                            data["size_bytes"],
                            data["modified_at"],
                            now,
                            data["last_scanned_at"],
                            int(data["is_video_supported"]),
                            now,
                            now,
                        ),
                    )
                    continue

                conversion_state = existing["conversion_state"]
                preview_state = existing["preview_state"]
                has_preview_assets = existing["has_preview_assets"]
                last_converted_at = existing["last_converted_at"]
                preview_generated_at = existing["preview_generated_at"]
                if changed:
                    conversion_state = "not_started"
                    preview_state = "not_started"
                    has_preview_assets = 0
                    last_converted_at = None
                    preview_generated_at = None

                conn.execute(
                    """
                    UPDATE files
                    SET directory_id = ?, path = ?, file_name = ?, extension = ?, size_bytes = ?,
                        modified_at = ?, last_scanned_at = ?, is_video_supported = ?,
                        conversion_state = ?, preview_state = ?, last_converted_at = ?,
                        preview_generated_at = ?, has_preview_assets = ?, last_error_code = NULL,
                        last_error_message = NULL, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        directory_id,
                        data["path"],
                        data["file_name"],
                        data["extension"],
                        data["size_bytes"],
                        data["modified_at"],
                        data["last_scanned_at"],
                        int(data["is_video_supported"]),
                        conversion_state,
                        preview_state,
                        last_converted_at,
                        preview_generated_at,
                        has_preview_assets,
                        now,
                        existing["id"],
                    ),
                )

            missing_files = sorted(set(existing_files) - set(discovered_files))
            for relative_path in missing_files:
                conn.execute(
                    "DELETE FROM files WHERE source_id = ? AND relative_path = ?",
                    (source["id"], relative_path),
                )

            missing_directories = sorted(
                (set(existing_directories) - set(discovered_directories)),
                key=lambda value: value.count("/"),
                reverse=True,
            )
            for relative_path in missing_directories:
                conn.execute(
                    "DELETE FROM directories WHERE source_id = ? AND relative_path = ?",
                    (source["id"], relative_path),
                )

        return {
            "directories_scanned": len(discovered_directories),
            "files_scanned": len(discovered_files),
        }

    def _require_active_source(self) -> dict:
        source = self._source_service.get_active_source()
        if source is None:
            raise ApiError("source_not_configured", "Configure an active source before scanning or browsing.", status=400)
        return source

    def _assert_root_directory_available(self, root_path: str) -> Path:
        path = Path(root_path)
        if not path.exists() or not path.is_dir():
            raise ApiError(
                "source_root_unavailable",
                "Configured source root path is not accessible from the backend machine.",
                status=400,
            )
        return path

    def _serialize_job_row(self, row) -> dict:
        return {
            "id": row["id"],
            "job_type": row["job_type"],
            "scope_type": row["scope_type"],
            "scope_ref": row["scope_ref"],
            "status": row["status"],
            "parameters": json.loads(row["parameters"]),
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "summary_message": row["summary_message"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


def normalize_relative_path(value: str | None) -> str:
    if value is None:
        return ""

    normalized = str(value).replace("\\", "/").strip().strip("/")
    if not normalized:
        return ""

    parts = [part for part in normalized.split("/") if part and part != "."]
    if any(part == ".." for part in parts):
        raise ApiError("invalid_path", "Relative paths must stay inside the active source.", status=400)
    return "/".join(parts)


def _ancestor_paths(path: str) -> list[str]:
    if not path:
        return [""]

    parts = path.split("/")
    results = [""]
    current = []
    for part in parts:
        current.append(part)
        results.append("/".join(current))
    return results


def _build_indicator(stats: dict, label: str) -> dict | None:
    total = stats["total"]
    if total == 0:
        return None

    done = stats["done"]
    failed = stats["failed"]
    in_progress = stats["in_progress"]
    pending = total - done - failed - in_progress

    if failed:
        state = "failed"
    elif in_progress:
        state = "in_progress"
    elif done == total:
        return None
    else:
        state = "not_started"

    return {
        "state": state,
        "total": total,
        "done": done,
        "pending": pending,
        "failed": failed,
        "message": f"{done} of {total} videos have completed {label}.",
    }


def _directory_display_name(path: Path, source_name: str, relative_path: str) -> str:
    if relative_path:
        return path.name
    return path.name or source_name or "Source root"


def _parent_path(relative_path: str) -> str:
    if not relative_path:
        return ""
    parent = PurePosixPath(relative_path).parent.as_posix()
    return "" if parent == "." else parent


def _prefix_like(prefix: str) -> str:
    return "%" if not prefix else f"{prefix}/%"


def _timestamp_from_stat(stat_result) -> str:
    return utc_now() if stat_result.st_mtime_ns == 0 else _timestamp_from_epoch(stat_result.st_mtime)


def _timestamp_from_epoch(value: float) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(value, UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _to_relative_path(root_path: Path, path: Path) -> str:
    relative = path.relative_to(root_path).as_posix()
    return "" if relative == "." else relative
