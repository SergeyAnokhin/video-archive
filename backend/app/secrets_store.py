"""Local secrets file access (Specification §18, Tech Stack): API keys and
other credentials never enter the SQLite database — they live in a
git-ignored `.env`-style file next to the backend, read/written with
`python-dotenv`.

Convention for other modules that need the secrets file path directly (e.g.
`app/backup.py` zipping/restoring it): import this module and use
`secrets_store.SECRETS_PATH` via attribute access, not
`from app.config import SECRETS_PATH`. Tests isolate every case that touches
real secrets by monkeypatching `secrets_store.SECRETS_PATH` (see
`tests/conftest.py`'s `isolated_secrets_file` fixture) — a direct
`from app.config import SECRETS_PATH` binds the pre-patch value and silently
reads/writes the real `backend/secrets.env` instead of the per-test temp file.

Provider API keys are keyed by `app/provider_entries.py` entry id (not
provider type), since a user can add multiple entries per provider type —
see `_entry_key_name()`. Only key *presence* and a masked suffix should ever
be exposed to the frontend, never the value itself.
"""

from __future__ import annotations

from dotenv import dotenv_values, set_key, unset_key

from app.config import SECRETS_PATH


def _entry_key_name(entry_id: str) -> str:
    return f"PROVIDER_ENTRY_{entry_id.replace('-', '_').upper()}_API_KEY"


def get_entry_api_key(entry_id: str) -> str | None:
    if not SECRETS_PATH.exists():
        return None
    values = dotenv_values(SECRETS_PATH)
    return values.get(_entry_key_name(entry_id)) or None


def set_entry_api_key(entry_id: str, api_key: str) -> None:
    if not SECRETS_PATH.exists():
        SECRETS_PATH.touch()
    set_key(str(SECRETS_PATH), _entry_key_name(entry_id), api_key, quote_mode="never")


def has_entry_api_key(entry_id: str) -> bool:
    return bool(get_entry_api_key(entry_id))


def delete_entry_api_key(entry_id: str) -> None:
    if not SECRETS_PATH.exists():
        return
    unset_key(str(SECRETS_PATH), _entry_key_name(entry_id))


def get_entry_api_key_suffix(entry_id: str, length: int = 4) -> str | None:
    api_key = get_entry_api_key(entry_id)
    return api_key[-length:] if api_key else None


# Source credentials (Specification §5, §18): historically only one active
# source existed at a time, so a fixed key pair was enough. Multiple saved
# sources now need distinct credentials, so new sources get a key pair keyed
# by their own id (see `_source_username_key`/`_source_password_key` below);
# these constants are kept only so rows created before that change keep
# resolving via `get_source_credentials_for`.
SOURCE_USERNAME_REF = "SOURCE_USERNAME"
SOURCE_SECRET_REF = "SOURCE_PASSWORD"


def _source_username_key(source_id: str) -> str:
    return f"SOURCE_{source_id.replace('-', '_').upper()}_USERNAME"


def _source_password_key(source_id: str) -> str:
    return f"SOURCE_{source_id.replace('-', '_').upper()}_PASSWORD"


def get_source_credentials_for(
    username_ref: str | None, secret_ref: str | None
) -> tuple[str | None, str | None]:
    if not username_ref or not secret_ref or not SECRETS_PATH.exists():
        return None, None
    values = dotenv_values(SECRETS_PATH)
    return values.get(username_ref) or None, values.get(secret_ref) or None


def set_source_credentials_for(source_id: str, username: str, password: str) -> tuple[str, str]:
    if not SECRETS_PATH.exists():
        SECRETS_PATH.touch()
    username_ref, secret_ref = _source_username_key(source_id), _source_password_key(source_id)
    set_key(str(SECRETS_PATH), username_ref, username, quote_mode="never")
    set_key(str(SECRETS_PATH), secret_ref, password, quote_mode="never")
    return username_ref, secret_ref


def delete_source_credentials_for(username_ref: str | None, secret_ref: str | None) -> None:
    if not SECRETS_PATH.exists():
        return
    if username_ref:
        unset_key(str(SECRETS_PATH), username_ref)
    if secret_ref:
        unset_key(str(SECRETS_PATH), secret_ref)


def get_source_credentials() -> tuple[str | None, str | None]:
    return get_source_credentials_for(SOURCE_USERNAME_REF, SOURCE_SECRET_REF)


def set_source_credentials(username: str, password: str) -> None:
    if not SECRETS_PATH.exists():
        SECRETS_PATH.touch()
    set_key(str(SECRETS_PATH), SOURCE_USERNAME_REF, username, quote_mode="never")
    set_key(str(SECRETS_PATH), SOURCE_SECRET_REF, password, quote_mode="never")


def clear_source_credentials() -> None:
    delete_source_credentials_for(SOURCE_USERNAME_REF, SOURCE_SECRET_REF)


def has_source_credentials() -> bool:
    username, password = get_source_credentials()
    return bool(username and password)
