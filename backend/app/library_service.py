from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path, PurePosixPath

from .db import connection
from .errors import ApiError
from .time_utils import utc_now


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".wmv"}


class LibraryService:
    def __init__(self, database_path: Path, source_service, conversion_profile_service=None, *, ffprobe_binary: str = "ffprobe") -> None:
        self._database_path = database_path
        self._source_service = source_service
        self._conversion_profile_service = conversion_profile_service
        self._ffprobe_binary = ffprobe_binary

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
            directory_preview_rows = conn.execute(
                """
                SELECT directory_relative_path
                FROM preview_assets
                WHERE source_id = ? AND asset_kind = 'directory'
                """,
                (source["id"],),
            ).fetchall()

        directory_preview_paths = {row["directory_relative_path"] for row in directory_preview_rows}

        nodes_by_path: dict[str, dict] = {}
        for row in directory_rows:
            path = row["relative_path"]
            nodes_by_path[path] = {
                "id": path or "root",
                "name": row["name"] or source["name"],
                "path": path,
                "parent_path": row["parent_relative_path"],
                "has_preview_asset": path in directory_preview_paths,
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
                "has_preview_asset": "" in directory_preview_paths,
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
                           has_preview_assets, last_error_code, last_error_message,
                           generated_from_job_id, generated_from_file_id, generated_kind
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
                           has_preview_assets, last_error_code, last_error_message,
                           generated_from_job_id, generated_from_file_id, generated_kind
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
                "generated_from_job_id": row["generated_from_job_id"],
                "generated_from_file_id": row["generated_from_file_id"],
                "generated_kind": row["generated_kind"],
                "is_generated": bool(row["generated_kind"]),
            }
            for row in rows
        ]

    def get_file(self, file_id: str) -> dict:
        with connection(self._database_path) as conn:
            row = conn.execute(
                """
                SELECT id, relative_path, path, file_name, extension, size_bytes, modified_at,
                       discovered_at, last_scanned_at, is_video_supported, conversion_state, preview_state,
                       has_preview_assets, last_conversion_profile_id, last_converted_at, preview_generated_at,
                       last_error_code, last_error_message, generated_from_job_id,
                       generated_from_file_id, generated_kind
                FROM files
                WHERE id = ?
                """,
                (file_id,),
            ).fetchone()
        if row is None:
            raise ApiError("file_not_found", "Requested file does not exist.", status=404)
        media_info = self._probe_media_info(Path(row["path"]))
        last_conversion_profile = self._resolve_last_conversion_profile(row["last_conversion_profile_id"])
        return {
            "id": row["id"],
            "relative_path": row["relative_path"],
            "path": row["path"],
            "file_name": row["file_name"],
            "extension": row["extension"],
            "size_bytes": row["size_bytes"],
            "modified_at": row["modified_at"],
            "discovered_at": row["discovered_at"],
            "last_scanned_at": row["last_scanned_at"],
            "is_video_supported": bool(row["is_video_supported"]),
            "conversion_state": row["conversion_state"],
            "preview_state": row["preview_state"],
            "has_preview_assets": bool(row["has_preview_assets"]),
            "last_conversion_profile_id": row["last_conversion_profile_id"],
            "last_conversion_profile": last_conversion_profile,
            "last_converted_at": row["last_converted_at"],
            "preview_generated_at": row["preview_generated_at"],
            "last_error_code": row["last_error_code"],
            "last_error_message": row["last_error_message"],
            "generated_from_job_id": row["generated_from_job_id"],
            "generated_from_file_id": row["generated_from_file_id"],
            "generated_kind": row["generated_kind"],
            "is_generated": bool(row["generated_kind"]),
            "media_info": media_info,
        }

    def register_generated_file(
        self,
        *,
        result: dict,
        source_file_id: str,
        generated_from_job_id: str,
        generated_kind: str,
        profile_id: str | None = None,
    ) -> dict:
        source = self._require_active_source()
        root_path = self._assert_root_directory_available(source["root_path"])
        relative_path = normalize_relative_path(result["relative_path"])
        file_path = Path(result["path"])
        if not file_path.exists() or not file_path.is_file():
            raise ApiError("generated_file_missing", "Generated output file is no longer available on disk.", status=404)

        now = utc_now()
        directory_relative_path = _parent_path(relative_path)
        stat_result = file_path.stat()
        with connection(self._database_path) as conn, conn:
            directory_id = self._ensure_directory_row(
                conn,
                source_id=source["id"],
                source_name=source["name"],
                root_path=root_path,
                directory_relative_path=directory_relative_path,
                now=now,
            )
            existing = conn.execute(
                """
                SELECT id
                FROM files
                WHERE source_id = ? AND relative_path = ?
                """,
                (source["id"], relative_path),
            ).fetchone()
            file_id = existing["id"] if existing is not None else str(uuid.uuid4())
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO files (
                        id, source_id, directory_id, relative_path, path, file_name, extension,
                        size_bytes, modified_at, discovered_at, last_scanned_at, is_video_supported,
                        conversion_state, preview_state, last_conversion_profile_id, last_converted_at,
                        preview_generated_at, has_preview_assets, last_error_code, last_error_message,
                        generated_from_job_id, generated_from_file_id, generated_kind,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'done', 'not_started', ?, ?, NULL, 0, NULL, NULL, ?, ?, ?, ?, ?)
                    """,
                    (
                        file_id,
                        source["id"],
                        directory_id,
                        relative_path,
                        str(file_path),
                        file_path.name,
                        file_path.suffix.lower(),
                        int(stat_result.st_size),
                        _timestamp_from_stat(stat_result),
                        now,
                        now,
                        int(file_path.suffix.lower() in VIDEO_EXTENSIONS),
                        profile_id,
                        now,
                        generated_from_job_id,
                        source_file_id,
                        generated_kind,
                        now,
                        now,
                    ),
                )
            else:
                self._delete_preview_assets_for_file(conn, file_id)
                conn.execute(
                    """
                    UPDATE files
                    SET directory_id = ?, relative_path = ?, path = ?, file_name = ?, extension = ?,
                        size_bytes = ?, modified_at = ?, last_scanned_at = ?, is_video_supported = ?,
                        conversion_state = 'done', preview_state = 'not_started', last_conversion_profile_id = ?,
                        last_converted_at = ?, preview_generated_at = NULL, has_preview_assets = 0,
                        keyframe_timestamps = NULL, large_tile_timestamps = NULL, face_detection_summary = NULL,
                        body_detection_summary = NULL, preview_asset_path = NULL, last_error_code = NULL,
                        last_error_message = NULL, generated_from_job_id = ?, generated_from_file_id = ?,
                        generated_kind = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        directory_id,
                        relative_path,
                        str(file_path),
                        file_path.name,
                        file_path.suffix.lower(),
                        int(stat_result.st_size),
                        _timestamp_from_stat(stat_result),
                        now,
                        int(file_path.suffix.lower() in VIDEO_EXTENSIONS),
                        profile_id,
                        now,
                        generated_from_job_id,
                        source_file_id,
                        generated_kind,
                        now,
                        file_id,
                    ),
                )

        return self.get_file(file_id)

    def move_file(self, file_id: str, destination_directory: str) -> dict:
        source = self._require_active_source()
        root_path = self._assert_root_directory_available(source["root_path"])
        normalized_directory = normalize_relative_path(destination_directory)
        with connection(self._database_path) as conn, conn:
            row = conn.execute(
                """
                SELECT id, source_id, relative_path, path, file_name, generated_from_job_id,
                       generated_from_file_id, generated_kind
                FROM files
                WHERE id = ?
                """,
                (file_id,),
            ).fetchone()
            if row is None:
                raise ApiError("file_not_found", "Requested file does not exist.", status=404)
            source_path = Path(row["path"])
            if not source_path.exists() or not source_path.is_file():
                raise ApiError("file_missing", "Requested file is no longer available on disk.", status=404)
            target_directory = root_path / Path(normalized_directory) if normalized_directory else root_path
            target_directory.mkdir(parents=True, exist_ok=True)
            target_path = target_directory / row["file_name"]
            if target_path.exists() and target_path.resolve() != source_path.resolve():
                raise ApiError("file_conflict", "A file with the same name already exists in the destination folder.", status=409)

            os.replace(source_path, target_path)
            self._delete_preview_assets_for_file(conn, file_id)

            directory_id = self._ensure_directory_row(
                conn,
                source_id=source["id"],
                source_name=source["name"],
                root_path=root_path,
                directory_relative_path=normalized_directory,
                now=utc_now(),
            )
            stat_result = target_path.stat()
            conn.execute(
                """
                UPDATE files
                SET directory_id = ?, relative_path = ?, path = ?, modified_at = ?, last_scanned_at = ?,
                    preview_state = 'not_started', preview_generated_at = NULL, has_preview_assets = 0,
                    keyframe_timestamps = NULL, large_tile_timestamps = NULL, face_detection_summary = NULL,
                    body_detection_summary = NULL, preview_asset_path = NULL, updated_at = ?
                WHERE id = ?
                """,
                (
                    directory_id,
                    _to_relative_path(root_path, target_path),
                    str(target_path),
                    _timestamp_from_stat(stat_result),
                    utc_now(),
                    utc_now(),
                    file_id,
                ),
            )
        return self.get_file(file_id)

    def delete_file(self, file_id: str) -> None:
        with connection(self._database_path) as conn, conn:
            row = conn.execute(
                """
                SELECT id, path
                FROM files
                WHERE id = ?
                """,
                (file_id,),
            ).fetchone()
            if row is None:
                raise ApiError("file_not_found", "Requested file does not exist.", status=404)

            file_path = Path(row["path"])
            if file_path.exists() and file_path.is_file():
                file_path.unlink()
            self._delete_preview_assets_for_file(conn, file_id)
            conn.execute("DELETE FROM files WHERE id = ?", (file_id,))

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
                           last_converted_at, preview_generated_at, preview_asset_path,
                           generated_from_job_id, generated_from_file_id, generated_kind
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
                            generated_from_job_id, generated_from_file_id, generated_kind,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'not_started', 'not_started',
                                  NULL, NULL, NULL, 0, NULL, NULL, NULL, NULL, NULL, ?, ?)
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
                preview_asset_path = existing["preview_asset_path"]
                generated_from_job_id = existing["generated_from_job_id"]
                generated_from_file_id = existing["generated_from_file_id"]
                generated_kind = existing["generated_kind"]
                if changed:
                    conversion_state = "not_started"
                    preview_state = "not_started"
                    has_preview_assets = 0
                    last_converted_at = None
                    preview_generated_at = None
                    preview_asset_path = None
                    conn.execute("DELETE FROM preview_assets WHERE asset_kind = 'file' AND file_id = ?", (existing["id"],))
                    conn.execute("DELETE FROM file_tags WHERE file_id = ?", (existing["id"],))

                conn.execute(
                    """
                    UPDATE files
                    SET directory_id = ?, path = ?, file_name = ?, extension = ?, size_bytes = ?,
                        modified_at = ?, last_scanned_at = ?, is_video_supported = ?,
                        conversion_state = ?, preview_state = ?, last_converted_at = ?,
                        preview_generated_at = ?, has_preview_assets = ?, keyframe_timestamps = CASE WHEN ? THEN NULL ELSE keyframe_timestamps END,
                        large_tile_timestamps = CASE WHEN ? THEN NULL ELSE large_tile_timestamps END,
                        face_detection_summary = CASE WHEN ? THEN NULL ELSE face_detection_summary END,
                        body_detection_summary = CASE WHEN ? THEN NULL ELSE body_detection_summary END,
                        preview_asset_path = ?, tagging_updated_at = CASE WHEN ? THEN NULL ELSE tagging_updated_at END,
                        tagging_model_info = CASE WHEN ? THEN NULL ELSE tagging_model_info END, last_error_code = NULL,
                        last_error_message = NULL, generated_from_job_id = ?, generated_from_file_id = ?,
                        generated_kind = ?, updated_at = ?
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
                        int(changed),
                        int(changed),
                        int(changed),
                        int(changed),
                        preview_asset_path,
                        int(changed),
                        int(changed),
                        generated_from_job_id,
                        generated_from_file_id,
                        generated_kind,
                        now,
                        existing["id"],
                    ),
                )

            missing_files = sorted(set(existing_files) - set(discovered_files))
            for relative_path in missing_files:
                file_row = existing_files[relative_path]
                conn.execute("DELETE FROM preview_assets WHERE asset_kind = 'file' AND file_id = ?", (file_row["id"],))
                conn.execute("DELETE FROM file_tags WHERE file_id = ?", (file_row["id"],))
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

            if subtree_prefix:
                conn.execute(
                    """
                    DELETE FROM preview_assets
                    WHERE asset_kind = 'directory' AND source_id = ?
                      AND (directory_relative_path = ? OR directory_relative_path LIKE ?)
                    """,
                    (source["id"], subtree_prefix, f"{subtree_prefix}/%"),
                )
            else:
                conn.execute(
                    "DELETE FROM preview_assets WHERE asset_kind = 'directory' AND source_id = ?",
                    (source["id"],),
                )

        return {
            "directories_scanned": len(discovered_directories),
            "files_scanned": len(discovered_files),
        }

    def _ensure_directory_row(self, conn, *, source_id: str, source_name: str, root_path: Path, directory_relative_path: str, now: str) -> str:
        directory_ids: dict[str, str] = {}
        rows = conn.execute("SELECT id, relative_path FROM directories WHERE source_id = ?", (source_id,)).fetchall()
        for row in rows:
            directory_ids[row["relative_path"]] = row["id"]

        for relative_path in _ancestor_paths(directory_relative_path):
            if relative_path in directory_ids:
                continue
            directory_path = root_path / Path(relative_path) if relative_path else root_path
            directory_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO directories (
                    id, source_id, relative_path, name, parent_relative_path,
                    last_scanned_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    directory_id,
                    source_id,
                    relative_path,
                    _directory_display_name(directory_path, source_name, relative_path),
                    None if relative_path == "" else _parent_path(relative_path),
                    now,
                    now,
                    now,
                ),
            )
            directory_ids[relative_path] = directory_id
        return directory_ids[directory_relative_path]

    def _delete_preview_assets_for_file(self, conn, file_id: str) -> None:
        rows = conn.execute(
            """
            SELECT image_path, metadata
            FROM preview_assets
            WHERE asset_kind = 'file' AND file_id = ?
            """,
            (file_id,),
        ).fetchall()
        for row in rows:
            image_path = row["image_path"]
            if image_path:
                path = Path(image_path)
                if path.exists() and path.is_file():
                    path.unlink()
            metadata = json.loads(row["metadata"] or "{}")
            card_gif_path = metadata.get("card_gif_path")
            if isinstance(card_gif_path, str) and card_gif_path:
                path = Path(card_gif_path)
                if path.exists() and path.is_file():
                    path.unlink()
        conn.execute("DELETE FROM preview_assets WHERE asset_kind = 'file' AND file_id = ?", (file_id,))


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

    def _resolve_last_conversion_profile(self, profile_id: str | None) -> dict | None:
        if not profile_id or self._conversion_profile_service is None:
            return None
        try:
            return self._conversion_profile_service.get_profile(profile_id)
        except ApiError:
            return None

    def _probe_media_info(self, file_path: Path) -> dict | None:
        if shutil.which(self._ffprobe_binary) is None or not file_path.exists():
            return None

        command = [
            self._ffprobe_binary,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_entries",
            "format=duration,bit_rate,size:stream=index,codec_type,codec_name,profile,width,height,display_aspect_ratio,bit_rate,avg_frame_rate,pix_fmt",
            str(file_path),
        ]
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=False)
        except OSError:
            return None

        if result.returncode != 0:
            return None

        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return None

        streams = payload.get("streams")
        format_info = payload.get("format")
        if not isinstance(streams, list) or not isinstance(format_info, dict):
            return None

        video_stream = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        audio_stream = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
        if not isinstance(video_stream, dict):
            return None

        width = _safe_int(video_stream.get("width"))
        height = _safe_int(video_stream.get("height"))
        stream_bitrate = _safe_int(video_stream.get("bit_rate"))
        format_bitrate = _safe_int(format_info.get("bit_rate"))
        size_bytes = _safe_int(format_info.get("size"))

        return {
            "video_codec": _safe_string(video_stream.get("codec_name")),
            "video_profile": _safe_string(video_stream.get("profile")),
            "audio_codec": _safe_string(audio_stream.get("codec_name")) if isinstance(audio_stream, dict) else None,
            "width": width,
            "height": height,
            "display_aspect_ratio": _safe_string(video_stream.get("display_aspect_ratio")),
            "frame_rate": _parse_frame_rate(video_stream.get("avg_frame_rate")),
            "pixel_format": _safe_string(video_stream.get("pix_fmt")),
            "duration_seconds": _safe_float(format_info.get("duration")),
            "bitrate_bps": stream_bitrate or format_bitrate,
            "size_bytes": size_bytes,
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


def _safe_string(value) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _safe_int(value) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _safe_float(value) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _parse_frame_rate(value) -> float | None:
    if value in (None, "", "0/0"):
        return None
    text = str(value)
    if "/" in text:
        numerator_text, denominator_text = text.split("/", 1)
        try:
            numerator = float(numerator_text)
            denominator = float(denominator_text)
        except ValueError:
            return None
        if denominator == 0:
            return None
        return round(numerator / denominator, 3)
    return _safe_float(text)
