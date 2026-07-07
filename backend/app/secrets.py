from __future__ import annotations

import json
from pathlib import Path


class SecretStore:
    def __init__(self, secrets_path: Path) -> None:
        self._path = secrets_path

    def upsert_source_credentials(self, source_id: str, username: str | None, password: str | None) -> tuple[str | None, str | None]:
        secrets = self._read()
        username_ref = None
        secret_ref = None

        if username:
            username_ref = f"source:{source_id}:username"
            secrets[username_ref] = username

        if password:
            secret_ref = f"source:{source_id}:password"
            secrets[secret_ref] = password

        self._write(secrets)
        return username_ref, secret_ref

    def get(self, ref: str | None) -> str | None:
        if not ref:
            return None
        return self._read().get(ref)

    def upsert_provider_api_key(self, provider_id: str, api_key: str | None) -> str | None:
        ref = f"provider:{provider_id}:api_key"
        secrets = self._read()
        if api_key is None:
            return ref if ref in secrets else None
        normalized = api_key.strip()
        if not normalized:
            return ref if ref in secrets else None
        secrets[ref] = normalized
        self._write(secrets)
        return ref

    def get_provider_api_key(self, provider_id: str, legacy_provider_name: str | None = None) -> str | None:
        value = self.get(f"provider:{provider_id}:api_key")
        if value or not legacy_provider_name or legacy_provider_name == provider_id:
            return value
        return self.get(f"provider:{legacy_provider_name}:api_key")

    def _read(self) -> dict[str, str]:
        if not self._path.exists():
            return {}

        return json.loads(self._path.read_text(encoding="utf-8"))

    def _write(self, secrets: dict[str, str]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(secrets, indent=2, sort_keys=True), encoding="utf-8")
        temp_path.replace(self._path)
