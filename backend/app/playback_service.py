from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote

from .db import connection
from .errors import ApiError
from .time_utils import utc_now


PLAYBACK_SECTION = "playback"
PLAYBACK_MODES = {"embedded", "external"}
DEFAULT_PLAYBACK_SETTINGS = {"mode": "embedded"}


class PlaybackSettingsService:
    """Persists the configured video-opening strategy and resolves per-file playback targets."""

    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def get_settings(self) -> dict:
        with connection(self._database_path) as conn:
            row = conn.execute(
                "SELECT payload FROM app_settings WHERE section = ?",
                (PLAYBACK_SECTION,),
            ).fetchone()
        payload = {} if row is None else json.loads(row["payload"])
        return {**DEFAULT_PLAYBACK_SETTINGS, **payload}

    def update_settings(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ApiError("invalid_request", "Playback settings payload must be a JSON object.", status=400)

        mode = payload.get("mode", DEFAULT_PLAYBACK_SETTINGS["mode"])
        if mode not in PLAYBACK_MODES:
            raise ApiError("invalid_request", "Field 'mode' must be 'embedded' or 'external'.", status=400)

        settings = {"mode": mode}
        now = utc_now()
        with connection(self._database_path) as conn, conn:
            conn.execute(
                """
                INSERT INTO app_settings (section, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(section) DO UPDATE SET payload = excluded.payload, updated_at = excluded.updated_at
                """,
                (PLAYBACK_SECTION, json.dumps(settings), now, now),
            )
        return settings

    def resolve_playback(self, *, file_row: dict, source: dict) -> dict:
        settings = self.get_settings()
        return {
            "mode": settings["mode"],
            "embedded_stream_url": f"/api/files/{file_row['id']}/stream",
            "external_path": file_row["path"],
            "external_link": _build_external_link(source, file_row["relative_path"]),
        }


def _build_external_link(source: dict, relative_path: str) -> str:
    quoted_path = quote(relative_path)
    port_segment = f":{source['port']}" if source.get("port") else ""
    return f"{source['protocol']}://{source['host']}{port_segment}/{quoted_path}"
