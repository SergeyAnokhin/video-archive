from __future__ import annotations

from dataclasses import dataclass

from .config import AppConfig
from .conversion_profile_service import ConversionProfileService
from .db import get_schema_version
from .job_service import JobService
from .library_service import LibraryService
from .preview_service import PreviewService
from .provider_settings_service import ProviderSettingsService
from .source_service import SourceService
from .tagging_service import TaggingService


@dataclass
class AppState:
    config: AppConfig
    source_service: SourceService
    library_service: LibraryService
    conversion_profile_service: ConversionProfileService
    preview_service: PreviewService
    provider_settings_service: ProviderSettingsService
    tagging_service: TaggingService
    job_service: JobService

    def app_info(self) -> dict:
        active_source = self.source_service.get_active_source()
        queue = self.job_service.get_queue_summary()
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
            "queue": queue,
        }
