from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.db import initialize_database
from app.errors import ApiError
from app.secrets import SecretStore
from app.source_service import LOCAL_SOURCE_PROTOCOL_SENTINEL, SourceService, parse_source_payload


class SourceServiceTests(unittest.TestCase):
    def test_replace_active_source_stores_credentials_outside_database(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "video_archive.db"
            secrets_path = root / "secrets.json"
            initialize_database(db_path)
            service = SourceService(db_path, SecretStore(secrets_path))

            payload = parse_source_payload(
                {
                    "name": "Archive NAS",
                    "protocol": "smb",
                    "host": "nas.local",
                    "port": 445,
                    "root_path": "/videos",
                    "username": "user",
                    "password": "secret",
                }
            )

            saved = service.replace_active_source(payload)

            self.assertEqual(saved["name"], "Archive NAS")
            self.assertEqual(saved["username"], "user")
            self.assertTrue(saved["has_password"])
            self.assertTrue(secrets_path.exists())
            self.assertNotIn("password", saved)

    def test_test_connection_uses_default_port_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "video_archive.db"
            secrets_path = root / "secrets.json"
            initialize_database(db_path)
            service = SourceService(db_path, SecretStore(secrets_path))

            payload = parse_source_payload(
                {
                    "name": "Archive NAS",
                    "protocol": "sftp",
                    "host": "nas.local",
                    "root_path": "/videos",
                }
            )

            calls: list[tuple[str, int]] = []

            def fake_connector(host: str, port: int) -> None:
                calls.append((host, port))

            result = service.test_connection(payload, connector=fake_connector)

            self.assertEqual(result["port"], 22)
            self.assertEqual(calls, [("nas.local", 22)])

    def test_parse_source_payload_rejects_unknown_protocol(self) -> None:
        with self.assertRaises(ApiError):
            parse_source_payload(
                {
                    "name": "Archive NAS",
                    "protocol": "nfs",
                    "host": "nas.local",
                    "root_path": "/videos",
                }
            )

    def test_parse_source_payload_accepts_local_without_host(self) -> None:
        payload = parse_source_payload(
            {
                "name": "Local Test Library",
                "protocol": "local",
                "root_path": "C:\\Videos",
            }
        )

        self.assertEqual(payload.protocol, "local")
        self.assertEqual(payload.host, LOCAL_SOURCE_PROTOCOL_SENTINEL)
        self.assertIsNone(payload.port)

    def test_test_connection_for_local_source_skips_socket_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "video_archive.db"
            secrets_path = root / "secrets.json"
            initialize_database(db_path)
            service = SourceService(db_path, SecretStore(secrets_path))

            payload = parse_source_payload(
                {
                    "name": "Local Test Library",
                    "protocol": "local",
                    "root_path": str(root),
                }
            )

            calls: list[tuple[str, int]] = []

            def fake_connector(host: str, port: int) -> None:
                calls.append((host, port))

            result = service.test_connection(payload, connector=fake_connector)

            self.assertTrue(result["ok"])
            self.assertEqual(result["port"], None)
            self.assertEqual(calls, [])

    def test_replace_active_source_round_trips_local_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "library"
            source_root.mkdir()
            db_path = root / "video_archive.db"
            secrets_path = root / "secrets.json"
            initialize_database(db_path)
            service = SourceService(db_path, SecretStore(secrets_path))

            payload = parse_source_payload(
                {
                    "name": "Local Test Library",
                    "protocol": "local",
                    "root_path": str(source_root),
                }
            )

            saved = service.replace_active_source(payload)

            self.assertEqual(saved["protocol"], "local")
            self.assertEqual(saved["host"], "")
            self.assertEqual(saved["root_path"], str(source_root))

    def test_list_local_directories_returns_children_for_absolute_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "alpha").mkdir()
            (root / "beta").mkdir()
            db_path = root / "video_archive.db"
            secrets_path = root / "secrets.json"
            initialize_database(db_path)
            service = SourceService(db_path, SecretStore(secrets_path))

            listing = service.list_local_directories(str(root))

            self.assertEqual(listing["path"], str(root.resolve()))
            self.assertEqual([entry["name"] for entry in listing["directories"]], ["alpha", "beta"])
            self.assertIn("favorites", listing)

    def test_list_local_directories_accepts_trailing_separator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "alpha").mkdir()
            db_path = root / "video_archive.db"
            secrets_path = root / "secrets.json"
            initialize_database(db_path)
            service = SourceService(db_path, SecretStore(secrets_path))

            listing = service.list_local_directories(f"{root}\\")

            self.assertEqual(listing["path"], str(root.resolve()))
            self.assertEqual([entry["name"] for entry in listing["directories"]], ["alpha"])

    def test_replace_active_source_keeps_existing_password_when_new_payload_omits_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_root = root / "library"
            source_root.mkdir()
            db_path = root / "video_archive.db"
            secrets_path = root / "secrets.json"
            initialize_database(db_path)
            service = SourceService(db_path, SecretStore(secrets_path))

            initial = parse_source_payload(
                {
                    "name": "Archive NAS",
                    "protocol": "smb",
                    "host": "nas.local",
                    "port": 445,
                    "root_path": str(source_root),
                    "username": "user",
                    "password": "secret",
                }
            )
            service.replace_active_source(initial)

            updated = parse_source_payload(
                {
                    "name": "Archive NAS 2",
                    "protocol": "smb",
                    "host": "nas-2.local",
                    "port": 445,
                    "root_path": str(source_root),
                    "username": "user",
                }
            )
            saved = service.replace_active_source(updated)

            self.assertEqual(saved["name"], "Archive NAS 2")
            self.assertTrue(saved["has_password"])


if __name__ == "__main__":
    unittest.main()
