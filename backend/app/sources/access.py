"""`SourceAccess`: the protocol-agnostic facade used by scan/convert/preview/
tag job code and the browsing/playback routers (Specification §5). It
dispatches every call to a `LocalBackend` or `SMBBackend` instance, so callers
only ever deal with relative-path strings — never a raw `pathlib.Path` that
may or may not point at a real local file.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from app import secrets_store
from app.sources.entries import Entry, EntryStat
from app.sources.local_backend import LocalBackend


class SourceAccess:
    def __init__(self, backend, protocol: str):
        self._backend = backend
        self.protocol = protocol

    # -- browsing / scan --

    def root_name(self) -> str:
        return self._backend.root_name()

    def scandir(self, rel_dir: str) -> list[Entry]:
        return self._backend.scandir(rel_dir)

    def walk(self, subtree_rel: str = "") -> Iterator[tuple[str, str | None, list[Entry]]]:
        """Recursive walk of `subtree_rel` (default: the whole source),
        yielding `(dir_rel, parent_rel, entries)` for that directory and
        every descendant, built generically on `scandir()` so both backends
        share this logic (mirrors `os.walk`'s shape closely enough to drop
        into the existing scan/rescan code)."""
        subtree_rel = subtree_rel.strip("/")
        parent_rel = None if not subtree_rel else (subtree_rel.rsplit("/", 1)[0] if "/" in subtree_rel else "")
        stack: list[tuple[str, str | None]] = [(subtree_rel, parent_rel)]

        while stack:
            dir_rel, parent = stack.pop()
            entries = self.scandir(dir_rel)
            yield dir_rel, parent, entries
            for entry in entries:
                if entry.is_dir and entry.name != ".video-archive":
                    child_rel = f"{dir_rel}/{entry.name}" if dir_rel else entry.name
                    stack.append((child_rel, dir_rel))

    def exists(self, rel_path: str) -> bool:
        return self._backend.exists(rel_path)

    def is_dir(self, rel_path: str) -> bool:
        return self._backend.is_dir(rel_path)

    def stat_rel(self, rel_path: str) -> EntryStat:
        return self._backend.stat_rel(rel_path)

    # -- processing (convert/preview/tag) --

    @contextmanager
    def local_copy(self, rel_path: str, *, on_copy_start: Callable[[], None] | None = None) -> Iterator[Path]:
        with self._backend.local_copy(rel_path, on_copy_start=on_copy_start) as path:
            yield path

    @contextmanager
    def stage_output_dir(self, rel_dir: str) -> Iterator[Path]:
        with self._backend.stage_output_dir(rel_dir) as path:
            yield path

    def commit_new_file(self, local_path: Path, dest_rel_path: str, *, allow_direct: bool = False) -> None:
        self._backend.commit_new_file(local_path, dest_rel_path, allow_direct=allow_direct)

    def remote_rename(self, rel_path: str, new_rel_path: str, *, allow_direct: bool = False) -> None:
        self._backend.remote_rename(rel_path, new_rel_path, allow_direct=allow_direct)

    def remote_remove(self, rel_path: str, *, allow_direct: bool = False) -> None:
        self._backend.remote_remove(rel_path, allow_direct=allow_direct)

    def remote_mkdir(self, rel_path: str) -> None:
        self._backend.remote_mkdir(rel_path)

    def remote_rmdir(self, rel_path: str) -> None:
        self._backend.remote_rmdir(rel_path)

    # -- playback --

    def read_bytes(self, rel_path: str) -> bytes:
        return self._backend.read_bytes(rel_path)

    def open_range(self, rel_path: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        return self._backend.open_range(rel_path, start, end)

    def size_of(self, rel_path: str) -> int:
        return self._backend.size_of(rel_path)

    def direct_path(self, rel_path: str) -> str:
        return self._backend.direct_path(rel_path)

    def direct_access_status(self) -> bool | None:
        return self._backend.direct_access_status()

    def close(self) -> None:
        self._backend.close()


def get_source_access(source_row) -> SourceAccess:
    """Build the right `SourceAccess` for a `sources` table row."""
    if source_row.protocol == "smb":
        from app.sources.smb_backend import SMBBackend

        username, password = secrets_store.get_source_credentials_for(
            source_row.username_ref, source_row.secret_ref
        )
        # `getattr` rather than a direct attribute access: not every caller's
        # SELECT is guaranteed to include this column (most use `s.*`, but a
        # narrower query shouldn't hard-fail just because this opt-in fast
        # path can't be evaluated -- it just stays off, same as the default).
        direct_access_enabled = bool(getattr(source_row, "direct_access_enabled", False))
        backend = SMBBackend(
            source_row.host, source_row.port, source_row.root_path, username, password, direct_access_enabled
        )
        return SourceAccess(backend, "smb")

    return SourceAccess(LocalBackend(Path(source_row.root_path)), "local")
