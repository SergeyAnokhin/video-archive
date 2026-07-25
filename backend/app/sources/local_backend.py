"""Local-filesystem implementation of the `SourceAccess` primitives
(Specification §5 "Local"). Every method is a thin wrapper around `pathlib`/
`os` — behavior is byte-for-byte the same as the pre-Stage-7 code that
manipulated `source_root / relative_path` directly, so existing local-source
tests keep passing unchanged.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from app.sources.entries import Entry, EntryStat


class LocalBackend:
    def __init__(self, root_path: Path):
        self.root = Path(root_path)

    def root_name(self) -> str:
        return self.root.name or str(self.root)

    def _abs(self, rel_path: str) -> Path:
        return (self.root / rel_path) if rel_path else self.root

    def scandir(self, rel_dir: str) -> list[Entry]:
        entries: list[Entry] = []
        try:
            with os.scandir(self._abs(rel_dir)) as it:
                for e in it:
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
        except OSError:
            pass
        return entries

    def exists(self, rel_path: str) -> bool:
        return self._abs(rel_path).exists()

    def is_dir(self, rel_path: str) -> bool:
        return self._abs(rel_path).is_dir()

    def stat_rel(self, rel_path: str) -> EntryStat:
        st = self._abs(rel_path).stat()
        return EntryStat(size=st.st_size, modified_at=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat())

    @contextmanager
    def local_copy(self, rel_path: str, *, on_copy_start: Callable[[], None] | None = None) -> Iterator[Path]:
        # Already a real local path: no download/cleanup needed, callback never fires.
        yield self._abs(rel_path)

    @contextmanager
    def stage_output_dir(self, rel_dir: str) -> Iterator[Path]:
        # A real directory that a same-volume `os.replace()` can move into.
        directory = self._abs(rel_dir)
        directory.mkdir(parents=True, exist_ok=True)
        yield directory

    def commit_new_file(self, local_path: Path, dest_rel_path: str, *, allow_direct: bool = False) -> None:
        # `allow_direct` only distinguishes SMB's fast path from its
        # smbclient-upload fallback -- a local source is already a direct
        # filesystem move either way, so the flag has nothing to switch on.
        dest = self._abs(dest_rel_path)
        if local_path == dest:
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(local_path, dest)

    def remote_rename(self, rel_path: str, new_rel_path: str, *, allow_direct: bool = False) -> None:
        os.replace(self._abs(rel_path), self._abs(new_rel_path))

    def remote_remove(self, rel_path: str, *, allow_direct: bool = False) -> None:
        self._abs(rel_path).unlink()

    def remote_mkdir(self, rel_path: str) -> None:
        self._abs(rel_path).mkdir()

    def ensure_dir(self, rel_path: str) -> None:
        self._abs(rel_path).mkdir(parents=True, exist_ok=True)

    def remote_rmdir(self, rel_path: str) -> None:
        self._abs(rel_path).rmdir()

    def read_bytes(self, rel_path: str) -> bytes:
        return self._abs(rel_path).read_bytes()

    def open_range(self, rel_path: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        path = self._abs(rel_path)
        size = path.stat().st_size
        real_end = size - 1 if end is None else min(end, size - 1)
        chunk_size = 1024 * 1024
        with open(path, "rb") as f:
            f.seek(start)
            remaining = real_end - start + 1
            while remaining > 0:
                chunk = f.read(min(chunk_size, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    def size_of(self, rel_path: str) -> int:
        return self._abs(rel_path).stat().st_size

    def direct_path(self, rel_path: str) -> str:
        return str(self._abs(rel_path))

    def close(self) -> None:
        pass
