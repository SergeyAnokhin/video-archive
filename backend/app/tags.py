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


# Mirrors `frontend/src/utils/tagColor.ts`'s `hashTagColor()` exactly (same
# palette, same hash fold) so a tag with no explicit `color` gets the same
# deterministic color server- and client-side -- the fallback used before
# `tag_catalog.color` existed, kept as the default for any tag nobody has
# explicitly recolored yet.
_FALLBACK_PALETTE = [
    "#ff6b6b", "#f59f00", "#ffd43b", "#69db7c", "#38d9a9", "#4dabf7",
    "#748ffc", "#da77f2", "#f783ac", "#ff922b", "#20c997", "#22b8cf",
]


def resolve_tag_color(tag_id: str, color: str | None) -> str:
    """The stored `color`, or -- when a tag has never had one explicitly set
    -- a deterministic hash-based fallback (kept identical to the client-side
    hash this app used before `tag_catalog.color` existed), so every tag
    always has a usable color regardless of whether it was ever repicked."""
    if color:
        return color
    hash_value = 0
    for ch in tag_id:
        hash_value = (hash_value * 31 + ord(ch)) & 0xFFFFFFFF
    if hash_value >= 0x80000000:
        hash_value -= 0x100000000
    return _FALLBACK_PALETTE[abs(hash_value) % len(_FALLBACK_PALETTE)]


def _row_to_dict(row) -> dict:
    return {
        "id": row.id,
        "tag_key": row.tag_key,
        "display_name": row.display_name,
        "is_active": bool(row.is_active),
        "is_ai_vocabulary": bool(row.is_ai_vocabulary),
        "is_user_defined": bool(row.is_user_defined),
        "sort_order": row.sort_order,
        "color": resolve_tag_color(row.id, row.color),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_tags(
    engine, query: str | None = None, active_only: bool = False, limit: int | None = None,
    category: str | None = None,
) -> list[dict]:
    """Scoped to one managed tag pool, never the whole `tag_catalog` (user
    request): `category="user"` returns the user-defined pool
    (`is_user_defined = 1`, Settings' own section + the per-file
    user-defined-tag picker); anything else (the default) returns the AI
    vocabulary (`is_ai_vocabulary = 1`) -- Settings' vocabulary editor and
    every AI-tagging prompt builder. A tag auto-created purely as a side
    effect of `assign_tuning_parameter_tags()`, or typed ad-hoc directly onto
    a file (`get_or_create_tag()`'s default), belongs to neither pool and
    never appears from this function -- see `list_used_tags()` for a listing
    that covers every pool."""
    clauses = ["is_user_defined = 1"] if category == "user" else ["is_ai_vocabulary = 1"]
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
    """Tags actually assigned to at least one file in this archive, from
    *any* pool -- AI vocabulary, user-defined, or plain ad-hoc (as opposed to
    `list_tags()`, which is always scoped to a single managed pool and
    includes vocabulary/user-defined entries never actually applied to a
    file). Feeds every "type a tag to add it to this file" suggestion list
    (playback screen's quick tag-add, `FileInfoPanel`, Tag Lab's review step
    -- user request: suggestions while typing must cover every tag type, not
    just the AI vocabulary), ordered by how often each tag is used so the
    most locally-relevant matches surface first.

    User-defined tags (`is_user_defined = 1`) are the one exception to "used
    on a file": they're included even with zero usages (LEFT JOIN, not
    JOIN), so a tag someone just created in Settings' user-defined pool
    shows up as a suggestion right away instead of only after it's first
    been attached to a file somewhere (user report)."""
    clauses = ["(ft.id IS NOT NULL OR tc.is_user_defined = 1)"]
    params: dict = {}
    if query:
        clauses.append("tc.tag_key LIKE :prefix")
        params["prefix"] = f"{normalize_tag_key(query)}%"
    where_sql = f"WHERE {' AND '.join(clauses)}"
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
                LEFT JOIN file_tags ft ON ft.tag_id = tc.id
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
                INSERT INTO tag_catalog
                    (id, tag_key, display_name, is_active, is_ai_vocabulary, is_user_defined,
                     sort_order, color, created_at, updated_at)
                VALUES (:id, :tag_key, :display_name, :is_active, :is_ai_vocabulary, :is_user_defined,
                        :sort_order, :color, :now, :now)
                """
            ),
            {
                "id": tag_id,
                "tag_key": tag_key,
                "display_name": data["display_name"].strip(),
                "is_active": bool(data.get("is_active", True)),
                "is_ai_vocabulary": bool(data.get("is_ai_vocabulary", True)),
                "is_user_defined": bool(data.get("is_user_defined", False)),
                "sort_order": data.get("sort_order", 0),
                "color": data.get("color"),
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
                    sort_order = :sort_order, color = :color, updated_at = :now
                WHERE id = :id
                """
            ),
            {
                "tag_key": new_key,
                "display_name": merged["display_name"].strip(),
                "is_active": bool(merged["is_active"]),
                "sort_order": merged["sort_order"],
                "color": merged["color"],
                "now": now,
                "id": tag_id,
            },
        )
    return get_tag(engine, tag_id)


def get_or_create_tag(
    engine, display_name: str, *, is_ai_vocabulary: bool = False, is_user_defined: bool = False
) -> dict:
    """Resolve `display_name` to an existing entry (case/whitespace-
    insensitive match on `tag_key`), or create a new one -- used when a user
    types a tag by hand in `FileInfoPanel`/`QuickTagAdd`/Tag Lab instead of
    picking one from an existing list, so either path ends up assigning a
    real `tag_catalog` row. Neither pool flag is on by default (user
    request): typing a tag directly onto a file is its own ad-hoc pool,
    distinct from the AI vocabulary (Settings' own editor) and from
    user-defined tags (their own picker, `is_user_defined=True`) -- it must
    not silently join either managed list. `is_ai_vocabulary=True` is passed
    explicitly by Settings' vocabulary "add" flow; `is_user_defined=True` by
    the user-defined-tag picker's "create new" flow.

    Either flag, when explicitly requested, promotes an existing row that
    doesn't yet belong to that pool -- e.g. typing an existing ad-hoc tag's
    name into the user-defined picker's "new tag" field makes it a real
    user-defined tag from then on, even though it already existed. The
    reverse never happens: a flag already set is never cleared just because
    a caller asking for the other flag (or neither) happens to match the
    same name."""
    tag_key = normalize_tag_key(display_name)
    with engine.connect() as conn:
        existing = _get_by_key(conn, tag_key)
    if existing is not None:
        updates: dict = {}
        if is_ai_vocabulary and not existing.is_ai_vocabulary:
            updates["is_ai_vocabulary"] = 1
        if is_user_defined and not existing.is_user_defined:
            updates["is_user_defined"] = 1
        if updates:
            now = _now()
            set_sql = ", ".join(f"{column} = :{column}" for column in updates)
            with engine.begin() as conn:
                conn.execute(
                    text(f"UPDATE tag_catalog SET {set_sql}, updated_at = :now WHERE id = :id"),
                    {**updates, "now": now, "id": existing.id},
                )
            return get_tag(engine, existing.id)
        return _row_to_dict(existing)
    try:
        return create_tag(
            engine,
            {"display_name": display_name, "is_ai_vocabulary": is_ai_vocabulary, "is_user_defined": is_user_defined},
        )
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


def assign_user_defined_tag(
    engine, file_id: str, *, tag_id: str | None = None, display_name: str | None = None
) -> dict | None:
    """Attach a user-defined tag (purely subjective, never AI-scored, user
    request) to `file_id` via the dedicated picker button in `FileInfoPanel`
    and the playback screen -- distinct from the free-text add field, which
    creates ad-hoc tags in neither managed pool. `tag_id` attaches an
    existing tag as-is (returns `None` if it doesn't exist -- the caller's
    job to turn that into a 404, same convention as `get_tag()`);
    `display_name` creates a new tag (or promotes an existing one to the
    user-defined pool if the name happens to already exist as some other
    kind of tag). Returns the tag that was assigned."""
    if tag_id:
        tag = get_tag(engine, tag_id)
        if tag is None:
            return None
    else:
        tag = get_or_create_tag(engine, display_name, is_user_defined=True)
    assign_file_tag(engine, file_id, tag["id"])
    return tag


def assign_tuning_parameter_tags(engine, file_id: str, display_names: list[str]) -> None:
    """Tag a tuning-sweep variant file with its encode parameters (user
    request) -- one tag per parameter (codec, dimension cap, CRF), so a
    variant's settings are visible and removable like any other tag. Unlike
    `assign_file_tag` this does not touch `files.tagged_at`: parameter tags
    record how the file was produced, not an AI-tagging result. These land
    in neither managed pool (`get_or_create_tag()`'s own default, user
    request): a swept parameter like "640px" is not something Settings
    should list or a vision provider should ever be asked to score."""
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
                SELECT ft.file_id, tc.id AS tag_id, tc.display_name, tc.color, ft.score,
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
                    "color": resolve_tag_color(row.tag_id, row.color),
                    "score": row.score,
                    "provider_name": row.provider_name,
                    "model_name": row.model_name,
                }
            )
    return result


_TOP_FOLDER_TAG_COUNT = 5


def top_tags_for_directory_subtree(conn, source_id: str, relative_path: str, limit: int = _TOP_FOLDER_TAG_COUNT) -> list[dict]:
    """The `limit` most frequently assigned tags among every file in this
    directory's subtree (recursively, user request), across all three tag
    pools -- AI vocabulary, user-defined, and ad-hoc (anything actually
    attached to a file via `file_tags`, same "every pool" scope as
    `list_used_tags()`). Ties broken alphabetically for determinism. Dynamic,
    uncached, same `relative_path LIKE` subtree-scoping convention as
    `status.compute_directory_status()`; takes an already-open `conn` for the
    same reason that function does -- both callers (`routers/tree.py`,
    `routers/directories.py`) call this once per directory node inside one
    already-open connection, so opening a fresh one per node would be
    wasteful."""
    if relative_path == "":
        clause = ""
        params: dict = {"sid": source_id, "limit": limit}
    else:
        clause = "AND f.relative_path LIKE :prefix"
        params = {"sid": source_id, "prefix": f"{relative_path}/%", "limit": limit}

    rows = conn.execute(
        text(
            f"""
            SELECT tc.id AS tag_id, tc.display_name, tc.color, COUNT(*) AS usage_count
            FROM file_tags ft
            JOIN files f ON f.id = ft.file_id
            JOIN tag_catalog tc ON tc.id = ft.tag_id
            WHERE f.source_id = :sid AND ft.score > 0 {clause}
            GROUP BY tc.id
            ORDER BY usage_count DESC, tc.display_name COLLATE NOCASE
            LIMIT :limit
            """
        ),
        params,
    ).all()
    return [
        {
            "tag_id": row.tag_id,
            "display_name": row.display_name,
            "color": resolve_tag_color(row.tag_id, row.color),
            "usage_count": row.usage_count,
        }
        for row in rows
    ]
