from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.db import initialize_database
from app.preview_service import PreviewService


class PreviewServiceTests(unittest.TestCase):
    def test_default_settings_and_live_preview(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "video_archive.db"
            initialize_database(db_path)
            preview_service = PreviewService(db_path, root / ".local")

            settings = preview_service.get_settings()
            preview = preview_service.build_live_preview()

            self.assertEqual(settings["sample_count"], 9)
            self.assertTrue(settings["identity_diversity_enabled"])
            self.assertEqual(settings["aspect_ratio_preset"], "video")
            self.assertEqual(preview["layout"]["sample_count"], settings["sample_count"])
            self.assertEqual(preview["layout"]["aspect_ratio_preset"], "video")
            self.assertTrue(preview["image_data_url"].startswith("data:image/png;base64,"))

    def test_create_and_update_preview_preset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "video_archive.db"
            initialize_database(db_path)
            preview_service = PreviewService(db_path, root / ".local")

            created = preview_service.create_layout_preset(
                {
                    "name": "Dense collage",
                    "sample_count": 12,
                    "large_tile_count": 3,
                    "timeline_flow": "column",
                    "identity_diversity_enabled": False,
                    "aspect_ratio_preset": "s24",
                    "layout_definition": {"kind": "auto-grid", "version": 1},
                }
            )
            updated = preview_service.update_layout_preset(
                created["id"],
                {
                    "name": "Dense collage v2",
                    "sample_count": 10,
                    "large_tile_count": 2,
                    "timeline_flow": "shuffle",
                    "identity_diversity_enabled": True,
                    "aspect_ratio_preset": "ultrawide",
                    "layout_definition": {"kind": "auto-grid", "version": 1},
                },
            )

            self.assertEqual(created["timeline_flow"], "column")
            self.assertEqual(created["aspect_ratio_preset"], "s24")
            self.assertEqual(updated["name"], "Dense collage v2")
            self.assertEqual(updated["timeline_flow"], "shuffle")
            self.assertEqual(updated["aspect_ratio_preset"], "ultrawide")
            self.assertTrue(updated["identity_diversity_enabled"])


if __name__ == "__main__":
    unittest.main()
