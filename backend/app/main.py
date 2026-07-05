from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .app_state import AppState
from .config import load_config
from .db import initialize_database
from .errors import ApiError
from .secrets import SecretStore
from .source_service import SourceService, parse_source_payload


APP_STATE: AppState | None = None


class VideoArchiveHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        try:
            path = urlparse(self.path).path
            if path == "/api/health":
                self._write_json(HTTPStatus.OK, {"status": "ok"})
                return

            if path == "/api/app/info":
                self._write_json(HTTPStatus.OK, _require_app_state().app_info())
                return

            if path == "/api/source":
                self._write_json(HTTPStatus.OK, {"source": _require_app_state().source_service.get_active_source()})
                return

            self._not_found()
        except ApiError as exc:
            self._write_error(exc)

    def do_PUT(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        try:
            path = urlparse(self.path).path
            if path == "/api/source":
                payload = parse_source_payload(self._read_json_body())
                source = _require_app_state().source_service.replace_active_source(payload)
                self._write_json(HTTPStatus.OK, {"source": source})
                return

            self._not_found()
        except ApiError as exc:
            self._write_error(exc)

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        try:
            path = urlparse(self.path).path
            if path == "/api/source/test-connection":
                payload = parse_source_payload(self._read_json_body())
                result = _require_app_state().source_service.test_connection(payload)
                self._write_json(HTTPStatus.OK, result)
                return

            self._not_found()
        except ApiError as exc:
            self._write_error(exc)

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} - {format % args}")

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


def create_app_state() -> AppState:
    config = load_config()
    initialize_database(config.database_path)
    source_service = SourceService(config.database_path, SecretStore(config.secrets_path))
    return AppState(config=config, source_service=source_service)


def main() -> None:
    global APP_STATE
    APP_STATE = create_app_state()

    server = ThreadingHTTPServer((APP_STATE.config.host, APP_STATE.config.port), VideoArchiveHandler)
    print(f"Video Archive backend listening on http://{APP_STATE.config.host}:{APP_STATE.config.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def _require_app_state() -> AppState:
    if APP_STATE is None:
        raise RuntimeError("App state is not initialized.")
    return APP_STATE


if __name__ == "__main__":
    main()
