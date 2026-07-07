from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.conversion_profile_service import ConversionProfileService
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

    def test_get_file_includes_media_info_and_last_conversion_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "library"
            target_dir = source_root / "family"
            target_dir.mkdir(parents=True)
            (target_dir / "Beach Sunset.mp4").write_bytes(b"video-data")

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
            profile_service = ConversionProfileService(db_path)
            library_service = LibraryService(db_path, source_service, profile_service, ffprobe_binary="fake-ffprobe")
            library_service.create_scan_job()
            file_id = library_service.list_files("family")[0]["id"]

            with connection(db_path) as conn, conn:
                conn.execute(
                    """
                    UPDATE files
                    SET last_conversion_profile_id = ?, last_converted_at = ?
                    WHERE id = ?
                    """,
                    ("default-h265-mp4", "2026-07-07T10:00:00Z", file_id),
                )

            library_service._probe_media_info = lambda path: {
                "video_codec": "hevc",
                "video_profile": "Main",
                "audio_codec": "aac",
                "width": 1920,
                "height": 1080,
                "display_aspect_ratio": "16:9",
                "frame_rate": 29.97,
                "pixel_format": "yuv420p",
                "duration_seconds": 42.5,
                "bitrate_bps": 1_800_000,
                "size_bytes": 123456,
            }

            file_payload = library_service.get_file(file_id)

            self.assertEqual(file_payload["last_conversion_profile"]["id"], "default-h265-mp4")
            self.assertEqual(file_payload["last_conversion_profile"]["video_codec"], "h265")
            self.assertEqual(file_payload["media_info"]["width"], 1920)
            self.assertEqual(file_payload["media_info"]["display_aspect_ratio"], "16:9")
            self.assertEqual(file_payload["media_info"]["bitrate_bps"], 1_800_000)

    def test_register_generated_file_marks_output_as_generated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "library"
            target_dir = source_root / "family"
            target_dir.mkdir(parents=True)
            (target_dir / "Beach Sunset.mp4").write_bytes(b"video-data")

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
            source_file_id = library_service.list_files("family")[0]["id"]

            generated_path = target_dir / "Beach Sunset.__test__tune-h265-side-800-crf-20.mp4"
            generated_path.write_bytes(b"generated")
            payload = library_service.register_generated_file(
                result={
                    "path": str(generated_path),
                    "relative_path": "family/Beach Sunset.__test__tune-h265-side-800-crf-20.mp4",
                    "file_name": generated_path.name,
                    "extension": ".mp4",
                    "size_bytes": int(generated_path.stat().st_size),
                    "modified_at": "2026-07-07T10:00:00Z",
                },
                source_file_id=source_file_id,
                generated_from_job_id="job-123",
                generated_kind="tune",
            )

            self.assertTrue(payload["is_generated"])
            self.assertEqual(payload["generated_kind"], "tune")
            self.assertEqual(payload["generated_from_job_id"], "job-123")
            self.assertEqual(payload["generated_from_file_id"], source_file_id)

    def test_move_file_updates_relative_path_and_keeps_generated_marker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "library"
            source_dir = source_root / "family"
            source_dir.mkdir(parents=True)
            generated_path = source_dir / "Generated.mp4"
            generated_path.write_bytes(b"video-data")

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
            file_id = library_service.list_files("family")[0]["id"]
            with connection(db_path) as conn, conn:
                conn.execute(
                    """
                    UPDATE files
                    SET generated_from_job_id = 'job-1', generated_kind = 'tune'
                    WHERE id = ?
                    """,
                    (file_id,),
                )

            moved = library_service.move_file(file_id, "family/archive")

            self.assertEqual(moved["relative_path"], "family/archive/Generated.mp4")
            self.assertEqual(moved["generated_kind"], "tune")
            self.assertTrue((source_root / "family" / "archive" / "Generated.mp4").exists())

    def test_delete_file_removes_disk_file_and_row(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "library"
            target_dir = source_root / "family"
            target_dir.mkdir(parents=True)
            target_file = target_dir / "Beach Sunset.mp4"
            target_file.write_bytes(b"video-data")

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
            file_id = library_service.list_files("family")[0]["id"]

            library_service.delete_file(file_id)

            self.assertFalse(target_file.exists())
            self.assertEqual(library_service.list_files("family"), [])


if __name__ == "__main__":
    unittest.main()
