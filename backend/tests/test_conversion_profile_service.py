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


if __name__ == "__main__":
    unittest.main()
