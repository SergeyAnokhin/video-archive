from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.db import connection, initialize_database
from app.provider_settings_service import ProviderSettingsService
from app.secrets import SecretStore


class ProviderSettingsServiceTests(unittest.TestCase):
    def test_dynamic_entries_preserve_order_and_runtime_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "video_archive.db"
            secrets_path = root / "secrets.json"
            initialize_database(db_path)
            service = ProviderSettingsService(db_path, SecretStore(secrets_path))

            saved = service.update_settings(
                [
                    {
                        "id": "gemini-primary",
                        "label": "Gemini Primary",
                        "provider": "gemini",
                        "enabled": True,
                        "vision_model": "gemini-2.0-flash",
                        "text_model": "",
                        "prefer_batch": True,
                        "api_key": "gemini-key",
                    },
                    {
                        "id": "openrouter-fallback",
                        "label": "Fallback",
                        "provider": "openrouter",
                        "enabled": True,
                        "vision_model": "openai/gpt-4.1-mini",
                        "text_model": "",
                        "prefer_batch": True,
                        "api_key": "openrouter-key",
                    },
                ]
            )

            self.assertEqual([entry["id"] for entry in saved], ["gemini-primary", "openrouter-fallback"])
            self.assertEqual(service.resolve_provider()["id"], "gemini-primary")
            self.assertEqual(service.resolve_provider(provider_name="openrouter")["id"], "openrouter-fallback")
            self.assertEqual(service.get_runtime_provider(provider_id="openrouter-fallback")["api_key"], "openrouter-key")

    def test_legacy_payload_is_read_with_legacy_secret_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db_path = root / "video_archive.db"
            secrets_path = root / "secrets.json"
            initialize_database(db_path)
            secret_store = SecretStore(secrets_path)
            service = ProviderSettingsService(db_path, secret_store)
            secret_store.upsert_provider_api_key("openrouter", "legacy-key")

            with connection(db_path) as conn, conn:
                conn.execute(
                    """
                    INSERT INTO app_settings (section, payload, created_at, updated_at)
                    VALUES (?, ?, '2026-07-07T00:00:00Z', '2026-07-07T00:00:00Z')
                    """,
                    (
                        "providers",
                        json.dumps(
                            [
                                {
                                    "provider": "openrouter",
                                    "enabled": True,
                                    "vision_model": "openrouter/test",
                                    "text_model": "",
                                    "prefer_batch": True,
                                }
                            ]
                        ),
                    ),
                )

            settings = service.get_settings()
            self.assertEqual(settings[0]["id"], "openrouter")
            self.assertTrue(settings[0]["api_key_configured"])
            self.assertEqual(service.get_runtime_provider(provider_id="openrouter")["api_key"], "legacy-key")


if __name__ == "__main__":
    unittest.main()
