import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


APP_INFO = {
    "version": "0.1.0",
    "active_source": None,
    "database": {
        "status": "not_configured",
    },
    "queue": {
        "status": "idle",
        "queued_jobs": 0,
        "running_jobs": 0,
    },
}


class VideoArchiveHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if self.path == "/api/health":
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return

        if self.path == "/api/app/info":
            self._write_json(HTTPStatus.OK, APP_INFO)
            return

        self._write_json(
            HTTPStatus.NOT_FOUND,
            {
                "error": {
                    "code": "not_found",
                    "message": "Endpoint not implemented in the initial skeleton.",
                }
            },
        )

    def log_message(self, format: str, *args) -> None:
        print(f"{self.address_string()} - {format % args}")

    def _write_json(self, status: HTTPStatus, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    host = os.environ.get("VIDEO_ARCHIVE_HOST", "127.0.0.1")
    port = int(os.environ.get("VIDEO_ARCHIVE_PORT", "8000"))
    server = ThreadingHTTPServer((host, port), VideoArchiveHandler)
    print(f"Video Archive backend listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
