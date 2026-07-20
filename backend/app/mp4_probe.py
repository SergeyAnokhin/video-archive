"""Fast-path media-info probe for MP4/MOV/M4V files: reads just enough of
the container's box structure (via `SourceAccess.open_range()` -- seek+range
reads, already implemented identically for both `LocalBackend` and
`SMBBackend`, no full-file download involved) to extract the same fields
`conversion.probe_media()` gets from a full ffprobe run, without spawning a
subprocess or reading the (usually much larger) `mdat` media payload at all.

Used as a first attempt by `GET /files/{id}/media-info`
(`app/routers/files.py`) before falling back to the existing
`local_copy()` + ffprobe path. `probe_media()` returns `None` on ANY doubt
(unrecognized/fragmented container, malformed boxes, missing video track) --
never a wrong answer, never a raised exception -- so the fallback is always
safe to take.

ISO-BMFF box basics this relies on: every box starts with a 4-byte
big-endian size (0 means "extends to EOF", 1 means a 8-byte "largesize"
follows) and a 4-byte type. `moov` (usually near the very end of the file
for camera recordings that were never given `-movflags +faststart`) holds
all the metadata we need: `mvhd` for overall duration/timescale, and the
first video `trak`'s `stsd` sample entry for width/height/codec fourCC. An
`mvex` box inside `moov` means a fragmented ("empty moov") mp4, where
`mvhd`/`stbl` data isn't reliable -- bail out in that case.
"""

from __future__ import annotations

from typing import Iterator

_MOOV_SIZE_CAP = 32 * 1024 * 1024
_MAX_TOP_LEVEL_BOXES = 10_000

_CODEC_NAMES: dict[bytes, str] = {
    b"avc1": "h264",
    b"avc3": "h264",
    b"hev1": "hevc",
    b"hvc1": "hevc",
    b"hvc2": "hevc",
    b"mp4v": "mpeg4",
    b"vp09": "vp9",
    b"av01": "av1",
}


def probe_media(access, rel_path: str, size_bytes: int) -> dict | None:
    """Same return shape as `conversion.probe_media()`. Returns `None` for
    anything this fast path doesn't confidently handle -- the caller must
    fall back to the full ffprobe-based path in that case."""
    try:
        return _probe(access, rel_path, size_bytes)
    except Exception:  # noqa: BLE001 - best-effort fast path, never blocks the fallback
        return None


def _read_exact(access, rel_path: str, offset: int, length: int) -> bytes:
    if length <= 0:
        return b""
    chunks = list(access.open_range(rel_path, offset, offset + length - 1))
    data = b"".join(chunks)
    if len(data) < length:
        raise ValueError("short read")
    return data[:length]


def _iter_boxes(buf: bytes) -> Iterator[tuple[bytes, bytes]]:
    """Walk sibling boxes within an already-loaded buffer, yielding
    `(box_type, box_content)` -- `box_content` excludes the box's own
    size/type (and largesize, if present) header."""
    offset = 0
    n = len(buf)
    while offset + 8 <= n:
        box_size = int.from_bytes(buf[offset : offset + 4], "big")
        box_type = buf[offset + 4 : offset + 8]
        header_len = 8
        if box_size == 1:
            if offset + 16 > n:
                return
            box_size = int.from_bytes(buf[offset + 8 : offset + 16], "big")
            header_len = 16
        elif box_size == 0:
            box_size = n - offset
        if box_size < header_len or offset + box_size > n:
            return
        yield box_type, buf[offset + header_len : offset + box_size]
        offset += box_size


def _find_top_level_moov(access, rel_path: str, size_bytes: int) -> tuple[int, int] | None:
    """Walk top-level boxes without reading their content (just the 8/16-byte
    header at each offset, skipping the rest -- in particular the usually
    huge `mdat` -- via arithmetic), returning `(offset, size)` of `moov`."""
    offset = 0
    for _ in range(_MAX_TOP_LEVEL_BOXES):
        if offset + 8 > size_bytes:
            return None
        header = _read_exact(access, rel_path, offset, 8)
        box_size = int.from_bytes(header[0:4], "big")
        box_type = header[4:8]
        header_len = 8
        if box_size == 1:
            ext = _read_exact(access, rel_path, offset + 8, 8)
            box_size = int.from_bytes(ext, "big")
            header_len = 16
        elif box_size == 0:
            box_size = size_bytes - offset
        if box_size < header_len:
            return None
        if box_type == b"moov":
            return offset, box_size
        offset += box_size
    return None


def _parse_mvhd(content: bytes) -> tuple[int, int] | None:
    """Returns `(timescale, duration)` in `mvhd`'s own units."""
    if len(content) < 4:
        return None
    version = content[0]
    if version == 1:
        if len(content) < 32:
            return None
        timescale = int.from_bytes(content[20:24], "big")
        duration = int.from_bytes(content[24:32], "big")
    else:
        if len(content) < 20:
            return None
        timescale = int.from_bytes(content[12:16], "big")
        duration = int.from_bytes(content[16:20], "big")
    if timescale <= 0:
        return None
    return timescale, duration


def _parse_stsd(content: bytes) -> tuple[int, int, str] | None:
    if len(content) < 8:
        return None
    entry_count = int.from_bytes(content[4:8], "big")
    if entry_count < 1:
        return None
    entry = content[8:]
    if len(entry) < 36:
        return None
    fourcc = entry[4:8]
    codec_name = _CODEC_NAMES.get(fourcc)
    if codec_name is None:
        return None
    width = int.from_bytes(entry[32:34], "big")
    height = int.from_bytes(entry[34:36], "big")
    if not width or not height:
        return None
    return width, height, codec_name


def _find_video_sample_entry(trak_content: bytes) -> tuple[int, int, str] | None:
    mdia_content = None
    for box_type, content in _iter_boxes(trak_content):
        if box_type == b"mdia":
            mdia_content = content
            break
    if mdia_content is None:
        return None

    handler_type = None
    minf_content = None
    for box_type, content in _iter_boxes(mdia_content):
        if box_type == b"hdlr" and len(content) >= 12:
            handler_type = content[8:12]
        elif box_type == b"minf":
            minf_content = content
    if handler_type != b"vide" or minf_content is None:
        return None

    stbl_content = None
    for box_type, content in _iter_boxes(minf_content):
        if box_type == b"stbl":
            stbl_content = content
            break
    if stbl_content is None:
        return None

    for box_type, content in _iter_boxes(stbl_content):
        if box_type == b"stsd":
            return _parse_stsd(content)
    return None


def _parse_moov(moov_content: bytes, size_bytes: int) -> dict | None:
    mvhd: tuple[int, int] | None = None
    video_entry: tuple[int, int, str] | None = None

    for box_type, content in _iter_boxes(moov_content):
        if box_type == b"mvex":
            # Fragmented/"empty moov" mp4 -- mvhd/stbl data here isn't
            # reliable, bail to the ffprobe-based fallback.
            return None
        if box_type == b"mvhd" and mvhd is None:
            mvhd = _parse_mvhd(content)
        elif box_type == b"trak" and video_entry is None:
            video_entry = _find_video_sample_entry(content)

    if video_entry is None:
        return None
    width, height, codec_name = video_entry

    duration = None
    if mvhd is not None:
        timescale, ticks = mvhd
        duration = ticks / timescale

    bit_rate = None
    if duration and duration > 0:
        bit_rate = int(size_bytes * 8 / duration)

    return {
        "has_video_stream": True,
        "width": width,
        "height": height,
        "video_codec_name": codec_name,
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "duration": duration,
        "bit_rate": bit_rate,
    }


def _probe(access, rel_path: str, size_bytes: int) -> dict | None:
    if size_bytes < 8:
        return None
    found = _find_top_level_moov(access, rel_path, size_bytes)
    if found is None:
        return None
    moov_offset, moov_size = found
    if moov_size > _MOOV_SIZE_CAP:
        return None
    moov_box = _read_exact(access, rel_path, moov_offset, moov_size)
    # `moov_box` still has its own 8/16-byte box header; strip it the same
    # way `_iter_boxes` would for a sibling box.
    header_len = 16 if int.from_bytes(moov_box[0:4], "big") == 1 else 8
    return _parse_moov(moov_box[header_len:], size_bytes)
