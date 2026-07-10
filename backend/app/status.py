"""Derived directory conversion/preview indicators (Specification §14).

Directory status is never persisted; it is always computed from the
`files` table for the requested subtree (Data Model "Derived Status
Queries").
"""

from __future__ import annotations

from sqlalchemy import text

from app.media import compute_variant_tags

_TOP_TAG_COUNT = 3


def compute_directory_status(conn, source_id: str, relative_path: str) -> dict:
    if relative_path == "":
        clause = ""
        params: dict = {"sid": source_id}
    else:
        clause = "AND relative_path LIKE :prefix"
        params = {"sid": source_id, "prefix": f"{relative_path}/%"}

    row = conn.execute(
        text(
            f"""
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN converted_at IS NOT NULL THEN 1 ELSE 0 END) AS converted,
                SUM(CASE WHEN has_preview_asset = 1 THEN 1 ELSE 0 END) AS previewed,
                SUM(size_bytes) AS total_size
            FROM files
            WHERE source_id = :sid AND is_video_supported = 1 {clause}
              AND file_name NOT LIKE '%.original.%' AND file_name NOT LIKE '%.variant-%'
            """
        ),
        params,
    ).fetchone()

    total = row.total or 0
    converted = row.converted or 0
    previewed = row.previewed or 0

    # Card grid folder tiles show the same handful of variant tags that are
    # most common among the folder's files (Design System card compactness
    # pass), so pull every file's tags -- not just the non-variant ones
    # counted above -- and rank them by frequency.
    tag_rows = conn.execute(
        text(f"SELECT id, relative_path FROM files WHERE source_id = :sid AND is_video_supported = 1 {clause}"),
        params,
    ).all()
    file_tags = compute_variant_tags([(r.id, r.relative_path) for r in tag_rows])
    tag_counts: dict[tuple[str, object], int] = {}
    for tags in file_tags.values():
        for tag in tags:
            key = (tag["param"], tag["value"])
            tag_counts[key] = tag_counts.get(key, 0) + 1
    top_tags = sorted(tag_counts, key=lambda key: tag_counts[key], reverse=True)[:_TOP_TAG_COUNT]

    return {
        "total_supported_files": total,
        "converted_count": converted,
        "preview_count": previewed,
        "conversion_complete": converted == total,
        "preview_complete": previewed == total,
        "total_size_bytes": row.total_size or 0,
        "top_variant_tags": [{"param": param, "value": value} for param, value in top_tags],
    }
