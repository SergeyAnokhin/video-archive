from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.db import initialize_database
from app.playback_settings_service import PlaybackSettingsService


class PlaybackSettingsServiceTests(unittest.TestCase):
    def test_default_settings_and_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "video_archive.db"
            initialize_database(db_path)

            service = PlaybackSettingsService(db_path)
            defaults = service.get_settings()
            updated = service.update_settings({"mode": "external", "external_strategy": "path"})

            self.assertEqual(defaults["mode"], "embedded")
            self.assertEqual(defaults["external_strategy"], "file_uri")
            self.assertEqual(updated["mode"], "external")
            self.assertEqual(updated["external_strategy"], "path")


if __name__ == "__main__":
    unittest.main()
