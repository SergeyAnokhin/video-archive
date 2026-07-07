from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.db import connection, initialize_database
from app.library_service import LibraryService
from app.secrets import SecretStore
from app.source_service import SourceService, parse_source_payload


class LibraryServiceTests(unittest.TestCase):
    def test_scan_job_populates_tree_files_and_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "library"
            (source_root / "family" / "2024").mkdir(parents=True)
            (source_root / "family" / "2024" / "Beach Sunset.mp4").write_bytes(b"video-data")
            (source_root / "family" / "2024" / "notes.txt").write_text("note", encoding="utf-8")

            db_path = root / "video_archive.db"
            secrets_path = root / "secrets.json"
            initialize_database(db_path)
            source_service = SourceService(db_path, SecretStore(secrets_path))
            payload = parse_source_payload(
                {
                    "name": "Archive NAS",
                    "protocol": "smb",
                    "host": "nas.local",
                    "port": 445,
                    "root_path": str(source_root),
                }
            )
            source_service.replace_active_source(payload)
            library_service = LibraryService(db_path, source_service)

            job = library_service.create_scan_job()
            tree = library_service.get_tree()
            files = library_service.list_files("family/2024")
            jobs = library_service.list_jobs()

            self.assertEqual(job["status"], "completed")
            self.assertEqual(jobs[0]["job_type"], "scan")
            self.assertEqual(tree[0]["path"], "")
            family_node = tree[0]["children"][0]
            self.assertEqual(family_node["path"], "family")
            self.assertIsNotNone(family_node["indicators"]["conversion"])
            self.assertEqual(len(files), 2)
            self.assertEqual(files[0]["file_name"], "Beach Sunset.mp4")
            self.assertEqual(files[0]["conversion_state"], "not_started")
            self.assertFalse(family_node["has_preview_asset"])

    def test_rescan_resets_processing_state_when_file_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "library"
            target_dir = source_root / "family" / "2024"
            target_dir.mkdir(parents=True)
            target_file = target_dir / "Beach Sunset.mp4"
            target_file.write_bytes(b"v1")

            db_path = root / "video_archive.db"
            secrets_path = root / "secrets.json"
            initialize_database(db_path)
            source_service = SourceService(db_path, SecretStore(secrets_path))
            payload = parse_source_payload(
                {
                    "name": "Archive NAS",
                    "protocol": "smb",
                    "host": "nas.local",
                    "port": 445,
                    "root_path": str(source_root),
                }
            )
            source_service.replace_active_source(payload)
            library_service = LibraryService(db_path, source_service)
            library_service.create_scan_job()

            with connection(db_path) as conn, conn:
                conn.execute(
                    """
                    UPDATE files
                    SET conversion_state = 'done', preview_state = 'done',
                        has_preview_assets = 1, last_converted_at = '2026-07-05T10:00:00Z',
                        preview_generated_at = '2026-07-05T10:05:00Z'
                    """
                )

            target_file.write_bytes(b"v2 changed")
            library_service.create_rescan_job("family/2024")
            files = library_service.list_files("family/2024")

            self.assertEqual(files[0]["conversion_state"], "not_started")
            self.assertEqual(files[0]["preview_state"], "not_started")
            self.assertFalse(files[0]["has_preview_assets"])

    def test_tree_marks_directories_with_preview_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "library"
            target_dir = source_root / "family" / "2024"
            target_dir.mkdir(parents=True)
            (target_dir / "Beach Sunset.mp4").write_bytes(b"v1")

            db_path = root / "video_archive.db"
            secrets_path = root / "secrets.json"
            initialize_database(db_path)
            source_service = SourceService(db_path, SecretStore(secrets_path))
            payload = parse_source_payload(
                {
                    "name": "Archive NAS",
                    "protocol": "smb",
                    "host": "nas.local",
                    "port": 445,
                    "root_path": str(source_root),
                }
            )
            source_service.replace_active_source(payload)
            library_service = LibraryService(db_path, source_service)
            library_service.create_scan_job()

            with connection(db_path) as conn, conn:
                source_id = conn.execute("SELECT id FROM sources WHERE is_active = 1").fetchone()["id"]
                conn.execute(
                    """
                    INSERT INTO preview_assets (
                        id, source_id, asset_kind, file_id, directory_relative_path, image_path, metadata, created_at, updated_at
                    ) VALUES (?, ?, 'directory', NULL, ?, ?, ?, datetime('now'), datetime('now'))
                    """,
                    ("preview-1", source_id, "family", str(root / "family.gif"), "{}"),
                )

            tree = library_service.get_tree()
            family_node = tree[0]["children"][0]

            self.assertTrue(family_node["has_preview_asset"])


if __name__ == "__main__":
    unittest.main()
