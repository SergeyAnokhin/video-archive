"""Derived directory conversion/preview indicators (Specification §14).

Directory status is never persisted; it is always computed from the
`files` table for the requested subtree (Data Model "Derived Status
Queries").
"""

from __future__ import annotations

from sqlalchemy import text


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
                SUM(CASE WHEN has_preview_asset = 1 THEN 1 ELSE 0 END) AS previewed
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

    return {
        "total_supported_files": total,
        "converted_count": converted,
        "preview_count": previewed,
        "conversion_complete": converted == total,
        "preview_complete": previewed == total,
    }
