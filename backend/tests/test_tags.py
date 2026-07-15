"""Unit tests for `app/tags.py` functions not already covered by the HTTP-
layer tests in `test_tagging_router.py` -- currently just
`top_tags_for_directory_subtree()` (user request: dynamic top-5 folder tags).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text

import app.db as db_module
from app.tags import create_tag, resolve_tag_color, top_tags_for_directory_subtree


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)
    db_module.init_db()
    return db_module.get_engine()


def _make_source_and_dirs(engine, root):
    root.mkdir(parents=True, exist_ok=True)
    (root / "sub").mkdir(parents=True, exist_ok=True)
    source_id = str(uuid.uuid4())
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sources (id, name, protocol, root_path, is_active, created_at, updated_at) "
                "VALUES (:id, 'Test', 'local', :root, 1, :now, :now)"
            ),
            {"id": source_id, "root": str(root), "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO directories (id, source_id, relative_path, name, parent_relative_path, "
                "has_folder_preview, last_scanned_at, created_at, updated_at) "
                "VALUES (:id, :sid, '', 'Root', NULL, 0, :now, :now, :now)"
            ),
            {"id": str(uuid.uuid4()), "sid": source_id, "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO directories (id, source_id, relative_path, name, parent_relative_path, "
                "has_folder_preview, last_scanned_at, created_at, updated_at) "
                "VALUES (:id, :sid, 'sub', 'sub', '', 0, :now, :now, :now)"
            ),
            {"id": str(uuid.uuid4()), "sid": source_id, "now": now},
        )
    return source_id


def _make_file(engine, source_id, relative_path):
    file_id = str(uuid.uuid4())
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, created_at, updated_at) "
                "SELECT :fid, :sid, d.id, :rel, :rel, 'mp4', 1, :now, :now, 1, :now, :now "
                "FROM directories d WHERE d.source_id = :sid "
                "AND d.relative_path = (CASE WHEN instr(:rel, '/') > 0 "
                "THEN substr(:rel, 1, instr(:rel, '/') - 1) ELSE '' END)"
            ),
            {"fid": file_id, "sid": source_id, "rel": relative_path, "now": now},
        )
    return file_id


def _assign(engine, file_id, tag_id, score=100, provider_name="manual"):
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO file_tags (id, file_id, tag_id, score, provider_name, model_name, assigned_at) "
                "VALUES (:id, :fid, :tid, :score, :provider, NULL, :now)"
            ),
            {"id": str(uuid.uuid4()), "fid": file_id, "tid": tag_id, "score": score, "provider": provider_name, "now": _now()},
        )


def test_top_tags_for_directory_subtree_ranks_by_frequency_recursively(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path, monkeypatch)
    source_id = _make_source_and_dirs(engine, tmp_path / "source")

    root_file = _make_file(engine, source_id, "root.mp4")
    sub_file_a = _make_file(engine, source_id, "sub/a.mp4")
    sub_file_b = _make_file(engine, source_id, "sub/b.mp4")

    beach = create_tag(engine, {"display_name": "Beach"})
    sunset = create_tag(engine, {"display_name": "Sunset"})
    night = create_tag(engine, {"display_name": "Night", "is_ai_vocabulary": False, "is_user_defined": True})
    rejected = create_tag(engine, {"display_name": "Rejected"})

    # Beach: 3 uses (all three files) -> most frequent.
    _assign(engine, root_file, beach["id"])
    _assign(engine, sub_file_a, beach["id"], provider_name="openrouter")
    _assign(engine, sub_file_b, beach["id"], provider_name="openrouter")
    # Sunset: 2 uses, both inside "sub".
    _assign(engine, sub_file_a, sunset["id"])
    _assign(engine, sub_file_b, sunset["id"])
    # Night (user-defined pool): 1 use -- confirms every pool counts, not
    # just the AI vocabulary (user request: "все назначенные теги").
    _assign(engine, sub_file_a, night["id"])
    # A 0-scored tag (AI evaluated and rejected it) must not count.
    _assign(engine, sub_file_a, rejected["id"], score=0, provider_name="openrouter")

    with engine.connect() as conn:
        root_top = top_tags_for_directory_subtree(conn, source_id, "")
        sub_top = top_tags_for_directory_subtree(conn, source_id, "sub")

    assert [t["display_name"] for t in root_top] == ["Beach", "Sunset", "Night"]
    assert root_top[0]["usage_count"] == 3
    assert root_top[0]["color"] == resolve_tag_color(beach["id"], None)

    # Scoped to "sub" only: Beach (2, from sub_file_a/b) and Sunset (2) tie on
    # count, broken alphabetically ("Beach" < "Sunset"); "Night" (1) last;
    # the root-only file's Beach assignment must not leak in.
    assert [t["display_name"] for t in sub_top] == ["Beach", "Sunset", "Night"]
    assert sub_top[0]["usage_count"] == 2
    assert sub_top[1]["usage_count"] == 2


def test_top_tags_for_directory_subtree_limits_to_five(tmp_path, monkeypatch):
    engine = _make_engine(tmp_path, monkeypatch)
    source_id = _make_source_and_dirs(engine, tmp_path / "source")
    file_id = _make_file(engine, source_id, "root.mp4")

    for i in range(7):
        tag = create_tag(engine, {"display_name": f"Tag{i}"})
        _assign(engine, file_id, tag["id"])

    with engine.connect() as conn:
        top = top_tags_for_directory_subtree(conn, source_id, "")

    assert len(top) == 5
