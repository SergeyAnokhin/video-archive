from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    app_version: str
    host: str
    port: int
    data_dir: Path
    database_path: Path
    secrets_path: Path


def load_config(base_dir: Path | None = None, environ: dict[str, str] | None = None) -> AppConfig:
    env = dict(environ or os.environ)
    backend_dir = base_dir or Path(__file__).resolve().parents[1]

    env_file = backend_dir / ".env.local"
    if env_file.exists():
        env = {**_load_env_file(env_file), **env}

    data_dir = Path(env.get("VIDEO_ARCHIVE_DATA_DIR", backend_dir / ".local"))
    database_path = Path(env.get("VIDEO_ARCHIVE_DB_PATH", data_dir / "video_archive.db"))
    secrets_path = Path(env.get("VIDEO_ARCHIVE_SECRETS_PATH", data_dir / "secrets.json"))

    return AppConfig(
        app_version=env.get("VIDEO_ARCHIVE_APP_VERSION", "0.1.0"),
        host=env.get("VIDEO_ARCHIVE_HOST", "127.0.0.1"),
        port=int(env.get("VIDEO_ARCHIVE_PORT", "18637")),
        data_dir=data_dir,
        database_path=database_path,
        secrets_path=secrets_path,
    )


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"'")
    return values
