from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.db import initialize_database
from app.provider_settings_service import ProviderSettingsService
from app.secrets import SecretStore
from app.tagging_service import TaggingService


class TaggingServiceTests(unittest.TestCase):
    def test_default_settings_and_vocab_update(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "video_archive.db"
            secrets_path = root / "secrets.json"
            initialize_database(db_path)
            provider_settings = ProviderSettingsService(db_path, SecretStore(secrets_path))
            tagging_service = TaggingService(db_path, provider_settings)

            settings = tagging_service.get_settings()
            self.assertEqual(settings["sample_count"], 9)
            self.assertEqual(settings["vocabulary"], [])

            updated = tagging_service.update_settings(
                {
                    "provider": "gemini",
                    "sample_count": 7,
                    "combine_frames": False,
                    "prefer_batch": True,
                    "vocabulary": ["Beach", "Family Time", "Pets"],
                }
            )

            self.assertEqual(updated["provider"], "gemini")
            self.assertEqual(updated["sample_count"], 7)
            self.assertFalse(updated["combine_frames"])
            self.assertEqual([entry["tag_key"] for entry in updated["vocabulary"]], ["beach", "family_time", "pets"])


if __name__ == "__main__":
    unittest.main()
