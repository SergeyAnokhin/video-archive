"""Tag vocabulary CRUD (Data Model §8, Settings §5, API §10).

The vocabulary is the closed, user-defined set of tags the tagging job
scores a video against (Specification §12.1) and the source of search
autocomplete suggestions (Specification §11.8). `tag_key` is a stable,
lowercased normalization of `display_name` used for de-duplication and
prefix matching; the user only ever sees/edits `display_name`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text


class DuplicateTagError(Exception):
    pass


def normalize_tag_key(display_name: str) -> str:
    return " ".join(display_name.strip().lower().split())


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_dict(row) -> dict:
    return {
        "id": row.id,
        "tag_key": row.tag_key,
        "display_name": row.display_name,
        "is_active": bool(row.is_active),
        "sort_order": row.sort_order,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_tags(
    engine, query: str | None = None, active_only: bool = False, limit: int | None = None
) -> list[dict]:
    clauses = []
    params: dict = {}
    if query:
        clauses.append("tag_key LIKE :prefix")
        params["prefix"] = f"{normalize_tag_key(query)}%"
    if active_only:
        clauses.append("is_active = 1")
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit_sql = ""
    if limit is not None:
        limit_sql = "LIMIT :limit"
        params["limit"] = limit

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"SELECT * FROM tag_catalog {where_sql} "
                f"ORDER BY sort_order, display_name COLLATE NOCASE {limit_sql}"
            ),
            params,
        ).all()
    return [_row_to_dict(row) for row in rows]


def get_tag(engine, tag_id: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM tag_catalog WHERE id = :id"), {"id": tag_id}).fetchone()
    return _row_to_dict(row) if row else None


def _get_by_key(conn, tag_key: str):
    return conn.execute(text("SELECT * FROM tag_catalog WHERE tag_key = :key"), {"key": tag_key}).fetchone()


def create_tag(engine, data: dict) -> dict:
    tag_key = normalize_tag_key(data["display_name"])
    tag_id = str(uuid.uuid4())
    now = _now()

    with engine.begin() as conn:
        if _get_by_key(conn, tag_key) is not None:
            raise DuplicateTagError(f"Tag already exists: {data['display_name']}")
        conn.execute(
            text(
                """
                INSERT INTO tag_catalog (id, tag_key, display_name, is_active, sort_order, created_at, updated_at)
                VALUES (:id, :tag_key, :display_name, :is_active, :sort_order, :now, :now)
                """
            ),
            {
                "id": tag_id,
                "tag_key": tag_key,
                "display_name": data["display_name"].strip(),
                "is_active": bool(data.get("is_active", True)),
                "sort_order": data.get("sort_order", 0),
                "now": now,
            },
        )
    return get_tag(engine, tag_id)


def update_tag(engine, tag_id: str, data: dict) -> dict | None:
    existing = get_tag(engine, tag_id)
    if existing is None:
        return None

    merged = {**existing, **data}
    new_key = normalize_tag_key(merged["display_name"])
    now = _now()

    with engine.begin() as conn:
        clash = _get_by_key(conn, new_key)
        if clash is not None and clash.id != tag_id:
            raise DuplicateTagError(f"Tag already exists: {merged['display_name']}")
        conn.execute(
            text(
                """
                UPDATE tag_catalog
                SET tag_key = :tag_key, display_name = :display_name, is_active = :is_active,
                    sort_order = :sort_order, updated_at = :now
                WHERE id = :id
                """
            ),
            {
                "tag_key": new_key,
                "display_name": merged["display_name"].strip(),
                "is_active": bool(merged["is_active"]),
                "sort_order": merged["sort_order"],
                "now": now,
                "id": tag_id,
            },
        )
    return get_tag(engine, tag_id)


def delete_tag(engine, tag_id: str) -> bool:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM file_tags WHERE tag_id = :id"), {"id": tag_id})
        result = conn.execute(text("DELETE FROM tag_catalog WHERE id = :id"), {"id": tag_id})
    return result.rowcount > 0
