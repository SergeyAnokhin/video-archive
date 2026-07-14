"""Per-request console logging.

Chat request (2026-07-14): replace uvicorn's default access log (one
"GET /api/jobs?limit=200 200 OK" line per hit, indistinguishable between
endpoints) with something that (a) stays silent for the handful of
endpoints the frontend polls every 1-3s for live progress, so they don't
drown out everything else, and (b) is otherwise a single expressive line
per request -- emoji by method, the route's path template, path/query
params, status, and duration -- for every other endpoint, success or
failure. Request bodies are deliberately never logged: some settings
endpoints (e.g. provider entry import) carry API keys in the body.
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

logger = logging.getLogger("app.requests")

_METHOD_EMOJI = {
    "GET": "📥",
    "POST": "📮",
    "PUT": "✏️",
    "PATCH": "✏️",
    "DELETE": "🗑️",
}

# (method, route path template) pairs the frontend polls every 1-3s for live
# job/batch progress (`JobsContext.tsx`, `BatchSubmissionsModal.tsx`,
# `FileTuneModal.tsx`) -- logging every hit here is pure noise. Stays silent
# for these only while they succeed; a failure still logs, since that's
# exactly the kind of thing worth seeing.
_QUIET_ROUTES = {
    ("GET", "/api/jobs"),
    ("GET", "/api/jobs/{job_id}/items"),
    ("GET", "/api/jobs/batch-submissions"),
}


def _route_path(request: Request) -> str:
    # `scope["route"].path` is only the path *local to the innermost router*
    # (FastAPI mounts each `include_router(..., prefix="/api")` as its own
    # lazily-expanded sub-router), so it comes back as e.g. "/jobs/{job_id}"
    # instead of "/api/jobs/{job_id}". Rebuilding the template from the real
    # request path plus the resolved path params sidesteps that and always
    # yields the full, prefixed template.
    path = request.url.path
    for name, value in request.path_params.items():
        path = path.replace(f"/{value}", f"/{{{name}}}", 1)
    return path


def _format(request: Request, route_path: str, status_code: int, duration_ms: float) -> str:
    method_emoji = _METHOD_EMOJI.get(request.method, "🌐")
    status_emoji = "✅" if status_code < 400 else "❌"
    route = request.scope.get("route")
    purpose = (getattr(route, "name", "") or "").replace("_", " ") or "unmatched route"

    params = {**request.path_params, **dict(request.query_params)}
    params_part = f" params={params}" if params else ""

    return (
        f"{method_emoji} {request.method} {route_path}{params_part} "
        f"-> {status_emoji} {status_code} ({duration_ms:.0f}ms) — {purpose}"
    )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.monotonic() - start) * 1000
            logger.exception(
                "💥 %s %s %s failed after %.0fms", _METHOD_EMOJI.get(request.method, "🌐"),
                request.method, _route_path(request), duration_ms,
            )
            raise

        route_path = _route_path(request)
        if response.status_code < 400 and (request.method, route_path) in _QUIET_ROUTES:
            return response

        duration_ms = (time.monotonic() - start) * 1000
        logger.info(_format(request, route_path, response.status_code, duration_ms))
        return response
