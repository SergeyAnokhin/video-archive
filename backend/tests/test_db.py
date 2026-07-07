from __future__ import annotations

import sqlite3
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

    def test_initialize_database_repairs_missing_generated_file_columns_when_version_is_already_7(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "video_archive.db"
            conn = sqlite3.connect(db_path)
            try:
                conn.execute(
                    """
                    CREATE TABLE schema_migrations (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO schema_migrations(version, applied_at)
                    VALUES (7, datetime('now'))
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE files (
                        id TEXT PRIMARY KEY,
                        source_id TEXT NOT NULL,
                        directory_id TEXT NOT NULL,
                        relative_path TEXT NOT NULL,
                        path TEXT NOT NULL,
                        file_name TEXT NOT NULL,
                        extension TEXT NOT NULL,
                        size_bytes INTEGER NOT NULL,
                        modified_at TEXT NULL,
                        discovered_at TEXT NOT NULL,
                        last_scanned_at TEXT NOT NULL,
                        is_video_supported INTEGER NOT NULL,
                        conversion_state TEXT NOT NULL,
                        preview_state TEXT NOT NULL,
                        last_conversion_profile_id TEXT NULL,
                        last_converted_at TEXT NULL,
                        preview_generated_at TEXT NULL,
                        has_preview_assets INTEGER NOT NULL,
                        last_error_code TEXT NULL,
                        last_error_message TEXT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        keyframe_timestamps TEXT NULL,
                        large_tile_timestamps TEXT NULL,
                        face_detection_summary TEXT NULL,
                        body_detection_summary TEXT NULL,
                        preview_layout_version INTEGER NOT NULL DEFAULT 1,
                        preview_asset_path TEXT NULL,
                        tagging_updated_at TEXT NULL,
                        tagging_model_info TEXT NULL
                    )
                    """
                )
                conn.commit()
            finally:
                conn.close()

            initialize_database(db_path)

            repaired = sqlite3.connect(db_path)
            try:
                columns = {row[1] for row in repaired.execute("PRAGMA table_info(files)").fetchall()}
                version = repaired.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
            finally:
                repaired.close()

        self.assertEqual(version, SCHEMA_VERSION)
        self.assertIn("generated_from_job_id", columns)
        self.assertIn("generated_from_file_id", columns)
        self.assertIn("generated_kind", columns)


if __name__ == "__main__":
    unittest.main()
