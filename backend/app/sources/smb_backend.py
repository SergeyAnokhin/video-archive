"""SMB implementation of the `SourceAccess` primitives (Specification §5
"SMB"), built on `smbclient` — the high-level, `os`-module-shaped API bundled
with the `smbprotocol` package fixed in Tech Stack. `smbclient` addresses
files with UNC-style path strings (`\\\\host\\share\\sub\\path`) against a
session registered once per host via `register_session()`.

Every operation goes through `_with_retry()`: if the call fails with a
connection-level error (dropped/idle session, transient network issue), the
session is re-registered once and the call retried, satisfying the
reconnect-behavior requirement for remote sources (Specification §5).

ffmpeg and PIL need a real local file to operate on, not a Python file
object, so `local_copy()` downloads the source video to a throwaway temp
directory and `commit_new_file()` uploads a locally produced file back —
conversion/preview/tagging code is otherwise unaware it's talking to SMB.
"""

from __future__ import annotations

import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath
from typing import Iterator

import smbclient
import smbclient.path
from smbprotocol.exceptions import SMBException

from app.sources import smb_stats
from app.sources.entries import Entry, EntryStat

_RETRYABLE = (SMBException, ConnectionError, TimeoutError, OSError)
_CHUNK_SIZE = 512 * 1024


def _copy_and_count(src, dst) -> None:
    """`shutil.copyfileobj()` with each chunk also fed to `smb_stats` -- used
    by `local_copy()`/`commit_new_file()` so the conversion/preview/tagging
    download-and-upload round trip shows up in the network gauge too, not
    just `read_bytes()`/`open_range()` (those alone left a whole conversion
    job -- the most network-heavy job type -- invisible to it)."""
    while True:
        chunk = src.read(_CHUNK_SIZE)
        if not chunk:
            break
        dst.write(chunk)
        smb_stats.add_bytes_transferred(len(chunk))


def _split_share(root_path: str) -> tuple[str, str]:
    """`root_path` stores the share name plus an optional nested subpath as
    one posix-style string, e.g. `videos` or `videos/archive/2024`
    (leading/trailing slashes are ignored)."""
    cleaned = (root_path or "").strip("/\\")
    share, _, subpath = cleaned.partition("/")
    return share, subpath


class SMBBackend:
    def __init__(self, host: str, port: int | None, root_path: str, username: str | None, password: str | None):
        self.host = host
        self.port = port or 445
        self.share, self.share_subpath = _split_share(root_path)
        self.username = username
        self.password = password
        self._register_session()

    def _register_session(self) -> None:
        smbclient.register_session(self.host, username=self.username, password=self.password, port=self.port)

    def root_name(self) -> str:
        if self.share_subpath:
            return self.share_subpath.rsplit("/", 1)[-1]
        return self.share

    def _unc(self, rel_path: str) -> str:
        parts = [p for p in (self.share, self.share_subpath, rel_path) if p]
        tail = "\\".join(p.strip("/\\").replace("/", "\\") for p in parts)
        return f"\\\\{self.host}\\{tail}"

    def _with_retry(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except _RETRYABLE:
            smbclient.reset_connection_cache()
            self._register_session()
            return func(*args, **kwargs)

    def scandir(self, rel_dir: str) -> list[Entry]:
        def _do() -> list[Entry]:
            entries: list[Entry] = []
            for e in smbclient.scandir(self._unc(rel_dir)):
                if e.is_dir():
                    entries.append(Entry(name=e.name, is_dir=True, stat=None))
                else:
                    st = e.stat()
                    entries.append(
                        Entry(
                            name=e.name,
                            is_dir=False,
                            stat=EntryStat(
                                size=st.st_size,
                                modified_at=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                            ),
                        )
                    )
            return entries

        try:
            return self._with_retry(_do)
        except OSError:
            return []

    def exists(self, rel_path: str) -> bool:
        try:
            return bool(self._with_retry(smbclient.path.exists, self._unc(rel_path)))
        except OSError:
            return False

    def is_dir(self, rel_path: str) -> bool:
        try:
            return bool(self._with_retry(smbclient.path.isdir, self._unc(rel_path)))
        except OSError:
            return False

    def stat_rel(self, rel_path: str) -> EntryStat:
        st = self._with_retry(smbclient.stat, self._unc(rel_path))
        return EntryStat(size=st.st_size, modified_at=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat())

    @contextmanager
    def local_copy(self, rel_path: str) -> Iterator[Path]:
        tmp_dir = Path(tempfile.mkdtemp(prefix="va_smb_"))
        local_path = tmp_dir / PureWindowsPath(rel_path).name
        try:
            def _download() -> None:
                with smbclient.open_file(self._unc(rel_path), mode="rb") as remote_f, open(local_path, "wb") as local_f:
                    _copy_and_count(remote_f, local_f)

            self._with_retry(_download)
            yield local_path
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @contextmanager
    def stage_output_dir(self, rel_dir: str) -> Iterator[Path]:
        # Any local scratch directory works: `commit_new_file()` uploads
        # bytes rather than doing a same-volume move.
        tmp_dir = Path(tempfile.mkdtemp(prefix="va_smb_out_"))
        try:
            yield tmp_dir
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def commit_new_file(self, local_path: Path, dest_rel_path: str) -> None:
        def _upload() -> None:
            # Unlike a same-volume local move, the destination's parent
            # directory chain (e.g. `.video-archive/backups/`) may not exist
            # yet on the share -- smbclient.open_file() doesn't create it.
            parent = PureWindowsPath(dest_rel_path).parent
            if str(parent) not in ("", "."):
                smbclient.makedirs(self._unc(str(parent)), exist_ok=True)
            with open(local_path, "rb") as local_f, smbclient.open_file(self._unc(dest_rel_path), mode="wb") as remote_f:
                _copy_and_count(local_f, remote_f)

        self._with_retry(_upload)
        if local_path.exists():
            local_path.unlink()

    def remote_rename(self, rel_path: str, new_rel_path: str) -> None:
        self._with_retry(smbclient.rename, self._unc(rel_path), self._unc(new_rel_path))

    def remote_remove(self, rel_path: str) -> None:
        self._with_retry(smbclient.remove, self._unc(rel_path))

    def remote_mkdir(self, rel_path: str) -> None:
        self._with_retry(smbclient.mkdir, self._unc(rel_path))

    def remote_rmdir(self, rel_path: str) -> None:
        self._with_retry(smbclient.rmdir, self._unc(rel_path))

    def read_bytes(self, rel_path: str) -> bytes:
        def _read() -> bytes:
            with smbclient.open_file(self._unc(rel_path), mode="rb") as f:
                return f.read()

        data = self._with_retry(_read)
        smb_stats.add_bytes_transferred(len(data))
        return data

    def open_range(self, rel_path: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        def _open():
            return smbclient.open_file(self._unc(rel_path), mode="rb")

        f = self._with_retry(_open)
        try:
            size = f.seek(0, 2)
            real_end = size - 1 if end is None else min(end, size - 1)
            f.seek(start)
            remaining = real_end - start + 1
            while remaining > 0:
                chunk = f.read(min(_CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                smb_stats.add_bytes_transferred(len(chunk))
                yield chunk
        finally:
            f.close()

    def size_of(self, rel_path: str) -> int:
        return self.stat_rel(rel_path).size

    def direct_path(self, rel_path: str) -> str:
        return self._unc(rel_path)

    def close(self) -> None:
        pass


def test_connection(host: str, port: int | None, root_path: str, username: str | None, password: str | None) -> tuple[bool, str | None]:
    """Attempt a session + directory listing without persisting anything;
    used by `POST /api/source/test-connection`."""
    try:
        backend = SMBBackend(host, port, root_path, username, password)
        backend.scandir("")
        if not backend.is_dir(""):
            return False, f"Path is not a directory: {backend.direct_path('')}"
        return True, None
    except Exception as exc:  # noqa: BLE001 - surfaced to the user as a plain message
        return False, str(exc)
