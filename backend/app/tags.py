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


def list_used_tags(engine, query: str | None = None, limit: int | None = None) -> list[dict]:
    """Tags actually assigned to at least one file in this archive (as
    opposed to `list_tags()`'s full vocabulary, which also includes tags
    only configured for AI tagging but never applied) -- feeds the playback
    screen's quick tag-add autocomplete (user request), ordered by how often
    each tag is used so the most locally-relevant matches surface first."""
    clauses = []
    params: dict = {}
    if query:
        clauses.append("tc.tag_key LIKE :prefix")
        params["prefix"] = f"{normalize_tag_key(query)}%"
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    limit_sql = ""
    if limit is not None:
        limit_sql = "LIMIT :limit"
        params["limit"] = limit

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT tc.*, COUNT(ft.id) AS usage_count
                FROM tag_catalog tc
                JOIN file_tags ft ON ft.tag_id = tc.id
                {where_sql}
                GROUP BY tc.id
                ORDER BY usage_count DESC, tc.display_name COLLATE NOCASE
                {limit_sql}
                """
            ),
            params,
        ).all()
    return [_row_to_dict(row) for row in rows]


def get_tag(engine, tag_id: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM tag_catalog WHERE id = :id"), {"id": tag_id}).fetchone()
    return _row_to_dict(row) if row else None


def list_tags_by_ids(engine, tag_ids: list[str]) -> list[dict | None]:
    """Fetches tags by id, preserving `tag_ids`' given order and length
    (a `None` entry for an id that no longer exists) -- used to reconstruct
    a batch tagging submission's exact vocabulary snapshot so its scores
    (positionally correlated with the tag order sent to the provider) still
    line up correctly even if the live vocabulary changed while the batch
    was in flight (post-V1, user request -- batch tagging survives a
    service restart, see `app/batch_submissions.py`/`app/jobs/tag.py`)."""
    if not tag_ids:
        return []
    placeholders = ", ".join(f":id_{i}" for i in range(len(tag_ids)))
    params = {f"id_{i}": tag_id for i, tag_id in enumerate(tag_ids)}
    with engine.connect() as conn:
        rows = conn.execute(text(f"SELECT * FROM tag_catalog WHERE id IN ({placeholders})"), params).all()
    by_id = {row.id: _row_to_dict(row) for row in rows}
    return [by_id.get(tag_id) for tag_id in tag_ids]


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


def get_or_create_tag(engine, display_name: str) -> dict:
    """Resolve `display_name` to an existing vocabulary entry (case/
    whitespace-insensitive match on `tag_key`), or create a new one -- used
    when a user types a tag by hand in `FileInfoPanel` instead of picking
    one from the existing vocabulary list, so either path ends up assigning
    a real `tag_catalog` row."""
    tag_key = normalize_tag_key(display_name)
    with engine.connect() as conn:
        existing = _get_by_key(conn, tag_key)
    if existing is not None:
        return _row_to_dict(existing)
    try:
        return create_tag(engine, {"display_name": display_name})
    except DuplicateTagError:
        # Lost a race with a concurrent creator of the same key (e.g. two
        # tuning-sweep variant threads tagging the shared codec at once) --
        # the tag exists now, so resolving it is the correct outcome.
        with engine.connect() as conn:
            row = _get_by_key(conn, tag_key)
        return _row_to_dict(row)


def assign_file_tag(engine, file_id: str, tag_id: str) -> None:
    """Manually assign `tag_id` to `file_id` (user request -- editable tags
    in `FileInfoPanel`), replacing any existing assignment of the same tag
    on that file rather than duplicating it (`file_tags` has no unique
    constraint on `(file_id, tag_id)`). A human explicitly picking/typing a
    tag is treated as full confidence (`score=100`), unlike a provider's
    scored guess -- `provider_name="manual"` distinguishes it from an AI
    assignment in the UI."""
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM file_tags WHERE file_id = :file_id AND tag_id = :tag_id"),
            {"file_id": file_id, "tag_id": tag_id},
        )
        conn.execute(
            text(
                """
                INSERT INTO file_tags (id, file_id, tag_id, score, provider_name, model_name, assigned_at)
                VALUES (:id, :file_id, :tag_id, 100, 'manual', NULL, :now)
                """
            ),
            {"id": str(uuid.uuid4()), "file_id": file_id, "tag_id": tag_id, "now": now},
        )
        conn.execute(
            text("UPDATE files SET tagged_at = :now, updated_at = :now WHERE id = :id"),
            {"now": now, "id": file_id},
        )


def assign_tuning_parameter_tags(engine, file_id: str, display_names: list[str]) -> None:
    """Tag a tuning-sweep variant file with its encode parameters (user
    request) -- one vocabulary tag per parameter (codec, dimension cap, CRF),
    so a variant's settings are visible and removable like any other tag.
    Unlike `assign_file_tag` this does not touch `files.tagged_at`: parameter
    tags record how the file was produced, not an AI-tagging result."""
    now = _now()
    tag_ids = [get_or_create_tag(engine, name)["id"] for name in display_names]
    with engine.begin() as conn:
        for tag_id in tag_ids:
            conn.execute(
                text("DELETE FROM file_tags WHERE file_id = :file_id AND tag_id = :tag_id"),
                {"file_id": file_id, "tag_id": tag_id},
            )
            conn.execute(
                text(
                    """
                    INSERT INTO file_tags (id, file_id, tag_id, score, provider_name, model_name, assigned_at)
                    VALUES (:id, :file_id, :tag_id, 100, 'tuning', NULL, :now)
                    """
                ),
                {"id": str(uuid.uuid4()), "file_id": file_id, "tag_id": tag_id, "now": now},
            )


def replace_scored_tags(engine, file_id: str, scored_tags: list[dict]) -> None:
    """Full replace of `file_id`'s `file_tags` rows (Data Model §9
    "re-tagging replaces the previous set") -- used by the `tag` job
    (`app/jobs/tag.py`) and by Tag Lab's apply step
    (`app/tag_lab.py::apply_tag_lab_result`). Each item is `{id, score,
    provider_name, model_name}`; unlike the old job-only helper this
    generalizes to a per-item provider/model instead of one pair for the
    whole batch, since a Tag Lab apply can mix model-scored tags and
    manually-added ones in a single write. Any `id` that no longer exists in
    `tag_catalog` (vocabulary changed between scoring and applying) is
    silently dropped rather than inserting an orphaned row -- SQLite foreign
    keys aren't enforced in this database."""
    now = _now()
    valid_ids = {
        tag["id"] for tag in list_tags_by_ids(engine, [entry["id"] for entry in scored_tags]) if tag is not None
    }
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM file_tags WHERE file_id = :file_id"), {"file_id": file_id})
        for entry in scored_tags:
            if entry["id"] not in valid_ids:
                continue
            conn.execute(
                text(
                    """
                    INSERT INTO file_tags (id, file_id, tag_id, score, provider_name, model_name, assigned_at)
                    VALUES (:id, :file_id, :tag_id, :score, :provider_name, :model_name, :now)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "file_id": file_id,
                    "tag_id": entry["id"],
                    "score": entry["score"],
                    "provider_name": entry["provider_name"],
                    "model_name": entry["model_name"],
                    "now": now,
                },
            )
        conn.execute(
            text("UPDATE files SET tagged_at = :now, updated_at = :now WHERE id = :id"),
            {"now": now, "id": file_id},
        )


def remove_file_tag(engine, file_id: str, tag_id: str) -> bool:
    """Un-assign `tag_id` from `file_id` (user request -- editable tags in
    `FileInfoPanel`). Returns whether an assignment actually existed."""
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM file_tags WHERE file_id = :file_id AND tag_id = :tag_id"),
            {"file_id": file_id, "tag_id": tag_id},
        )
    return result.rowcount > 0


def delete_tag(engine, tag_id: str) -> bool:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM file_tags WHERE tag_id = :id"), {"id": tag_id})
        result = conn.execute(text("DELETE FROM tag_catalog WHERE id = :id"), {"id": tag_id})
    return result.rowcount > 0


def list_top_tags_for_files(engine, file_ids: list[str], limit_per_file: int = 4) -> dict[str, list[dict]]:
    """Batch-fetch each file's top-scored assigned tags (Data Model §8), for
    card badges in the library grid — mirrors `compute_variant_tags()`'s
    `{file_id: [...]}` shape so the router can attach it the same way."""
    if not file_ids:
        return {}
    placeholders = ", ".join(f":id_{i}" for i in range(len(file_ids)))
    params = {f"id_{i}": file_id for i, file_id in enumerate(file_ids)}

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                f"""
                SELECT ft.file_id, tc.id AS tag_id, tc.display_name, ft.score,
                       ft.provider_name, ft.model_name
                FROM file_tags ft
                JOIN tag_catalog tc ON tc.id = ft.tag_id
                WHERE ft.file_id IN ({placeholders}) AND ft.score > 0
                ORDER BY ft.file_id, ft.score DESC
                """
            ),
            params,
        ).all()

    result: dict[str, list[dict]] = {}
    for row in rows:
        bucket = result.setdefault(row.file_id, [])
        if len(bucket) < limit_per_file:
            bucket.append(
                {
                    "tag_id": row.tag_id,
                    "display_name": row.display_name,
                    "score": row.score,
                    "provider_name": row.provider_name,
                    "model_name": row.model_name,
                }
            )
    return result
