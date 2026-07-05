from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.db import SCHEMA_VERSION, get_schema_version, initialize_database


class DatabaseTests(unittest.TestCase):
    def test_initialize_database_creates_expected_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "video_archive.db"
            initialize_database(db_path)

            version = get_schema_version(db_path)

        self.assertEqual(version, SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
