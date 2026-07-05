from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from .conversion_profile_service import ConversionProfileService
from .conversion_service import ConversionService
from .db import connection
from .errors import ApiError
from .library_service import LibraryService, normalize_relative_path
from .source_service import SourceService
from .time_utils import utc_now


SUPPORTED_JOB_TYPES = {"scan", "rescan", "convert", "preview", "tag", "tune"}
RESTARTABLE_JOB_STATUSES = {"completed", "failed", "cancelled"}
TERMINAL_JOB_STATUSES = {"completed", "failed", "cancelled"}


class _JobCancelled(Exception):
    pass


class JobService:
    def __init__(
        self,
        database_path: Path,
        source_service: SourceService,
        library_service: LibraryService,
        conversion_profile_service: ConversionProfileService,
        conversion_service: ConversionService,
    ) -> None:
        self._database_path = database_path
        self._source_service = source_service
        self._library_service = library_service
        self._conversion_profile_service = conversion_profile_service
        self._conversion_service = conversion_service
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()
        self._worker_thread: threading.Thread | None = None

    def start(self) -> None:
        self._repair_interrupted_jobs()
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._worker_thread = threading.Thread(target=self._worker_loop, name="video-archive-job-worker", daemon=True)
        self._worker_thread.start()

    def shutdown(self, timeout: float = 5) -> None:
        self._stop_event.set()
        self._wake_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=timeout)

    def wait_for_shutdown(self, timeout: float) -> bool:
        return self._stop_event.wait(timeout=timeout)

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

    def list_jobs(
        self,
        *,
        status: str | None = None,
        job_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        safe_limit = max(1, min(limit, 100))
        safe_offset = max(0, offset)
        clauses: list[str] = []
        params: list[object] = []

        if status is not None:
            clauses.append("jobs.status = ?")
            params.append(status)
        if job_type is not None:
            clauses.append("jobs.job_type = ?")
            params.append(job_type)

        where_sql = ""
        if clauses:
            where_sql = f"WHERE {' AND '.join(clauses)}"

        with connection(self._database_path) as conn:
            rows = conn.execute(
                f"""
                SELECT jobs.id, jobs.job_type, jobs.scope_type, jobs.scope_ref, jobs.status,
                       jobs.requested_by, jobs.parameters, jobs.started_at, jobs.finished_at,
                       jobs.summary_message, jobs.cancel_requested_at, jobs.created_at, jobs.updated_at,
                       COALESCE(SUM(CASE WHEN job_items.status = 'queued' THEN 1 ELSE 0 END), 0) AS queued_items,
                       COALESCE(SUM(CASE WHEN job_items.status = 'running' THEN 1 ELSE 0 END), 0) AS running_items,
                       COALESCE(SUM(CASE WHEN job_items.status = 'completed' THEN 1 ELSE 0 END), 0) AS completed_items,
                       COALESCE(SUM(CASE WHEN job_items.status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_items,
                       COALESCE(SUM(CASE WHEN job_items.status = 'cancelled' THEN 1 ELSE 0 END), 0) AS cancelled_items,
                       COALESCE(SUM(CASE WHEN job_items.status = 'skipped' THEN 1 ELSE 0 END), 0) AS skipped_items,
                       COUNT(job_items.id) AS total_items
                FROM jobs
                LEFT JOIN job_items ON job_items.job_id = jobs.id
                {where_sql}
                GROUP BY jobs.id
                ORDER BY jobs.created_at DESC, jobs.id DESC
                LIMIT ? OFFSET ?
                """,
                (*params, safe_limit, safe_offset),
            ).fetchall()

        return [self._serialize_job_row(row) for row in rows]

    def get_job(self, job_id: str) -> dict:
        with connection(self._database_path) as conn:
            row = conn.execute(
                """
                SELECT jobs.id, jobs.job_type, jobs.scope_type, jobs.scope_ref, jobs.status,
                       jobs.requested_by, jobs.parameters, jobs.started_at, jobs.finished_at,
                       jobs.summary_message, jobs.cancel_requested_at, jobs.created_at, jobs.updated_at,
                       COALESCE(SUM(CASE WHEN job_items.status = 'queued' THEN 1 ELSE 0 END), 0) AS queued_items,
                       COALESCE(SUM(CASE WHEN job_items.status = 'running' THEN 1 ELSE 0 END), 0) AS running_items,
                       COALESCE(SUM(CASE WHEN job_items.status = 'completed' THEN 1 ELSE 0 END), 0) AS completed_items,
                       COALESCE(SUM(CASE WHEN job_items.status = 'failed' THEN 1 ELSE 0 END), 0) AS failed_items,
                       COALESCE(SUM(CASE WHEN job_items.status = 'cancelled' THEN 1 ELSE 0 END), 0) AS cancelled_items,
                       COALESCE(SUM(CASE WHEN job_items.status = 'skipped' THEN 1 ELSE 0 END), 0) AS skipped_items,
                       COUNT(job_items.id) AS total_items
                FROM jobs
                LEFT JOIN job_items ON job_items.job_id = jobs.id
                WHERE jobs.id = ?
                GROUP BY jobs.id
                """,
                (job_id,),
            ).fetchone()

        if row is None:
            raise ApiError("job_not_found", "Requested job does not exist.", status=404)
        return self._serialize_job_row(row)

    def list_job_items(self, job_id: str) -> list[dict]:
        self.get_job(job_id)
        with connection(self._database_path) as conn:
            rows = conn.execute(
                """
                SELECT job_items.id, job_items.job_id, job_items.file_id, job_items.item_key,
                       job_items.status, job_items.step_name, job_items.message, job_items.started_at,
                       job_items.finished_at, job_items.output_ref, files.file_name, files.relative_path
                FROM job_items
                LEFT JOIN files ON files.id = job_items.file_id
                WHERE job_items.job_id = ?
                ORDER BY job_items.rowid ASC
                """,
                (job_id,),
            ).fetchall()

        return [self._serialize_job_item_row(row) for row in rows]

    def list_events(
        self,
        *,
        job_id: str | None = None,
        file_id: str | None = None,
        level: str | None = None,
        limit: int = 100,
        after_stream_id: int | None = None,
    ) -> list[dict]:
        safe_limit = max(1, min(limit, 500))
        clauses: list[str] = []
        params: list[object] = []

        if job_id is not None:
            clauses.append("job_id = ?")
            params.append(job_id)
        if file_id is not None:
            clauses.append("file_id = ?")
            params.append(file_id)
        if level is not None:
            clauses.append("level = ?")
            params.append(level)
        if after_stream_id is not None:
            clauses.append("rowid > ?")
            params.append(after_stream_id)

        where_sql = ""
        if clauses:
            where_sql = f"WHERE {' AND '.join(clauses)}"

        with connection(self._database_path) as conn:
            rows = conn.execute(
                f"""
                SELECT rowid AS stream_id, id, job_id, file_id, level, event_type, message, payload, created_at
                FROM app_events
                {where_sql}
                ORDER BY rowid DESC
                LIMIT ?
                """,
                (*params, safe_limit),
            ).fetchall()

        ordered_rows = list(reversed(rows))
        return [self._serialize_event_row(row) for row in ordered_rows]

    def create_scan_job(self) -> dict:
        self._require_active_source()
        return self._create_job(
            job_type="scan",
            scope_type="source",
            scope_ref="",
            parameters={"relative_path": "", "recursive": True},
            item_specs=[{"item_key": "active-source", "message": "Waiting to scan the active source."}],
        )

    def create_rescan_job(self, relative_path: str) -> dict:
        self._require_active_source()
        normalized_path = normalize_relative_path(relative_path)
        scope_type = "source" if normalized_path == "" else "directory"
        scope_ref = normalized_path
        item_key = normalized_path or "active-source"
        message = "Waiting to rescan the active source." if normalized_path == "" else f"Waiting to rescan {normalized_path}."
        return self._create_job(
            job_type="rescan",
            scope_type=scope_type,
            scope_ref=scope_ref,
            parameters={"relative_path": normalized_path, "recursive": True},
            item_specs=[{"item_key": item_key, "message": message}],
        )

    def create_convert_directory_job(self, relative_path: str, *, profile_id: str | None = None, mode: str = "production") -> dict:
        normalized_path = normalize_relative_path(relative_path)
        profile = self._conversion_profile_service.resolve_profile(profile_id)
        item_specs = self._build_directory_item_specs(normalized_path)
        return self._create_job(
            job_type="convert",
            scope_type="directory",
            scope_ref=normalized_path,
            parameters={
                "relative_path": normalized_path,
                "recursive": True,
                "mode": mode,
                "profile_id": profile["id"],
                "profile": profile,
            },
            item_specs=item_specs,
        )

    def create_preview_directory_job(self, relative_path: str) -> dict:
        normalized_path = normalize_relative_path(relative_path)
        item_specs = self._build_directory_item_specs(normalized_path)
        return self._create_job(
            job_type="preview",
            scope_type="directory",
            scope_ref=normalized_path,
            parameters={"relative_path": normalized_path, "recursive": True},
            item_specs=item_specs,
        )

    def create_tag_directory_job(self, relative_path: str) -> dict:
        normalized_path = normalize_relative_path(relative_path)
        item_specs = self._build_directory_item_specs(normalized_path)
        return self._create_job(
            job_type="tag",
            scope_type="directory",
            scope_ref=normalized_path,
            parameters={"relative_path": normalized_path, "recursive": True},
            item_specs=item_specs,
        )

    def create_convert_file_job(self, file_id: str, *, profile_id: str | None = None, mode: str = "production") -> dict:
        file_row = self._require_file(file_id)
        profile = self._conversion_profile_service.resolve_profile(profile_id)
        return self._create_job(
            job_type="convert",
            scope_type="file",
            scope_ref=file_id,
            parameters={
                "file_id": file_id,
                "relative_path": file_row["relative_path"],
                "mode": mode,
                "profile_id": profile["id"],
                "profile": profile,
            },
            item_specs=[self._file_item_spec(file_row)],
        )

    def create_preview_file_job(self, file_id: str) -> dict:
        file_row = self._require_file(file_id)
        return self._create_job(
            job_type="preview",
            scope_type="file",
            scope_ref=file_id,
            parameters={"file_id": file_id, "relative_path": file_row["relative_path"]},
            item_specs=[self._file_item_spec(file_row)],
        )

    def create_tag_file_job(self, file_id: str) -> dict:
        file_row = self._require_file(file_id)
        return self._create_job(
            job_type="tag",
            scope_type="file",
            scope_ref=file_id,
            parameters={"file_id": file_id, "relative_path": file_row["relative_path"]},
            item_specs=[self._file_item_spec(file_row)],
        )

    def create_tune_file_job(self, file_id: str, sweep: dict | None = None) -> dict:
        file_row = self._require_file(file_id)
        return self._create_job(
            job_type="tune",
            scope_type="file",
            scope_ref=file_id,
            parameters={"file_id": file_id, "relative_path": file_row["relative_path"], "sweep": sweep or {}},
            item_specs=[self._file_item_spec(file_row)],
        )

    def cancel_job(self, job_id: str) -> dict:
        now = utc_now()
        with connection(self._database_path) as conn, conn:
            row = conn.execute(
                "SELECT id, status, job_type FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if row is None:
                raise ApiError("job_not_found", "Requested job does not exist.", status=404)
            if row["status"] in TERMINAL_JOB_STATUSES:
                raise ApiError("job_not_cancellable", "Only queued or running jobs can be cancelled.", status=409)

            if row["status"] == "queued":
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'cancelled', cancel_requested_at = ?, finished_at = ?,
                        summary_message = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, "Cancelled before execution started.", now, job_id),
                )
                conn.execute(
                    """
                    UPDATE job_items
                    SET status = 'cancelled', message = ?, finished_at = ?, started_at = COALESCE(started_at, ?)
                    WHERE job_id = ? AND status = 'queued'
                    """,
                    ("Cancelled before execution started.", now, now, job_id),
                )
                self._insert_event(conn, job_id=job_id, level="warning", event_type="job.cancelled", message="Job cancelled before execution started.")
            else:
                conn.execute(
                    """
                    UPDATE jobs
                    SET cancel_requested_at = ?, summary_message = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, "Cancellation requested.", now, job_id),
                )
                self._insert_event(conn, job_id=job_id, level="warning", event_type="job.cancel_requested", message="Cancellation requested for running job.")

        self._wake_event.set()
        return self.get_job(job_id)

    def restart_job(self, job_id: str) -> dict:
        job = self.get_job(job_id)
        if job["status"] not in RESTARTABLE_JOB_STATUSES:
            raise ApiError("job_not_restartable", "Only completed, failed, or cancelled jobs can be restarted.", status=409)

        job_type = job["job_type"]
        parameters = job["parameters"]
        if job_type == "scan":
            return self.create_scan_job()
        if job_type == "rescan":
            return self.create_rescan_job(parameters.get("relative_path", ""))
        if job_type == "convert":
            if job["scope_type"] == "file":
                return self.create_convert_file_job(
                    parameters["file_id"],
                    profile_id=parameters.get("profile_id"),
                    mode=parameters.get("mode", "production"),
                )
            return self.create_convert_directory_job(
                parameters.get("relative_path", ""),
                profile_id=parameters.get("profile_id"),
                mode=parameters.get("mode", "production"),
            )
        if job_type == "preview":
            if job["scope_type"] == "file":
                return self.create_preview_file_job(parameters["file_id"])
            return self.create_preview_directory_job(parameters.get("relative_path", ""))
        if job_type == "tag":
            if job["scope_type"] == "file":
                return self.create_tag_file_job(parameters["file_id"])
            return self.create_tag_directory_job(parameters.get("relative_path", ""))
        if job_type == "tune":
            return self.create_tune_file_job(parameters["file_id"], parameters.get("sweep"))
        raise ApiError("job_not_restartable", "This job type cannot be restarted in the current implementation.", status=409)

    def _create_job(
        self,
        *,
        job_type: str,
        scope_type: str,
        scope_ref: str,
        parameters: dict,
        item_specs: list[dict],
    ) -> dict:
        now = utc_now()
        job_id = str(uuid.uuid4())
        summary_message = f"Queued {job_type} job."
        with connection(self._database_path) as conn, conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, job_type, scope_type, scope_ref, status, requested_by, parameters,
                    started_at, finished_at, summary_message, cancel_requested_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'queued', NULL, ?, NULL, NULL, ?, NULL, ?, ?)
                """,
                (job_id, job_type, scope_type, scope_ref, json.dumps(parameters), summary_message, now, now),
            )
            for item_spec in item_specs or [{"item_key": scope_ref or "scope", "message": "Queued."}]:
                conn.execute(
                    """
                    INSERT INTO job_items (
                        id, job_id, file_id, item_key, status, step_name, message,
                        started_at, finished_at, output_ref
                    ) VALUES (?, ?, ?, ?, 'queued', ?, ?, NULL, NULL, NULL)
                    """,
                    (
                        str(uuid.uuid4()),
                        job_id,
                        item_spec.get("file_id"),
                        item_spec.get("item_key"),
                        item_spec.get("step_name"),
                        item_spec.get("message"),
                    ),
                )
            self._insert_event(conn, job_id=job_id, level="info", event_type="job.queued", message=summary_message, payload=parameters)

        self._wake_event.set()
        return self.get_job(job_id)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            job = self._claim_next_job()
            if job is None:
                self._wake_event.wait(timeout=1)
                self._wake_event.clear()
                continue
            self._execute_job(job)

    def _claim_next_job(self) -> dict | None:
        now = utc_now()
        with connection(self._database_path) as conn, conn:
            row = conn.execute(
                """
                SELECT id
                FROM jobs
                WHERE status = 'queued'
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None

            updated = conn.execute(
                """
                UPDATE jobs
                SET status = 'running', started_at = COALESCE(started_at, ?), updated_at = ?
                WHERE id = ? AND status = 'queued'
                """,
                (now, now, row["id"]),
            )
            if updated.rowcount != 1:
                return None
            self._insert_event(conn, job_id=row["id"], level="info", event_type="job.started", message="Job started.")

        return self.get_job(row["id"])

    def _execute_job(self, job: dict) -> None:
        try:
            if self._job_cancel_requested(job["id"]):
                raise _JobCancelled()

            if job["job_type"] in {"scan", "rescan"}:
                summary_message = self._execute_scan_job(job)
            elif job["job_type"] == "convert":
                summary_message = self._execute_convert_job(job)
            else:
                summary_message = self._execute_placeholder_job(job)
            self._complete_job(job["id"], summary_message)
        except _JobCancelled:
            self._cancel_running_job(job["id"], "Job cancelled.")
        except ApiError as exc:
            self._fail_job(job["id"], exc.message)
        except Exception as exc:  # pragma: no cover - defensive fallback
            self._fail_job(job["id"], f"Unexpected job failure: {exc}")

    def _execute_scan_job(self, job: dict) -> str:
        source = self._require_active_source()
        relative_path = normalize_relative_path(job["parameters"].get("relative_path"))
        items = self.list_job_items(job["id"])
        if items:
            self._set_job_item_status(items[0]["id"], "running", f"Scanning {relative_path or 'active source'}...")
        summary = self._library_service.scan_source(source, relative_path)
        if items:
            self._set_job_item_status(
                items[0]["id"],
                "completed",
                f"Scanned {summary['directories_scanned']} directories and {summary['files_scanned']} files.",
            )

        finished_at = utc_now()
        with connection(self._database_path) as conn, conn:
            conn.execute(
                "UPDATE sources SET last_scan_at = ?, updated_at = ? WHERE id = ?",
                (finished_at, finished_at, source["id"]),
            )
            self._insert_event(
                conn,
                job_id=job["id"],
                level="info",
                event_type="scan.completed",
                message=f"Scanned {summary['directories_scanned']} directories and {summary['files_scanned']} files.",
            )

        return f"Scanned {summary['directories_scanned']} directories and {summary['files_scanned']} files."

    def _execute_convert_job(self, job: dict) -> str:
        source = self._require_active_source()
        profile = job["parameters"].get("profile")
        if not isinstance(profile, dict):
            profile = self._conversion_profile_service.resolve_profile(job["parameters"].get("profile_id"))
        mode = job["parameters"].get("mode", "production")
        items = self.list_job_items(job["id"])
        completed = 0
        failed = 0

        for item in items:
            if self._job_cancel_requested(job["id"]):
                raise _JobCancelled()
            if not item["file_id"]:
                self._set_job_item_status(item["id"], "skipped", item["message"] or "No eligible file found.")
                continue

            file_row = self._get_file_for_conversion(item["file_id"])
            item_label = file_row["relative_path"]
            self._set_job_item_status(item["id"], "running", f"Converting {item_label} with profile {profile['name']}...")
            self._set_file_conversion_state(
                file_id=file_row["id"],
                state="in_progress",
                profile_id=profile["id"],
                error_code=None,
                error_message=None,
            )
            self._append_event(
                job_id=job["id"],
                file_id=file_row["id"],
                level="info",
                event_type="convert.item.started",
                message=f"Started {mode} conversion for {item_label} using profile {profile['name']}.",
                payload={"mode": mode, "profile_id": profile["id"]},
            )
            try:
                result = self._conversion_service.convert_file(
                    source_root=source["root_path"],
                    file_row=file_row,
                    profile=profile,
                    mode=mode,
                )
            except ApiError as exc:
                failed += 1
                self._set_job_item_status(item["id"], "failed", exc.message)
                self._set_file_conversion_state(
                    file_id=file_row["id"],
                    state="failed",
                    profile_id=profile["id"],
                    error_code=exc.code,
                    error_message=exc.message,
                )
                self._append_event(
                    job_id=job["id"],
                    file_id=file_row["id"],
                    level="error",
                    event_type="convert.item.failed",
                    message=f"Conversion failed for {item_label}: {exc.message}",
                    payload={"mode": mode, "profile_id": profile["id"], "error_code": exc.code},
                )
                continue

            self._record_successful_conversion(
                file_id=file_row["id"],
                result=result,
                profile_id=profile["id"],
            )
            self._set_job_item_status(
                item["id"],
                "completed",
                f"{mode.capitalize()} conversion completed for {result['relative_path']}.",
                output_ref=result["output_ref"],
            )
            self._append_event(
                job_id=job["id"],
                file_id=file_row["id"],
                level="info",
                event_type="convert.item.completed",
                message=f"Completed {mode} conversion for {result['relative_path']}.",
                payload={"mode": mode, "profile_id": profile["id"], "output_ref": result["output_ref"]},
            )
            completed += 1

        if failed:
            raise ApiError("conversion_job_failed", f"Conversion failed for {failed} item(s); {completed} completed successfully.", status=500)
        if completed == 0:
            return "Conversion job completed with no eligible files."
        return f"Conversion job completed for {completed} item(s) in {mode} mode using profile {profile['name']}."

    def _execute_placeholder_job(self, job: dict) -> str:
        items = self.list_job_items(job["id"])
        processed = 0
        for item in items:
            if self._job_cancel_requested(job["id"]):
                raise _JobCancelled()

            item_label = item["relative_path"] or item["item_key"] or "scope item"
            self._set_job_item_status(item["id"], "running", f"Preparing {job['job_type']} placeholder for {item_label}.")
            self._append_event(
                job_id=job["id"],
                file_id=item["file_id"],
                level="info",
                event_type=f"{job['job_type']}.item.started",
                message=f"Started placeholder {job['job_type']} work for {item_label}.",
            )
            self._set_job_item_status(
                item["id"],
                "completed",
                f"Placeholder {job['job_type']} workflow completed without heavy processing.",
            )
            self._append_event(
                job_id=job["id"],
                file_id=item["file_id"],
                level="info",
                event_type=f"{job['job_type']}.item.completed",
                message=f"Completed placeholder {job['job_type']} work for {item_label}.",
            )
            processed += 1

        if processed == 0:
            return f"{job['job_type'].capitalize()} job completed with no eligible items."
        return f"{job['job_type'].capitalize()} job completed for {processed} item(s). Heavy processing is not implemented yet."

    def _complete_job(self, job_id: str, message: str) -> None:
        now = utc_now()
        with connection(self._database_path) as conn, conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'completed', finished_at = ?, summary_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, message, now, job_id),
            )
            self._insert_event(conn, job_id=job_id, level="info", event_type="job.completed", message=message)

    def _fail_job(self, job_id: str, message: str) -> None:
        now = utc_now()
        with connection(self._database_path) as conn, conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'failed', finished_at = ?, summary_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, message, now, job_id),
            )
            conn.execute(
                """
                UPDATE job_items
                SET status = CASE WHEN status = 'completed' THEN status ELSE 'failed' END,
                    message = CASE WHEN status = 'completed' THEN message ELSE ? END,
                    finished_at = CASE WHEN status = 'completed' THEN finished_at ELSE ? END,
                    started_at = COALESCE(started_at, ?)
                WHERE job_id = ? AND status IN ('queued', 'running', 'failed')
                """,
                (message, now, now, job_id),
            )
            self._insert_event(conn, job_id=job_id, level="error", event_type="job.failed", message=message)

    def _cancel_running_job(self, job_id: str, message: str) -> None:
        now = utc_now()
        with connection(self._database_path) as conn, conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'cancelled', finished_at = ?, summary_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (now, message, now, job_id),
            )
            conn.execute(
                """
                UPDATE job_items
                SET status = CASE WHEN status = 'completed' THEN status ELSE 'cancelled' END,
                    message = CASE WHEN status = 'completed' THEN message ELSE ? END,
                    finished_at = CASE WHEN status = 'completed' THEN finished_at ELSE ? END,
                    started_at = COALESCE(started_at, ?)
                WHERE job_id = ? AND status IN ('queued', 'running', 'cancelled')
                """,
                (message, now, now, job_id),
            )
            self._insert_event(conn, job_id=job_id, level="warning", event_type="job.cancelled", message=message)

    def _set_job_item_status(self, item_id: str, status: str, message: str, *, output_ref: str | None = None) -> None:
        now = utc_now()
        with connection(self._database_path) as conn, conn:
            conn.execute(
                """
                UPDATE job_items
                SET status = ?, message = ?, started_at = COALESCE(started_at, ?),
                    finished_at = CASE WHEN ? IN ('completed', 'failed', 'cancelled', 'skipped') THEN ? ELSE NULL END,
                    output_ref = COALESCE(?, output_ref)
                WHERE id = ?
                """,
                (status, message, now, status, now, output_ref, item_id),
            )

    def _job_cancel_requested(self, job_id: str) -> bool:
        with connection(self._database_path) as conn:
            row = conn.execute(
                "SELECT cancel_requested_at, status FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
        if row is None:
            return True
        return row["cancel_requested_at"] is not None or row["status"] == "cancelled"

    def _append_event(
        self,
        *,
        job_id: str | None,
        file_id: str | None = None,
        level: str,
        event_type: str,
        message: str,
        payload: dict | None = None,
    ) -> None:
        with connection(self._database_path) as conn, conn:
            self._insert_event(conn, job_id=job_id, file_id=file_id, level=level, event_type=event_type, message=message, payload=payload)

    def _insert_event(
        self,
        conn,
        *,
        job_id: str | None,
        level: str,
        event_type: str,
        message: str,
        file_id: str | None = None,
        payload: dict | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT INTO app_events (id, job_id, file_id, level, event_type, message, payload, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                job_id,
                file_id,
                level,
                event_type,
                message,
                None if payload is None else json.dumps(payload),
                utc_now(),
            ),
        )
        self._wake_event.set()

    def _build_directory_item_specs(self, relative_path: str) -> list[dict]:
        files = self._list_supported_files_in_scope(relative_path)
        if files:
            return [self._file_item_spec(row) for row in files]
        placeholder = relative_path or "active source"
        return [{"item_key": placeholder, "message": f"No eligible files found under {placeholder}."}]

    def _list_supported_files_in_scope(self, relative_path: str) -> list:
        source = self._require_active_source()
        with connection(self._database_path) as conn:
            if relative_path:
                rows = conn.execute(
                    """
                    SELECT id, relative_path, file_name
                    FROM files
                    WHERE source_id = ?
                      AND is_video_supported = 1
                      AND (relative_path = ? OR relative_path LIKE ?)
                    ORDER BY relative_path ASC
                    """,
                    (source["id"], relative_path, f"{relative_path}/%"),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, relative_path, file_name
                    FROM files
                    WHERE source_id = ? AND is_video_supported = 1
                    ORDER BY relative_path ASC
                    """,
                    (source["id"],),
                ).fetchall()
        return list(rows)

    def _require_file(self, file_id: str):
        with connection(self._database_path) as conn:
            row = conn.execute(
                """
                SELECT id, relative_path, file_name, is_video_supported
                FROM files
                WHERE id = ?
                """,
                (file_id,),
            ).fetchone()
        if row is None:
            raise ApiError("file_not_found", "Requested file does not exist.", status=404)
        if not row["is_video_supported"]:
            raise ApiError("unsupported_file", "Selected file is not eligible for video workflows.", status=400)
        return row

    def _get_file_for_conversion(self, file_id: str):
        with connection(self._database_path) as conn:
            row = conn.execute(
                """
                SELECT id, directory_id, relative_path, path, file_name, extension, is_video_supported
                FROM files
                WHERE id = ?
                """,
                (file_id,),
            ).fetchone()
        if row is None:
            raise ApiError("file_not_found", "Requested file does not exist.", status=404)
        if not row["is_video_supported"]:
            raise ApiError("unsupported_file", "Selected file is not eligible for video workflows.", status=400)
        return row

    def _set_file_conversion_state(
        self,
        *,
        file_id: str,
        state: str,
        profile_id: str,
        error_code: str | None,
        error_message: str | None,
    ) -> None:
        now = utc_now()
        with connection(self._database_path) as conn, conn:
            conn.execute(
                """
                UPDATE files
                SET conversion_state = ?, last_conversion_profile_id = ?, last_error_code = ?,
                    last_error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (state, profile_id, error_code, error_message, now, file_id),
            )

    def _record_successful_conversion(self, *, file_id: str, result: dict, profile_id: str) -> None:
        now = utc_now()
        with connection(self._database_path) as conn, conn:
            conn.execute(
                """
                UPDATE files
                SET relative_path = ?, path = ?, file_name = ?, extension = ?, size_bytes = ?,
                    modified_at = ?, conversion_state = 'done', last_conversion_profile_id = ?,
                    last_converted_at = ?, last_error_code = NULL, last_error_message = NULL,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    result["relative_path"],
                    result["path"],
                    result["file_name"],
                    result["extension"],
                    result["size_bytes"],
                    result["modified_at"],
                    profile_id,
                    now,
                    now,
                    file_id,
                ),
            )

    def _require_active_source(self) -> dict:
        source = self._source_service.get_active_source()
        if source is None:
            raise ApiError("source_not_configured", "Configure an active source before creating jobs.", status=400)
        return source

    def _repair_interrupted_jobs(self) -> None:
        now = utc_now()
        with connection(self._database_path) as conn, conn:
            running_jobs = conn.execute(
                "SELECT id FROM jobs WHERE status = 'running'"
            ).fetchall()
            for row in running_jobs:
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'failed', finished_at = ?, summary_message = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, "Job was interrupted by backend restart.", now, row["id"]),
                )
                conn.execute(
                    """
                    UPDATE job_items
                    SET status = CASE WHEN status = 'completed' THEN status ELSE 'failed' END,
                        message = CASE WHEN status = 'completed' THEN message ELSE ? END,
                        finished_at = CASE WHEN status = 'completed' THEN finished_at ELSE ? END,
                        started_at = COALESCE(started_at, ?)
                    WHERE job_id = ? AND status IN ('queued', 'running')
                    """,
                    ("Job was interrupted by backend restart.", now, now, row["id"]),
                )
                self._insert_event(
                    conn,
                    job_id=row["id"],
                    level="error",
                    event_type="job.interrupted",
                    message="Job was interrupted by backend restart.",
                )

    def _serialize_job_row(self, row) -> dict:
        return {
            "id": row["id"],
            "job_type": row["job_type"],
            "scope_type": row["scope_type"],
            "scope_ref": row["scope_ref"],
            "status": row["status"],
            "requested_by": row["requested_by"],
            "parameters": json.loads(row["parameters"]),
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "summary_message": row["summary_message"],
            "cancel_requested_at": row["cancel_requested_at"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "item_counts": {
                "queued": row["queued_items"],
                "running": row["running_items"],
                "completed": row["completed_items"],
                "failed": row["failed_items"],
                "cancelled": row["cancelled_items"],
                "skipped": row["skipped_items"],
                "total": row["total_items"],
            },
        }

    def _serialize_job_item_row(self, row) -> dict:
        return {
            "id": row["id"],
            "job_id": row["job_id"],
            "file_id": row["file_id"],
            "item_key": row["item_key"],
            "status": row["status"],
            "step_name": row["step_name"],
            "message": row["message"],
            "started_at": row["started_at"],
            "finished_at": row["finished_at"],
            "output_ref": row["output_ref"],
            "file_name": row["file_name"],
            "relative_path": row["relative_path"],
        }

    def _serialize_event_row(self, row) -> dict:
        return {
            "stream_id": row["stream_id"],
            "id": row["id"],
            "job_id": row["job_id"],
            "file_id": row["file_id"],
            "level": row["level"],
            "event_type": row["event_type"],
            "message": row["message"],
            "payload": None if row["payload"] is None else json.loads(row["payload"]),
            "created_at": row["created_at"],
        }

    def _file_item_spec(self, file_row) -> dict:
        return {
            "file_id": file_row["id"],
            "item_key": file_row["relative_path"],
            "message": f"Queued for {file_row['relative_path']}.",
        }
