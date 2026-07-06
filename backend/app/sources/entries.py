"""Backend-agnostic directory-entry shapes shared by `local_backend.py` and
`smb_backend.py`."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EntryStat:
    size: int
    modified_at: str  # ISO 8601 UTC


@dataclass(frozen=True)
class Entry:
    name: str
    is_dir: bool
    stat: EntryStat | None  # None for directories; not needed by scan
