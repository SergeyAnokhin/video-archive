"""Uniform file-access layer for the active source (Specification §5).

Scan, conversion, preview, and tagging job code go through `SourceAccess`
instead of touching `pathlib`/`os` directly, so the same code paths work for
the `local` protocol (plain filesystem, unchanged from earlier stages), the
`smb` protocol added in Stage 7 (`smbclient`, the high-level module bundled
with the `smbprotocol` package fixed in Tech Stack), and the `webdav`
protocol (`httpx` + `PROPFIND`/`GET`/`PUT`/`MKCOL`/`DELETE`/`MOVE`, no third-
party WebDAV library).
"""

from __future__ import annotations

from app.sources.access import SourceAccess, get_source_access
from app.sources.entries import Entry, EntryStat

__all__ = ["SourceAccess", "get_source_access", "Entry", "EntryStat"]
