"""Shared fixtures: every test gets its own temp SQLite db and never touches
the developer's real `backend/video_archive.db` (which may have a real
worker/dev-server attached to it).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

import app.db as db_module
import app.secrets_store as secrets_store_module


@pytest.fixture(autouse=True)
def isolated_secrets_file(tmp_path, monkeypatch):
    """Every test gets its own secrets file, never the developer's real
    `backend/secrets.env` (Stage 6 tagging/provider tests write API keys)."""
    monkeypatch.setattr(secrets_store_module, "SECRETS_PATH", tmp_path / "secrets.env")


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)
    db_module.init_db()
    return db_module.get_engine()


@pytest.fixture()
def source(engine, tmp_path):
    """An active `local` source row pointing at an empty temp directory."""
    source_root = tmp_path / "source"
    source_root.mkdir()
    source_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sources (id, name, protocol, root_path, is_active, created_at, updated_at) "
                "VALUES (:id, 'Test', 'local', :root, 1, :now, :now)"
            ),
            {"id": source_id, "root": str(source_root), "now": now},
        )
    return {"id": source_id, "root": source_root}


def make_files(root: Path, count: int, subdir: str = "clips") -> None:
    folder = root / subdir
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (folder / f"clip_{i:04d}.mp4").write_bytes(b"0")


class FakeSMBFS:
    """In-memory fake of the tiny slice of the `smbclient` module API used by
    `app/sources/smb_backend.py`, so SMB-source tests exercise the real
    `SMBBackend` code (UNC path building, retry-on-error, upload/download
    plumbing) without a real network/SMB server (none is available in this
    environment). Keyed by host/share so `SMBBackend._unc()`'s output round-trips
    back to a relative posix path via `_to_rel()`.
    """

    def __init__(self, host: str, share: str):
        self.host = host
        self.share = share
        self.prefix = f"\\\\{host}\\{share}"
        self.files: dict[str, tuple[bytes, float]] = {}
        self.dirs: set[str] = set()
        self.fail_next: list[Exception] = []

    def _to_rel(self, unc_path: str) -> str:
        assert unc_path.startswith(self.prefix), f"{unc_path} not under {self.prefix}"
        return unc_path[len(self.prefix):].strip("\\").replace("\\", "/")

    def _maybe_fail(self) -> None:
        if self.fail_next:
            raise self.fail_next.pop(0)

    def seed(self, rel_path: str, content: bytes) -> None:
        self.files[rel_path] = (content, datetime.now(timezone.utc).timestamp())

    def read(self, rel_path: str) -> bytes:
        return self.files[rel_path][0]

    def exists(self, rel_path: str) -> bool:
        if rel_path == "":
            return True
        return (
            rel_path in self.files
            or rel_path in self.dirs
            or any(k.startswith(rel_path + "/") for k in self.files)
        )

    # -- smbclient-shaped API -------------------------------------------------

    def register_session(self, *a, **k) -> None:
        self._maybe_fail()

    def reset_connection_cache(self, *a, **k) -> None:
        pass

    def scandir(self, unc_path: str, **kwargs):
        self._maybe_fail()
        rel_dir = self._to_rel(unc_path)
        prefix = f"{rel_dir}/" if rel_dir else ""
        seen_dirs: set[str] = set()
        entries = []
        for key in list(self.files):
            if not key.startswith(prefix):
                continue
            remainder = key[len(prefix):]
            if "/" in remainder:
                child_dir = remainder.split("/", 1)[0]
                if child_dir not in seen_dirs:
                    seen_dirs.add(child_dir)
                    entries.append(_FakeEntry(child_dir, True, None))
            else:
                content, mtime = self.files[key]
                entries.append(_FakeEntry(remainder, False, _FakeStat(len(content), mtime)))
        return entries

    def stat(self, unc_path: str, **kwargs):
        self._maybe_fail()
        rel_path = self._to_rel(unc_path)
        content, mtime = self.files[rel_path]
        return _FakeStat(len(content), mtime)

    def open_file(self, unc_path: str, mode: str = "r", **kwargs):
        self._maybe_fail()
        rel_path = self._to_rel(unc_path)
        if "w" in mode:
            # Mirrors real SMB: opening a file for write does not create
            # missing parent directories (unlike a local filesystem move).
            parent = rel_path.rsplit("/", 1)[0] if "/" in rel_path else ""
            if not self.exists(parent):
                raise OSError(2, "No such file or directory", unc_path)
        return _FakeSMBFile(self, rel_path, mode)

    def rename(self, src_unc: str, dst_unc: str, **kwargs) -> None:
        self._maybe_fail()
        src_rel, dst_rel = self._to_rel(src_unc), self._to_rel(dst_unc)
        self.files[dst_rel] = self.files.pop(src_rel)

    def remove(self, unc_path: str, **kwargs) -> None:
        self._maybe_fail()
        del self.files[self._to_rel(unc_path)]

    def mkdir(self, unc_path: str, **kwargs) -> None:
        self._maybe_fail()
        self.dirs.add(self._to_rel(unc_path))

    def makedirs(self, unc_path: str, exist_ok: bool = False, **kwargs) -> None:
        self._maybe_fail()
        rel_path = self._to_rel(unc_path)
        if not exist_ok and self.exists(rel_path):
            raise OSError(17, "File exists", unc_path)
        parts = rel_path.split("/")
        for i in range(len(parts)):
            self.dirs.add("/".join(parts[: i + 1]))

    def rmdir(self, unc_path: str, **kwargs) -> None:
        self._maybe_fail()
        self.dirs.discard(self._to_rel(unc_path))

    def path_exists(self, unc_path: str, **kwargs) -> bool:
        return self.exists(self._to_rel(unc_path))

    def path_isdir(self, unc_path: str, **kwargs) -> bool:
        rel_path = self._to_rel(unc_path)
        return rel_path == "" or (rel_path not in self.files and self.exists(rel_path))


@dataclass(frozen=True)
class _FakeStat:
    st_size: int
    st_mtime: float


class _FakeEntry:
    def __init__(self, name: str, is_directory: bool, stat_result):
        self.name = name
        self._is_dir = is_directory
        self._stat = stat_result

    def is_dir(self) -> bool:
        return self._is_dir

    def stat(self):
        return self._stat


class _FakeSMBFile:
    def __init__(self, fs: FakeSMBFS, rel_path: str, mode: str):
        self._fs = fs
        self._rel_path = rel_path
        self._writing = "w" in mode
        content = b"" if self._writing else fs.files[rel_path][0]
        import io

        self._buf = io.BytesIO(content)

    def read(self, n: int = -1) -> bytes:
        return self._buf.read(n)

    def write(self, data: bytes) -> int:
        return self._buf.write(data)

    def seek(self, offset: int, whence: int = 0) -> int:
        return self._buf.seek(offset, whence)

    def close(self) -> None:
        if self._writing:
            self._fs.files[self._rel_path] = (self._buf.getvalue(), datetime.now(timezone.utc).timestamp())
        self._buf.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        self.close()


@pytest.fixture()
def fake_smb(monkeypatch):
    """Patches `smbclient`'s module-level functions with an in-memory fake so
    `app.sources.smb_backend.SMBBackend` can be exercised without a real SMB
    server. Returns the `FakeSMBFS` instance for seeding/assertions."""
    import smbclient
    import smbclient.path

    fs = FakeSMBFS(host="testnas", share="testshare")
    monkeypatch.setattr(smbclient, "register_session", fs.register_session)
    monkeypatch.setattr(smbclient, "reset_connection_cache", fs.reset_connection_cache)
    monkeypatch.setattr(smbclient, "scandir", fs.scandir)
    monkeypatch.setattr(smbclient, "stat", fs.stat)
    monkeypatch.setattr(smbclient, "open_file", fs.open_file)
    monkeypatch.setattr(smbclient, "rename", fs.rename)
    monkeypatch.setattr(smbclient, "remove", fs.remove)
    monkeypatch.setattr(smbclient, "mkdir", fs.mkdir)
    monkeypatch.setattr(smbclient, "makedirs", fs.makedirs)
    monkeypatch.setattr(smbclient, "rmdir", fs.rmdir)
    monkeypatch.setattr(smbclient.path, "exists", fs.path_exists)
    monkeypatch.setattr(smbclient.path, "isdir", fs.path_isdir)
    return fs


@pytest.fixture()
def smb_source(engine, fake_smb):
    """An active `smb` source row pointing at the `fake_smb` fake share."""
    source_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sources (id, name, protocol, host, port, root_path, "
                "username_ref, secret_ref, is_active, created_at, updated_at) "
                "VALUES (:id, 'Test SMB', 'smb', :host, 445, :root, 'SOURCE_USERNAME', 'SOURCE_PASSWORD', "
                "1, :now, :now)"
            ),
            {"id": source_id, "host": fake_smb.host, "root": fake_smb.share, "now": now},
        )
    return {"id": source_id, "fs": fake_smb}


def make_video(path: Path, *, size: str = "160x120", duration: float = 0.5) -> None:
    """Encode a tiny real video with ffmpeg (h264/mp4-ish by default) so
    conversion tests exercise real ffmpeg/ffprobe instead of fixture bytes."""
    import subprocess

    path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate=5",
            "-pix_fmt", "yuv420p",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to generate test video: {result.stderr[-500:]}")


def make_image(path: Path, *, size: tuple[int, int] = (160, 120), color: tuple[int, int, int] = (0, 0, 0)) -> None:
    """Writes a real, decodable JPEG/PNG (PIL, already a dependency) so
    standalone-image tests don't need ffmpeg."""
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, color).save(path)
