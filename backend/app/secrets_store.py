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

Provider API keys are keyed by provider type — one key per provider, shared
by every `app/provider_entries.py` entry (model) of that type, see
`_provider_key_name()`. Before that, keys were stored per entry id
(`_entry_key_name()`); `migrate_entry_keys_to_provider_keys()` copies them
over once and leaves the old per-entry values in place so nothing is lost
when one provider type had several different keys. Only key *presence* and
a masked suffix should ever be exposed to the frontend, never the value
itself.
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


def _provider_key_name(provider_type: str) -> str:
    return f"PROVIDER_{provider_type.upper()}_API_KEY"


def get_provider_api_key(provider_type: str) -> str | None:
    if not SECRETS_PATH.exists():
        return None
    values = dotenv_values(SECRETS_PATH)
    return values.get(_provider_key_name(provider_type)) or None


def set_provider_api_key(provider_type: str, api_key: str) -> None:
    if not SECRETS_PATH.exists():
        SECRETS_PATH.touch()
    set_key(str(SECRETS_PATH), _provider_key_name(provider_type), api_key, quote_mode="never")


def delete_provider_api_key(provider_type: str) -> None:
    if not SECRETS_PATH.exists():
        return
    unset_key(str(SECRETS_PATH), _provider_key_name(provider_type))


def get_provider_api_key_suffix(provider_type: str, length: int = 4) -> str | None:
    api_key = get_provider_api_key(provider_type)
    return api_key[-length:] if api_key else None


def migrate_entry_keys_to_provider_keys(entries: list[tuple[str, str]]) -> None:
    """One-time move to one key per provider type. `entries` is
    `(entry_id, provider_type)` in priority order; for every type that has
    no provider key yet, the first entry with a key wins. Old per-entry
    keys stay in the file -- see `legacy_entry_keys_differ()`."""
    for entry_id, provider_type in entries:
        if get_provider_api_key(provider_type):
            continue
        api_key = get_entry_api_key(entry_id)
        if api_key:
            set_provider_api_key(provider_type, api_key)


def legacy_entry_keys_differ(provider_type: str, entry_ids: list[str]) -> bool:
    """True when a leftover per-entry key of `entry_ids` (all of
    `provider_type`) differs from the provider key -- i.e. migration had to
    pick one of several keys and the user should check it."""
    provider_key = get_provider_api_key(provider_type)
    return any(
        (legacy := get_entry_api_key(entry_id)) and legacy != provider_key for entry_id in entry_ids
    )


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
