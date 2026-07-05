from __future__ import annotations

import json
from pathlib import Path

from .db import connection
from .errors import ApiError
from .time_utils import utc_now


PLAYBACK_SECTION = "playback"
PLAYBACK_MODES = {"embedded", "external"}
EXTERNAL_STRATEGIES = {"file_uri", "path"}
DEFAULT_PLAYBACK_SETTINGS = {
    "mode": "embedded",
    "external_strategy": "file_uri",
}


class PlaybackSettingsService:
    def __init__(self, database_path: Path) -> None:
        self._database_path = database_path

    def get_settings(self) -> dict:
        with connection(self._database_path) as conn:
            row = conn.execute("SELECT payload FROM app_settings WHERE section = ?", (PLAYBACK_SECTION,)).fetchone()
        payload = {} if row is None else json.loads(row["payload"])
        return self._merge_settings_payload(payload)

    def update_settings(self, payload: dict) -> dict:
        settings = self._merge_settings_payload(payload)
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

    def _merge_settings_payload(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ApiError("invalid_request", "Playback settings payload must be a JSON object.", status=400)

        mode = payload.get("mode", DEFAULT_PLAYBACK_SETTINGS["mode"])
        if not isinstance(mode, str) or mode not in PLAYBACK_MODES:
            raise ApiError("invalid_request", "Playback mode must be 'embedded' or 'external'.", status=400)

        external_strategy = payload.get("external_strategy", DEFAULT_PLAYBACK_SETTINGS["external_strategy"])
        if not isinstance(external_strategy, str) or external_strategy not in EXTERNAL_STRATEGIES:
            raise ApiError("invalid_request", "External playback strategy must be 'file_uri' or 'path'.", status=400)

        return {
            "mode": mode,
            "external_strategy": external_strategy,
        }
