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

`local_copy()` has an opt-in fast path (`direct_access_enabled`, per-source
setting, Windows-only): when `app.sources.windows_unc.available()` says the
OS itself can already reach this host directly, it yields the real UNC path
instead of downloading -- see `windows_unc.py` for why this is a separate
session from the one `smbclient`/`register_session()` manages here, and why
it's a best-effort fast path with automatic fallback rather than a hard
requirement.

`commit_new_file()`/`remote_rename()`/`remote_remove()` have a matching
opt-in fast path, gated by both the same per-source setting/UNC probe *and*
an explicit `allow_direct` argument each caller passes (conversion is the
only caller that ever sets it `True`, driven by the global
`conversion_settings.direct_write_enabled` switch -- everyone else keeps
today's smbclient upload/rename/remove behavior unconditionally). When
active, these do a raw filesystem rename/remove against the UNC path
instead of smbclient traffic; any `OSError` falls back to the smbclient
path exactly like `local_copy()` falls back to downloading.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath
from typing import Iterator

import smbclient
import smbclient.path
from smbprotocol.exceptions import SMBException

from app.sources import smb_stats, windows_unc
from app.sources.entries import Entry, EntryStat

_RETRYABLE = (SMBException, ConnectionError, TimeoutError, OSError)
# 4 MiB (user request, chat 2026-07-25 -- slow preview generation on a
# high-latency SMB share): fewer round-trips per file than the prior 512 KiB
# chunk size, without materially changing peak memory (still one chunk in
# flight at a time per read loop).
_CHUNK_SIZE = 4 * 1024 * 1024

# `smbclient` caches one connection per host in a process-wide registry, so
# every `SMBBackend` instance for the same host actually shares a single
# underlying socket/session -- concurrent requests (e.g. a media-info lookup
# racing a conversion job's download) issue SMB protocol messages on it at
# the same time, which the server/library isn't guaranteed to interleave
# safely (observed as "SMBException: ... 0 credits are available" and
# "read of closed file" when one thread's retry reset the shared connection
# out from under another thread's in-flight read). Serializing all backend
# calls through this lock keeps SMB traffic to one operation at a time.
#
# This lock is process-wide (every host, every source), not per-host: it
# only guards `smbclient`'s shared connection pool, not a specific share, so
# splitting it per-host wouldn't actually stop two hosts' calls from racing
# the same pool internals.
_smb_lock = threading.Lock()

# Separate, always-fast lock guarding *metadata about* `_smb_lock` (who's
# holding it and since when) -- deliberately never nested inside `_smb_lock`
# itself, so a caller stuck on a hung SMB read (see `_locked()` below) can
# never make this metadata unreadable too. This is what lets the Settings UI
# show "SMB lock: busy" instead of hanging in the same way as everything else.
_state_lock = threading.Lock()
_lock_held_since: float | None = None
_lock_description: str | None = None


@contextmanager
def _locked(description: str):
    """Acquires the current `_smb_lock` while recording why, for
    `get_lock_status()`. Reads `_smb_lock` via the global each time (not a
    cached reference) so a `force_release_lock()` call made while this is
    blocked takes effect for the *next* caller immediately, without needing
    this one to ever return."""
    global _lock_held_since, _lock_description
    lock = _smb_lock
    with lock:
        with _state_lock:
            _lock_held_since = time.monotonic()
            _lock_description = description
        try:
            yield
        finally:
            with _state_lock:
                # Only clear if nobody force-released (and thus already
                # cleared/reassigned) while we were running -- otherwise a
                # slow caller finishing after a force-release would wipe out
                # a newer, unrelated holder's state.
                if _smb_lock is lock:
                    _lock_held_since = None
                    _lock_description = None


def get_lock_status() -> dict:
    """Read-only snapshot for the Settings UI -- deliberately touches only
    `_state_lock` (always fast), never `_smb_lock` itself."""
    with _state_lock:
        held_since = _lock_held_since
        description = _lock_description
    if held_since is None:
        return {"held": False, "held_since": None, "seconds_held": None, "description": None}
    seconds_held = time.monotonic() - held_since
    held_since_iso = (datetime.now(timezone.utc) - timedelta(seconds=seconds_held)).isoformat()
    return {
        "held": True,
        "held_since": held_since_iso,
        "seconds_held": seconds_held,
        "description": description,
    }


def force_release_lock() -> None:
    """Escape hatch for a wedged `_smb_lock` (Settings UI "release lock"
    button): swaps in a brand-new lock so every future SMB call proceeds
    immediately. Whatever thread is stuck holding the *old* lock keeps
    holding it forever -- Python has no safe way to force a thread off a
    blocking socket call -- but that thread is now abandoned rather than
    blocking the rest of the process."""
    global _smb_lock, _lock_held_since, _lock_description
    with _state_lock:
        _smb_lock = threading.Lock()
        _lock_held_since = None
        _lock_description = None


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


def _unc_readable(unc_path: Path) -> bool:
    """Cheap open+close via the OS's own filesystem layer -- proves the OS
    can really read this UNC path right now, separate from (and a stronger
    signal than) `windows_unc.available()`'s own `net use` check. A plain
    function rather than inlined so tests can monkeypatch it directly."""
    try:
        with open(unc_path, "rb"):
            return True
    except OSError:
        return False


def _split_share(root_path: str) -> tuple[str, str]:
    """`root_path` stores the share name plus an optional nested subpath as
    one posix-style string, e.g. `videos` or `videos/archive/2024`
    (leading/trailing slashes are ignored)."""
    cleaned = (root_path or "").strip("/\\")
    share, _, subpath = cleaned.partition("/")
    return share, subpath


class SMBBackend:
    def __init__(
        self,
        host: str,
        port: int | None,
        root_path: str,
        username: str | None,
        password: str | None,
        direct_access_enabled: bool = False,
    ):
        self.host = host
        self.port = port or 445
        self.share, self.share_subpath = _split_share(root_path)
        self.username = username
        self.password = password
        self.direct_access_enabled = direct_access_enabled
        # Must go through the same lock as `_with_retry()`: `smbclient`
        # caches one connection per host process-wide, so an unsynchronized
        # `register_session()` here can race a concurrent request's SMB
        # traffic on that shared socket (see `_smb_lock` above).
        with _locked(f"{host}: register_session"):
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
        description = f"{self.host}: {getattr(func, '__name__', 'smb_operation')}"
        with _locked(description):
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

    def _direct_available(self) -> bool:
        return self.direct_access_enabled and windows_unc.available(self.host, self.share, self.username, self.password)

    @contextmanager
    def local_copy(self, rel_path: str, *, on_copy_start: Callable[[], None] | None = None) -> Iterator[Path]:
        if self._direct_available():
            unc_path = Path(self._unc(rel_path))
            if _unc_readable(unc_path):
                yield unc_path
                return
            windows_unc.report_failure(self.host, self.username)

        if on_copy_start is not None:
            on_copy_start()

        tmp_dir = Path(tempfile.mkdtemp(prefix="va_smb_"))
        local_path = tmp_dir / PureWindowsPath(rel_path).name
        try:
            def _download() -> None:
                with smbclient.open_file(
                    self._unc(rel_path), mode="rb", share_access="rwd"
                ) as remote_f, open(local_path, "wb") as local_f:
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

    def commit_new_file(self, local_path: Path, dest_rel_path: str, *, allow_direct: bool = False) -> None:
        if allow_direct and self._direct_available():
            try:
                os.replace(local_path, self._unc(dest_rel_path))
                return
            except OSError:
                windows_unc.report_failure(self.host, self.username)

        def _upload() -> None:
            # Unlike a same-volume local move, the destination's parent
            # directory chain (e.g. `.video-archive/backups/`) may not exist
            # yet on the share -- smbclient.open_file() doesn't create it.
            parent = PureWindowsPath(dest_rel_path).parent
            if str(parent) not in ("", "."):
                smbclient.makedirs(self._unc(str(parent)), exist_ok=True)
            with open(local_path, "rb") as local_f, smbclient.open_file(
                self._unc(dest_rel_path), mode="wb", share_access="rwd"
            ) as remote_f:
                _copy_and_count(local_f, remote_f)

        self._with_retry(_upload)
        if local_path.exists():
            local_path.unlink()

    def remote_rename(self, rel_path: str, new_rel_path: str, *, allow_direct: bool = False) -> None:
        if allow_direct and self._direct_available():
            try:
                os.replace(self._unc(rel_path), self._unc(new_rel_path))
                return
            except OSError:
                windows_unc.report_failure(self.host, self.username)
        self._with_retry(smbclient.rename, self._unc(rel_path), self._unc(new_rel_path))

    def remote_remove(self, rel_path: str, *, allow_direct: bool = False) -> None:
        if allow_direct and self._direct_available():
            try:
                os.remove(self._unc(rel_path))
                return
            except OSError:
                windows_unc.report_failure(self.host, self.username)
        self._with_retry(smbclient.remove, self._unc(rel_path))

    def remote_mkdir(self, rel_path: str) -> None:
        self._with_retry(smbclient.mkdir, self._unc(rel_path))

    def ensure_dir(self, rel_path: str) -> None:
        if rel_path not in ("", "."):
            self._with_retry(smbclient.makedirs, self._unc(rel_path), exist_ok=True)

    def remote_rmdir(self, rel_path: str) -> None:
        self._with_retry(smbclient.rmdir, self._unc(rel_path))

    def read_bytes(self, rel_path: str) -> bytes:
        def _read() -> bytes:
            with smbclient.open_file(self._unc(rel_path), mode="rb", share_access="rwd") as f:
                return f.read()

        data = self._with_retry(_read)
        smb_stats.add_bytes_transferred(len(data))
        return data

    def open_range(self, rel_path: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        def _open():
            return smbclient.open_file(self._unc(rel_path), mode="rb", share_access="rwd")

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

    def direct_access_status(self) -> bool | None:
        """`None` when the fast path isn't even enabled for this source;
        otherwise the same cached `windows_unc.available()` probe
        `local_copy()` itself checks, so callers (the `/source/status`
        endpoint) see exactly what the next file read would actually use."""
        if not self.direct_access_enabled:
            return None
        return windows_unc.available(self.host, self.share, self.username, self.password)

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
