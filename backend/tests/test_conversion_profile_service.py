from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.conversion_profile_service import ConversionProfileService
from app.db import initialize_database


class ConversionProfileServiceTests(unittest.TestCase):
    def test_default_profile_is_seeded_and_listed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "video_archive.db"
            initialize_database(db_path)

            service = ConversionProfileService(db_path)
            profiles = service.list_profiles()

            self.assertEqual(len(profiles), 1)
            self.assertEqual(profiles[0]["video_codec"], "h265")
            self.assertEqual(profiles[0]["container"], "mp4")
            self.assertTrue(profiles[0]["drop_audio"])
            self.assertTrue(profiles[0]["is_default"])

    def test_create_profile_accepts_h264_and_marks_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "video_archive.db"
            initialize_database(db_path)

            service = ConversionProfileService(db_path)
            created = service.create_profile(
                {
                    "name": "Fast H.264",
                    "is_default": True,
                    "video_codec": "h264",
                    "container": "mp4",
                    "max_dimension": 1280,
                    "quality_mode": "crf",
                    "quality_value": "24",
                    "drop_audio": False,
                }
            )
            profiles = service.list_profiles()

            self.assertEqual(created["video_codec"], "h264")
            self.assertTrue(created["is_default"])
            self.assertEqual(profiles[0]["id"], created["id"])


if __name__ == "__main__":
    unittest.main()
