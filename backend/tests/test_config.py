from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.config import load_config


class ConfigTests(unittest.TestCase):
    def test_load_config_uses_env_file_for_local_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            (base_dir / ".env.local").write_text(
                "\n".join(
                    [
                        "VIDEO_ARCHIVE_HOST=0.0.0.0",
                        "VIDEO_ARCHIVE_PORT=8123",
                        f"VIDEO_ARCHIVE_DATA_DIR={base_dir / 'data'}",
                    ]
                ),
                encoding="utf-8",
            )

            config = load_config(base_dir=base_dir, environ={})

        self.assertEqual(config.host, "0.0.0.0")
        self.assertEqual(config.port, 8123)
        self.assertEqual(config.data_dir, base_dir / "data")
        self.assertEqual(config.database_path, base_dir / "data" / "video_archive.db")


if __name__ == "__main__":
    unittest.main()
