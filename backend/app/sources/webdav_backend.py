"""WebDAV implementation of the `SourceAccess` primitives (a source hosted by
a WebDAV server, e.g. Synology DSM's WebDAV Server package — see
`docs/webdav-setup.md`), built on `httpx` (already a dependency, used
elsewhere for provider calls) plus stdlib `xml.etree.ElementTree` for
`PROPFIND` multistatus parsing. No third-party WebDAV client library is used.

Unlike `smb_backend.py`, there is no process-wide connection lock here:
`httpx.Client` pools independent HTTP connections per request, so concurrent
WebDAV calls don't share a single stateful session the way `smbclient` does —
one slow/stuck request only blocks its own caller, not every other source
operation in the process.

`host` may include a scheme (`https://nas.local`); if omitted, `https://` is
assumed, matching Synology DSM's WebDAV Server default. `port` is a separate
field (same UX as `smb`) — DSM's own defaults are 5005 (HTTP) / 5006 (HTTPS),
not the scheme's standard port, so it must be set explicitly rather than
inferred. `root_path` is a URL path appended after the host, same convention
as SMB's `share[/subpath]`.

ffmpeg/ffprobe need a real local file, not an HTTP response, so `local_copy()`
downloads to a throwaway temp directory and `commit_new_file()` uploads a
locally produced file back, exactly like the SMB backend's copy-based
approach — conversion/preview/tagging code is otherwise unaware it's talking
to WebDAV. There is no direct-path fast path (no OS-level WebDAV redirector
comparable to SMB's UNC paths), so `direct_access_status()` always reports
`None` and `local_copy()`/`commit_new_file()`/`remote_rename()`/
`remote_remove()` ignore `allow_direct` — it's accepted only for call-site
parity with the other two backends.
"""

from __future__ import annotations

import shutil
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, unquote, urlsplit, urlunsplit

import httpx

from app.sources.entries import Entry, EntryStat

_CHUNK_SIZE = 512 * 1024
_RETRYABLE = (httpx.TransportError, httpx.TimeoutException)

_PROPFIND_BODY = b"""<?xml version="1.0" encoding="utf-8" ?>
<D:propfind xmlns:D="DAV:">
  <D:prop>
    <D:resourcetype/>
    <D:getcontentlength/>
    <D:getlastmodified/>
  </D:prop>
</D:propfind>
"""


def _build_base_url(host: str, port: int | None) -> str:
    """`host` may or may not carry a scheme/port of its own; an explicit
    `port` (when given) always wins over one embedded in `host`."""
    raw = (host or "").strip()
    if "://" not in raw:
        raw = f"https://{raw}"
    parsed = urlsplit(raw)
    scheme = parsed.scheme or "https"
    hostname = parsed.hostname or ""
    effective_port = port or parsed.port
    netloc = f"{hostname}:{effective_port}" if effective_port else hostname
    return urlunsplit((scheme, netloc, "", "", ""))


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(el: ET.Element, name: str) -> ET.Element | None:
    for child in el:
        if _localname(child.tag) == name:
            return child
    return None


def _children(el: ET.Element, name: str) -> Iterator[ET.Element]:
    for child in el:
        if _localname(child.tag) == name:
            yield child


def _parse_multistatus(xml_text: str) -> list[tuple[str, bool, EntryStat | None]]:
    """Parses a `PROPFIND` multistatus response into `(href, is_dir, stat)`
    tuples, ignoring whatever namespace prefix (`D:`, `d:`, ...) the server
    used — only the local element name matters."""
    root = ET.fromstring(xml_text)
    results: list[tuple[str, bool, EntryStat | None]] = []
    for response_el in _children(root, "response"):
        href_el = _child(response_el, "href")
        if href_el is None or not href_el.text:
            continue
        is_dir = False
        size = 0
        modified_at: datetime | None = None
        for propstat_el in _children(response_el, "propstat"):
            status_el = _child(propstat_el, "status")
            if status_el is not None and status_el.text and " 200 " not in f" {status_el.text} ":
                continue
            prop_el = _child(propstat_el, "prop")
            if prop_el is None:
                continue
            resourcetype_el = _child(prop_el, "resourcetype")
            if resourcetype_el is not None and _child(resourcetype_el, "collection") is not None:
                is_dir = True
            length_el = _child(prop_el, "getcontentlength")
            if length_el is not None and length_el.text:
                size = int(length_el.text)
            modified_el = _child(prop_el, "getlastmodified")
            if modified_el is not None and modified_el.text:
                try:
                    modified_at = parsedate_to_datetime(modified_el.text)
                except (TypeError, ValueError):
                    modified_at = None
        stat = None
        if not is_dir:
            resolved = (modified_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
            stat = EntryStat(size=size, modified_at=resolved.isoformat())
        results.append((href_el.text, is_dir, stat))
    return results


class WebDAVBackend:
    def __init__(
        self,
        host: str,
        port: int | None,
        root_path: str,
        username: str | None,
        password: str | None,
        verify_ssl: bool = True,
        *,
        transport: httpx.BaseTransport | None = None,
    ):
        self._base_url = _build_base_url(host, port)
        self.root_path = (root_path or "").strip("/")
        self._client = httpx.Client(
            auth=(username, password) if username else None,
            verify=verify_ssl,
            timeout=30.0,
            transport=transport,
        )

    def _url(self, rel_path: str) -> str:
        combined = "/".join(p.strip("/") for p in (self.root_path, rel_path) if p and p.strip("/"))
        quoted = quote(combined, safe="/")
        return f"{self._base_url}/{quoted}" if quoted else f"{self._base_url}/"

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._client.request(method, url, **kwargs)
        except _RETRYABLE:
            return self._client.request(method, url, **kwargs)

    def root_name(self) -> str:
        if self.root_path:
            return self.root_path.rsplit("/", 1)[-1]
        return urlsplit(self._base_url).hostname or self._base_url

    def _propfind(self, rel_path: str, depth: str) -> httpx.Response:
        url = self._url(rel_path)
        if depth == "1" and not url.endswith("/"):
            url += "/"
        return self._request(
            "PROPFIND", url, headers={"Depth": depth, "Content-Type": "application/xml"}, content=_PROPFIND_BODY
        )

    def _propfind_self(self, rel_path: str) -> tuple[str, bool, EntryStat | None] | None:
        resp = self._propfind(rel_path, "0")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        results = _parse_multistatus(resp.text)
        return results[0] if results else None

    def scandir(self, rel_dir: str) -> list[Entry]:
        try:
            resp = self._propfind(rel_dir, "1")
        except httpx.HTTPError:
            return []
        if resp.status_code == 404:
            return []
        try:
            resp.raise_for_status()
        except httpx.HTTPError:
            return []

        request_path = urlsplit(str(resp.request.url)).path
        self_path = request_path.rstrip("/") + "/"
        entries: list[Entry] = []
        for href, is_dir, stat in _parse_multistatus(resp.text):
            href_path = urlsplit(href).path
            if href_path.rstrip("/") + "/" == self_path:
                continue  # the multistatus entry describing the directory itself
            name = unquote(href_path.rstrip("/").rsplit("/", 1)[-1])
            if not name:
                continue
            entries.append(Entry(name=name, is_dir=is_dir, stat=stat))
        return entries

    def exists(self, rel_path: str) -> bool:
        try:
            return self._propfind_self(rel_path) is not None
        except httpx.HTTPError:
            return False

    def is_dir(self, rel_path: str) -> bool:
        try:
            result = self._propfind_self(rel_path)
        except httpx.HTTPError:
            return False
        return bool(result and result[1])

    def stat_rel(self, rel_path: str) -> EntryStat:
        result = self._propfind_self(rel_path)
        if result is None:
            raise FileNotFoundError(rel_path)
        _, is_dir, stat = result
        if is_dir or stat is None:
            raise IsADirectoryError(rel_path)
        return stat

    @contextmanager
    def local_copy(self, rel_path: str, *, on_copy_start: Callable[[], None] | None = None) -> Iterator[Path]:
        if on_copy_start is not None:
            on_copy_start()
        tmp_dir = Path(tempfile.mkdtemp(prefix="va_webdav_"))
        local_path = tmp_dir / PurePosixPath(rel_path).name
        try:
            with self._client.stream("GET", self._url(rel_path)) as resp:
                resp.raise_for_status()
                with open(local_path, "wb") as f:
                    for chunk in resp.iter_bytes(_CHUNK_SIZE):
                        f.write(chunk)
            yield local_path
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    @contextmanager
    def stage_output_dir(self, rel_dir: str) -> Iterator[Path]:
        tmp_dir = Path(tempfile.mkdtemp(prefix="va_webdav_out_"))
        try:
            yield tmp_dir
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _ensure_collection(self, rel_dir: str) -> None:
        """`MKCOL` only creates one level at a time (unlike `smbclient.makedirs`),
        so missing parents are created top-down, one segment at a time."""
        accum = ""
        for part in (p for p in rel_dir.strip("/").split("/") if p):
            accum = f"{accum}/{part}" if accum else part
            url = self._url(accum)
            if not url.endswith("/"):
                url += "/"
            resp = self._request("MKCOL", url)
            if resp.status_code in (201, 405):  # 405 = already exists as a collection
                continue
            resp.raise_for_status()

    def commit_new_file(self, local_path: Path, dest_rel_path: str, *, allow_direct: bool = False) -> None:
        parent = str(PurePosixPath(dest_rel_path).parent)
        if parent not in ("", "."):
            self._ensure_collection(parent)

        def _chunks() -> Iterator[bytes]:
            with open(local_path, "rb") as f:
                while True:
                    chunk = f.read(_CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk

        resp = self._request("PUT", self._url(dest_rel_path), content=_chunks())
        resp.raise_for_status()
        if local_path.exists():
            local_path.unlink()

    def remote_rename(self, rel_path: str, new_rel_path: str, *, allow_direct: bool = False) -> None:
        resp = self._request(
            "MOVE", self._url(rel_path), headers={"Destination": self._url(new_rel_path), "Overwrite": "F"}
        )
        resp.raise_for_status()

    def remote_remove(self, rel_path: str, *, allow_direct: bool = False) -> None:
        resp = self._request("DELETE", self._url(rel_path))
        resp.raise_for_status()

    def remote_mkdir(self, rel_path: str) -> None:
        url = self._url(rel_path)
        if not url.endswith("/"):
            url += "/"
        resp = self._request("MKCOL", url)
        resp.raise_for_status()

    def ensure_dir(self, rel_path: str) -> None:
        if rel_path not in ("", "."):
            self._ensure_collection(rel_path)

    def remote_rmdir(self, rel_path: str) -> None:
        # A plain `DELETE` on a WebDAV collection is typically recursive,
        # unlike `os.rmdir`/`smbclient.rmdir`'s strict "must be empty"
        # semantics -- checked explicitly here so behavior matches the other
        # two backends instead of silently deleting a non-empty directory.
        if self.scandir(rel_path):
            raise OSError(f"Directory not empty: {rel_path}")
        url = self._url(rel_path)
        if not url.endswith("/"):
            url += "/"
        resp = self._request("DELETE", url)
        resp.raise_for_status()

    def read_bytes(self, rel_path: str) -> bytes:
        resp = self._request("GET", self._url(rel_path))
        resp.raise_for_status()
        return resp.content

    def open_range(self, rel_path: str, start: int = 0, end: int | None = None) -> Iterator[bytes]:
        headers = {"Range": f"bytes={start}-{end if end is not None else ''}"}
        with self._client.stream("GET", self._url(rel_path), headers=headers) as resp:
            resp.raise_for_status()
            yield from resp.iter_bytes(_CHUNK_SIZE)

    def size_of(self, rel_path: str) -> int:
        return self.stat_rel(rel_path).size

    def direct_path(self, rel_path: str) -> str:
        # No filesystem-addressable fast path exists for WebDAV (no OS-level
        # UNC-style redirector) -- this is only for call-site parity with
        # `LocalBackend`/`SMBBackend`; returns the resolved WebDAV URL.
        return self._url(rel_path)

    def direct_access_status(self) -> bool | None:
        return None

    def close(self) -> None:
        self._client.close()


def test_connection(
    host: str, port: int | None, root_path: str, username: str | None, password: str | None, verify_ssl: bool = True
) -> tuple[bool, str | None]:
    """Attempt a `PROPFIND` against the root without persisting anything;
    used by `POST /api/source/test-connection`."""
    backend = WebDAVBackend(host, port, root_path, username, password, verify_ssl)
    try:
        if not backend.is_dir(""):
            return False, f"Path is not a directory: {backend.direct_path('')}"
        backend.scandir("")
        return True, None
    except Exception as exc:  # noqa: BLE001 - surfaced to the user as a plain message
        return False, str(exc)
    finally:
        backend.close()
