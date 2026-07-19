"""Process-wide counter of bytes moved over SMB (reads and writes), fed by
`smb_backend.py`.

Simple in-memory total (resets on backend restart, which is fine — it backs
a "current load" indicator in the frontend, not a historical metric). The
frontend computes a bytes/sec rate itself from two samples of the cumulative
total taken a known interval apart.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_total_bytes_transferred = 0


def add_bytes_transferred(n: int) -> None:
    global _total_bytes_transferred
    with _lock:
        _total_bytes_transferred += n


def get_total_bytes_transferred() -> int:
    with _lock:
        return _total_bytes_transferred
