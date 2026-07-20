"""Windows-only capability probe for reading an SMB source's files straight
off their `\\\\host\\share\\...` UNC path instead of `SMBBackend.local_copy()`'s
default full-file download to a temp dir.

This only works when the OS itself (not this app's own in-process
`smbprotocol`/`smbclient` session, see `smb_backend.py`) already has -- or can
establish -- an authenticated SMB session to the host, the same thing
Windows Explorer relies on. `net use` is how that OS-level session is
established/confirmed; a real operation succeeding is the only trustworthy
signal (same "probe, don't assume" reasoning as `hardware_accel.py`), so this
never trusts a stale positive result forever -- a dropped OS session is
re-detected within `_RECHECK_OK_SECONDS`, and `report_failure()` lets a
caller that just saw a live UNC read/write fail force an immediate re-probe
instead of waiting out the TTL.

Windows only allows one set of credentials per remote host for SMB at the OS
level -- `net use` to a host that already has a session under different
credentials fails with error 1219 ("multiple connections... using more than
one user name are not allowed"). Any such failure is just "unavailable right
now", never raised to the caller: every consumer of `available()` must fall
back to the existing download-based path.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass

_RECHECK_OK_SECONDS = 60
_RECHECK_FAIL_SECONDS = 30
_NET_USE_TIMEOUT = 10


@dataclass
class _CacheEntry:
    available: bool
    checked_at: float


_lock = threading.Lock()
_cache: dict[tuple[str, str], _CacheEntry] = {}


def is_supported() -> bool:
    """Whether this OS has a UNC/SMB redirector at all -- the underlying
    mechanism (`net use`, `\\\\host\\share` paths) is Windows-only."""
    return os.name == "nt"


def _net_use(host: str, share: str, username: str | None, password: str | None) -> bool:
    unc_share = f"\\\\{host}\\{share}"
    args = ["net", "use", unc_share]
    if password:
        args.append(password)
    if username:
        args += ["/user:" + username]
    args.append("/persistent:no")
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            timeout=_NET_USE_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def available(host: str, share: str, username: str | None, password: str | None, *, force: bool = False) -> bool:
    """Best-effort check that ffprobe/ffmpeg could read `\\\\host\\share\\...`
    directly right now. Never raises -- any failure just means "not
    available", so the caller should fall back to the existing behavior."""
    if not is_supported():
        return False

    key = (host, username or "")
    now = time.monotonic()
    with _lock:
        entry = _cache.get(key)
        if entry is not None and not force:
            ttl = _RECHECK_OK_SECONDS if entry.available else _RECHECK_FAIL_SECONDS
            if now - entry.checked_at < ttl:
                return entry.available

    result = _net_use(host, share, username, password)
    with _lock:
        _cache[key] = _CacheEntry(available=result, checked_at=now)
    return result


def report_failure(host: str, username: str | None) -> None:
    """A caller that just saw a live UNC read/write fail despite `available()`
    having said yes -- invalidate the cache entry so the next call re-probes
    immediately instead of trusting a stale positive for up to
    `_RECHECK_OK_SECONDS`."""
    key = (host, username or "")
    with _lock:
        _cache.pop(key, None)


def reset_cache() -> None:
    """Test-only: clears the module-level cache."""
    with _lock:
        _cache.clear()
