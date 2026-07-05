from __future__ import annotations

from dataclasses import dataclass

from .config import AppConfig
from .db import get_schema_version
from .source_service import SourceService


@dataclass
class AppState:
    config: AppConfig
    source_service: SourceService

    def app_info(self) -> dict:
        active_source = self.source_service.get_active_source()
        return {
            "version": self.config.app_version,
            "active_source": (
                None
                if active_source is None
                else {
                    "id": active_source["id"],
                    "name": active_source["name"],
                    "protocol": active_source["protocol"],
                    "host": active_source["host"],
                    "root_path": active_source["root_path"],
                }
            ),
            "database": {
                "status": "ok",
                "path": str(self.config.database_path),
                "schema_version": get_schema_version(self.config.database_path),
            },
            "queue": {
                "status": "idle",
                "queued_jobs": 0,
                "running_jobs": 0,
            },
        }
