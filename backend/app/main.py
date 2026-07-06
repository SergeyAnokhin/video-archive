from __future__ import annotations

import json
import mimetypes
import sys
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .app_state import AppState
from .config import load_config
from .conversion_profile_service import ConversionProfileService
from .conversion_service import ConversionService
from .db import initialize_database
from .errors import ApiError
from .job_service import JobService
from .library_service import LibraryService, normalize_relative_path
from .playback_settings_service import PlaybackSettingsService
from .preview_service import PreviewService
from .provider_settings_service import ProviderSettingsService
from .secrets import SecretStore
from .source_service import SourceService, parse_source_payload
from .tagging_service import TaggingService


APP_STATE: AppState | None = None


class VideoArchiveHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        try:
            parsed = urlparse(self.path)
            path = parsed.path
            query = parse_qs(parsed.query)
            if path == "/api/health":
                self._write_json(HTTPStatus.OK, {"status": "ok"})
                return

            if path == "/api/app/info":
                self._write_json(HTTPStatus.OK, _require_app_state().app_info())
                return

            if path == "/api/source":
                self._write_json(HTTPStatus.OK, {"source": _require_app_state().source_service.get_active_source()})
                return

            if path == "/api/local-directories":
                self._write_json(
                    HTTPStatus.OK,
                    _require_app_state().source_service.list_local_directories(_first_query_value(query, "path")),
                )
                return

            if path == "/api/tree":
                self._write_json(HTTPStatus.OK, {"tree": _require_app_state().library_service.get_tree()})
                return

            if path == "/api/files":
                directory = _first_query_value(query, "directory") or ""
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "directory": normalize_relative_path(directory),
                        "files": _require_app_state().library_service.list_files(directory=directory),
                    },
                )
                return

            if path == "/api/conversion-profiles":
                self._write_json(
                    HTTPStatus.OK,
                    {"profiles": _require_app_state().conversion_profile_service.list_profiles()},
                )
                return

            if path == "/api/settings":
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "settings": {
                            "preview": _require_app_state().preview_service.get_settings(),
                            "playback": _require_app_state().playback_settings_service.get_settings(),
                            "tagging": _require_app_state().tagging_service.get_settings(),
                        }
                    },
                )
                return

            if path == "/api/settings/providers":
                self._write_json(HTTPStatus.OK, {"providers": _require_app_state().provider_settings_service.get_settings()})
                return

            if path == "/api/preview-layouts":
                self._write_json(HTTPStatus.OK, {"presets": _require_app_state().preview_service.list_layout_presets()})
                return

            if path.startswith("/api/files/") and path.endswith("/preview"):
                file_id = path.removeprefix("/api/files/").removesuffix("/preview")
                preview = _require_app_state().preview_service.get_file_preview(file_id)
                self._write_json(HTTPStatus.OK, {"preview": preview})
                return

            if path.startswith("/api/files/") and path.endswith("/preview-image"):
                file_id = path.removeprefix("/api/files/").removesuffix("/preview-image")
                preview = _require_app_state().preview_service.get_file_preview(file_id, include_image_data=False)
                if preview is None:
                    raise ApiError("preview_not_found", "Requested preview asset does not exist.", status=404)
                self._serve_file_content(Path(preview["image_path"]))
                return

            if path.startswith("/api/files/") and path.endswith("/playback"):
                file_id = path.removeprefix("/api/files/").removesuffix("/playback")
                file_row = _require_app_state().library_service.get_file(file_id)
                settings = _require_app_state().playback_settings_service.get_settings()
                self._write_json(HTTPStatus.OK, {"playback": _build_playback_payload(file_row, settings)})
                return

            if path.startswith("/api/files/") and path.endswith("/content"):
                file_id = path.removeprefix("/api/files/").removesuffix("/content")
                file_row = _require_app_state().library_service.get_file(file_id)
                self._serve_file_content(Path(file_row["path"]))
                return

            if path.startswith("/api/files/") and path.endswith("/tags"):
                file_id = path.removeprefix("/api/files/").removesuffix("/tags")
                tags = _require_app_state().tagging_service.get_file_tags(file_id)
                self._write_json(HTTPStatus.OK, {"tags": tags})
                return

            if path.startswith("/api/files/"):
                file_id = path.removeprefix("/api/files/")
                self._write_json(HTTPStatus.OK, {"file": _require_app_state().library_service.get_file(file_id)})
                return

            if path == "/api/directories/preview":
                relative_path = normalize_relative_path(_first_query_value(query, "relative_path"))
                source = _require_app_state().source_service.get_active_source()
                if source is None:
                    raise ApiError("source_not_configured", "Configure an active source before loading directory previews.", status=400)
                preview = _require_app_state().preview_service.get_directory_preview(source["id"], relative_path)
                self._write_json(HTTPStatus.OK, {"preview": preview})
                return

            if path == "/api/jobs":
                limit = _parse_limit(_first_query_value(query, "limit"))
                offset = _parse_offset(_first_query_value(query, "offset"))
                status = _first_query_value(query, "status")
                job_type = _first_query_value(query, "job_type")
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "jobs": _require_app_state().job_service.list_jobs(
                            status=status,
                            job_type=job_type,
                            limit=limit,
                            offset=offset,
                        )
                    },
                )
                return

            if path.startswith("/api/jobs/"):
                job_tail = path.removeprefix("/api/jobs/")
                if job_tail.endswith("/items"):
                    job_id = job_tail.removesuffix("/items")
                    self._write_json(HTTPStatus.OK, {"items": _require_app_state().job_service.list_job_items(job_id)})
                    return
                self._write_json(HTTPStatus.OK, {"job": _require_app_state().job_service.get_job(job_tail)})
                return

            if path == "/api/logs":
                limit = _parse_log_limit(_first_query_value(query, "limit"))
                self._write_json(
                    HTTPStatus.OK,
                    {
                        "events": _require_app_state().job_service.list_events(
                            job_id=_first_query_value(query, "job_id"),
                            file_id=_first_query_value(query, "file_id"),
                            level=_first_query_value(query, "level"),
                            limit=limit,
                        )
                    },
                )
                return

            if path == "/api/logs/stream":
                self._stream_events(
                    job_id=_first_query_value(query, "job_id"),
                    file_id=_first_query_value(query, "file_id"),
                    level=_first_query_value(query, "level"),
                )
                return

            self._not_found()
        except ApiError as exc:
            self._write_error(exc)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:  # pragma: no cover - defensive server logging
            self._handle_unexpected_exception("GET", self.path, exc)

    def do_PUT(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        try:
            path = urlparse(self.path).path
            if path == "/api/source":
                payload = parse_source_payload(self._read_json_body())
                source = _require_app_state().source_service.replace_active_source(payload)
                self._write_json(HTTPStatus.OK, {"source": source})
                return

            if path == "/api/settings":
                payload = self._read_json_body()
                response_settings: dict[str, dict] = {}
                if "preview" in payload:
                    preview_payload = payload.get("preview")
                    if not isinstance(preview_payload, dict):
                        raise ApiError("invalid_request", "Field 'preview' must be a JSON object.", status=400)
                    response_settings["preview"] = _require_app_state().preview_service.update_settings(preview_payload)
                if "playback" in payload:
                    playback_payload = payload.get("playback")
                    if not isinstance(playback_payload, dict):
                        raise ApiError("invalid_request", "Field 'playback' must be a JSON object.", status=400)
                    response_settings["playback"] = _require_app_state().playback_settings_service.update_settings(playback_payload)
                if "tagging" in payload:
                    tagging_payload = payload.get("tagging")
                    if not isinstance(tagging_payload, dict):
                        raise ApiError("invalid_request", "Field 'tagging' must be a JSON object.", status=400)
                    response_settings["tagging"] = _require_app_state().tagging_service.update_settings(tagging_payload)
                if not response_settings:
                    raise ApiError("invalid_request", "Request must include 'preview', 'playback', or 'tagging' settings.", status=400)
                self._write_json(HTTPStatus.OK, {"settings": response_settings})
                return

            if path == "/api/settings/providers":
                payload = self._read_json_body()
                providers_payload = payload.get("providers")
                if not isinstance(providers_payload, list):
                    raise ApiError("invalid_request", "Field 'providers' must be an array.", status=400)
                providers = _require_app_state().provider_settings_service.update_settings(providers_payload)
                self._write_json(HTTPStatus.OK, {"providers": providers})
                return

            if path.startswith("/api/preview-layouts/"):
                preset_id = path.removeprefix("/api/preview-layouts/")
                preset = _require_app_state().preview_service.update_layout_preset(preset_id, self._read_json_body())
                self._write_json(HTTPStatus.OK, {"preset": preset})
                return

            self._not_found()
        except ApiError as exc:
            self._write_error(exc)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:  # pragma: no cover - defensive server logging
            self._handle_unexpected_exception("PUT", self.path, exc)

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        try:
            path = urlparse(self.path).path
            if path == "/api/source/test-connection":
                payload = parse_source_payload(self._read_json_body())
                result = _require_app_state().source_service.test_connection(payload)
                self._write_json(HTTPStatus.OK, result)
                return

            if path == "/api/source/reconnect":
                result = _require_app_state().source_service.reconnect_active_source()
                self._write_json(HTTPStatus.OK, result)
                return

            if path == "/api/jobs/scan-source":
                job = _require_app_state().job_service.create_scan_job()
                self._write_json(HTTPStatus.OK, {"job": job})
                return

            if path == "/api/jobs/rescan-directory":
                relative_path = normalize_relative_path(self._read_json_body().get("relative_path"))
                job = _require_app_state().job_service.create_rescan_job(relative_path)
                self._write_json(HTTPStatus.OK, {"job": job})
                return

            if path == "/api/jobs/convert-directory":
                payload = self._read_json_body()
                relative_path = normalize_relative_path(payload.get("relative_path"))
                job = _require_app_state().job_service.create_convert_directory_job(
                    relative_path,
                    profile_id=_read_optional_string(payload, "profile_id"),
                    mode=_read_conversion_mode(payload.get("mode")),
                )
                self._write_json(HTTPStatus.OK, {"job": job})
                return

            if path == "/api/jobs/preview-directory":
                relative_path = normalize_relative_path(self._read_json_body().get("relative_path"))
                job = _require_app_state().job_service.create_preview_directory_job(relative_path)
                self._write_json(HTTPStatus.OK, {"job": job})
                return

            if path == "/api/jobs/tag-directory":
                relative_path = normalize_relative_path(self._read_json_body().get("relative_path"))
                job = _require_app_state().job_service.create_tag_directory_job(relative_path)
                self._write_json(HTTPStatus.OK, {"job": job})
                return

            if path == "/api/jobs/convert-file":
                payload = self._read_json_body()
                job = _require_app_state().job_service.create_convert_file_job(
                    _read_required_string(payload, "file_id"),
                    profile_id=_read_optional_string(payload, "profile_id"),
                    mode=_read_conversion_mode(payload.get("mode")),
                )
                self._write_json(HTTPStatus.OK, {"job": job})
                return

            if path == "/api/jobs/preview-file":
                job = _require_app_state().job_service.create_preview_file_job(_read_required_string(self._read_json_body(), "file_id"))
                self._write_json(HTTPStatus.OK, {"job": job})
                return

            if path == "/api/preview-layouts":
                preset = _require_app_state().preview_service.create_layout_preset(self._read_json_body())
                self._write_json(HTTPStatus.OK, {"preset": preset})
                return

            if path == "/api/preview-layouts/preview":
                preview = _require_app_state().preview_service.build_live_preview(self._read_json_body())
                self._write_json(HTTPStatus.OK, {"preview": preview})
                return

            if path == "/api/conversion-profiles":
                profile = _require_app_state().conversion_profile_service.create_profile(self._read_json_body())
                self._write_json(HTTPStatus.OK, {"profile": profile})
                return

            if path == "/api/jobs/tag-file":
                job = _require_app_state().job_service.create_tag_file_job(_read_required_string(self._read_json_body(), "file_id"))
                self._write_json(HTTPStatus.OK, {"job": job})
                return

            if path == "/api/jobs/tune-file":
                payload = self._read_json_body()
                job = _require_app_state().job_service.create_tune_file_job(_read_required_string(payload, "file_id"), payload.get("sweep"))
                self._write_json(HTTPStatus.OK, {"job": job})
                return

            if path.startswith("/api/jobs/"):
                job_tail = path.removeprefix("/api/jobs/")
                if job_tail.endswith("/cancel"):
                    job_id = job_tail.removesuffix("/cancel")
                    job = _require_app_state().job_service.cancel_job(job_id)
                    self._write_json(HTTPStatus.OK, {"job": job})
                    return
                if job_tail.endswith("/restart"):
                    job_id = job_tail.removesuffix("/restart")
                    job = _require_app_state().job_service.restart_job(job_id)
                    self._write_json(HTTPStatus.OK, {"job": job})
                    return

                self._not_found()

            if path.startswith("/api/preview-layouts/"):
                preset_id = path.removeprefix("/api/preview-layouts/")
                preset = _require_app_state().preview_service.update_layout_preset(preset_id, self._read_json_body())
                self._write_json(HTTPStatus.OK, {"preset": preset})
                return

            self._not_found()
        except ApiError as exc:
            self._write_error(exc)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:  # pragma: no cover - defensive server logging
            self._handle_unexpected_exception("POST", self.path, exc)

    def do_DELETE(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        try:
            path = urlparse(self.path).path
            if path.startswith("/api/preview-layouts/"):
                preset_id = path.removeprefix("/api/preview-layouts/")
                _require_app_state().preview_service.delete_layout_preset(preset_id)
                self._write_json(HTTPStatus.OK, {"ok": True})
                return
            self._not_found()
        except ApiError as exc:
            self._write_error(exc)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as exc:  # pragma: no cover - defensive server logging
            self._handle_unexpected_exception("DELETE", self.path, exc)

    def _serve_file_content(self, file_path: Path) -> None:
        if not file_path.exists() or not file_path.is_file():
            raise ApiError("file_not_found", "Playback file is not available.", status=404)

        file_size = file_path.stat().st_size
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        range_header = self.headers.get("Range")
        start = 0
        end = file_size - 1
        status = HTTPStatus.OK

        if range_header and range_header.startswith("bytes="):
            range_value = range_header.removeprefix("bytes=").strip()
            start_text, _, end_text = range_value.partition("-")
            if start_text:
                start = max(0, int(start_text))
            if end_text:
                end = min(file_size - 1, int(end_text))
            if start > end or start >= file_size:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.end_headers()
                return
            status = HTTPStatus.PARTIAL_CONTENT

        content_length = (end - start) + 1
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(content_length))
        self.send_header("Cache-Control", "no-store")
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.end_headers()

        with file_path.open("rb") as handle:
            handle.seek(start)
            remaining = content_length
            while remaining > 0:
                data = handle.read(min(64 * 1024, remaining))
                if not data:
                    break
                self.wfile.write(data)
                remaining -= len(data)

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _handle_unexpected_exception(self, method: str, path: str, error: Exception) -> None:
        self._log_exception(method, path, error)
        self._write_json(
            HTTPStatus.INTERNAL_SERVER_ERROR,
            {"error": {"code": "internal_server_error", "message": f"{type(error).__name__}: {error}"}},
        )

    def _log_exception(self, method: str, path: str, error: Exception) -> None:
        print(f"[backend-error] {method} {path}", file=sys.stderr, flush=True)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
        print("", file=sys.stderr, flush=True)

    def _read_json_body(self) -> dict:
        content_length = self.headers.get("Content-Length")
        if content_length is None:
            raise ApiError("invalid_request", "Missing Content-Length header.", status=400)

        try:
            size = int(content_length)
        except ValueError as exc:
            raise ApiError("invalid_request", "Invalid Content-Length header.", status=400) from exc

        body = self.rfile.read(size)
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ApiError("invalid_json", "Request body must be valid JSON.", status=400) from exc

        if not isinstance(payload, dict):
            raise ApiError("invalid_request", "Request body must be a JSON object.", status=400)
        return payload

    def _not_found(self) -> None:
        raise ApiError(
            "not_found",
            "Endpoint not implemented in the current backend foundation.",
            status=HTTPStatus.NOT_FOUND,
        )

    def _write_error(self, error: ApiError) -> None:
        self._write_json(
            HTTPStatus(error.status),
            {"error": {"code": error.code, "message": error.message}},
        )

    def _write_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _stream_events(self, *, job_id: str | None, file_id: str | None, level: str | None) -> None:
        last_event_id_header = self.headers.get("Last-Event-ID")
        after_stream_id = None if not last_event_id_header else int(last_event_id_header)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        self.wfile.write(b": connected\n\n")
        self.wfile.flush()

        job_service = _require_app_state().job_service
        while True:
            events = job_service.list_events(
                job_id=job_id,
                file_id=file_id,
                level=level,
                limit=200,
                after_stream_id=after_stream_id,
            )
            if events:
                for event in events:
                    after_stream_id = event["stream_id"]
                    body = f"id: {event['stream_id']}\ndata: {json.dumps(event)}\n\n".encode("utf-8")
                    self.wfile.write(body)
                    self.wfile.flush()
            else:
                self.wfile.write(b": heartbeat\n\n")
                self.wfile.flush()

            if APP_STATE is None or APP_STATE.job_service.wait_for_shutdown(timeout=1):
                return


def create_app_state() -> AppState:
    config = load_config()
    initialize_database(config.database_path)
    secret_store = SecretStore(config.secrets_path)
    source_service = SourceService(config.database_path, secret_store)
    library_service = LibraryService(config.database_path, source_service)
    conversion_profile_service = ConversionProfileService(config.database_path)
    playback_settings_service = PlaybackSettingsService(config.database_path)
    preview_service = PreviewService(config.database_path, config.data_dir)
    provider_settings_service = ProviderSettingsService(config.database_path, secret_store)
    tagging_service = TaggingService(config.database_path, provider_settings_service)
    job_service = JobService(
        config.database_path,
        source_service,
        library_service,
        conversion_profile_service,
        ConversionService(),
        preview_service,
        tagging_service,
    )
    job_service.start()
    return AppState(
        config=config,
        source_service=source_service,
        library_service=library_service,
        conversion_profile_service=conversion_profile_service,
        playback_settings_service=playback_settings_service,
        preview_service=preview_service,
        provider_settings_service=provider_settings_service,
        tagging_service=tagging_service,
        job_service=job_service,
    )


def main() -> None:
    global APP_STATE
    APP_STATE = create_app_state()

    server = ThreadingHTTPServer((APP_STATE.config.host, APP_STATE.config.port), VideoArchiveHandler)
    print(f"Video Archive backend listening on http://{APP_STATE.config.host}:{APP_STATE.config.port}")
    print(f"Video Archive database: {APP_STATE.config.database_path}")
    print(f"Video Archive secrets: {APP_STATE.config.secrets_path}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        APP_STATE.job_service.shutdown()
        server.server_close()


def _require_app_state() -> AppState:
    if APP_STATE is None:
        raise RuntimeError("App state is not initialized.")
    return APP_STATE


def _first_query_value(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    if not values:
        return None
    return values[0]


def _parse_limit(value: str | None) -> int:
    if value is None:
        return 20
    try:
        limit = int(value)
    except ValueError as exc:
        raise ApiError("invalid_request", "Query parameter 'limit' must be an integer.", status=400) from exc
    if limit < 1 or limit > 100:
        raise ApiError("invalid_request", "Query parameter 'limit' must be between 1 and 100.", status=400)
    return limit


def _parse_offset(value: str | None) -> int:
    if value is None:
        return 0
    try:
        offset = int(value)
    except ValueError as exc:
        raise ApiError("invalid_request", "Query parameter 'offset' must be an integer.", status=400) from exc
    if offset < 0:
        raise ApiError("invalid_request", "Query parameter 'offset' must be zero or positive.", status=400)
    return offset


def _parse_log_limit(value: str | None) -> int:
    if value is None:
        return 100
    try:
        limit = int(value)
    except ValueError as exc:
        raise ApiError("invalid_request", "Query parameter 'limit' must be an integer.", status=400) from exc
    if limit < 1 or limit > 500:
        raise ApiError("invalid_request", "Query parameter 'limit' must be between 1 and 500.", status=400)
    return limit


def _read_required_string(payload: dict, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ApiError("invalid_request", f"Field '{key}' must be a non-empty string.", status=400)
    return value.strip()


def _read_optional_string(payload: dict, key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ApiError("invalid_request", f"Field '{key}' must be a string when provided.", status=400)
    normalized = value.strip()
    return normalized or None


def _read_conversion_mode(value: object) -> str:
    if value is None:
        return "production"
    if not isinstance(value, str):
        raise ApiError("invalid_request", "Field 'mode' must be a string when provided.", status=400)
    normalized = value.strip().lower()
    if normalized not in {"production", "test"}:
        raise ApiError("invalid_request", "Field 'mode' must be 'production' or 'test'.", status=400)
    return normalized


def _build_playback_payload(file_row: dict, settings: dict) -> dict:
    path = Path(file_row["path"])
    file_uri = _to_file_uri(path)
    return {
        "file_id": file_row["id"],
        "file_name": file_row["file_name"],
        "path": str(path),
        "mode": settings["mode"],
        "external_strategy": settings["external_strategy"],
        "embedded_url": f"/api/files/{file_row['id']}/content",
        "external_url": file_uri,
        "external_supported": file_uri is not None,
    }


def _to_file_uri(path: Path) -> str | None:
    try:
        return path.resolve().as_uri()
    except ValueError:
        raw = str(path).replace("\\", "/")
        if raw.startswith("//"):
            return f"file:{raw}"
        if len(raw) >= 2 and raw[1] == ":":
            return f"file:///{raw[0]}:{raw[2:]}"
        return None


if __name__ == "__main__":
    main()
