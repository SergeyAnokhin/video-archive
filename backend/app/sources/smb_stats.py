"""Process-wide counter of bytes read over SMB, fed by `smb_backend.py`.

Simple in-memory total (resets on backend restart, which is fine — it backs
a "current load" indicator in the frontend, not a historical metric). The
frontend computes a bytes/sec rate itself from two samples of the cumulative
total taken a known interval apart.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_total_bytes_read = 0


def add_bytes_read(n: int) -> None:
    global _total_bytes_read
    with _lock:
        _total_bytes_read += n


def get_total_bytes_read() -> int:
    with _lock:
        return _total_bytes_read
