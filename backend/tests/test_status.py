"""Derived directory status tests (Specification §14): the
`compute_directory_status()` aggregation (subtree scoping, test-artifact and
unsupported-file exclusion, completeness flags) and the `GET /api/tree`
endpoint's `include_status`/`depth` behavior.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

import app.db as db_module
from app.main import app
from app.status import compute_directory_status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _add_dir(conn, source_id: str, rel_path: str, parent: str | None) -> str:
    dir_id = str(uuid.uuid4())
    conn.execute(
        text(
            "INSERT INTO directories (id, source_id, relative_path, name, parent_relative_path, "
            "has_folder_preview, last_scanned_at, created_at, updated_at) "
            "VALUES (:id, :sid, :rel, :name, :parent, 0, :now, :now, :now)"
        ),
        {
            "id": dir_id,
            "sid": source_id,
            "rel": rel_path,
            "name": rel_path.rsplit("/", 1)[-1] or "Root",
            "parent": parent,
            "now": _now(),
        },
    )
    return dir_id


def _add_file(
    conn,
    source_id: str,
    directory_id: str,
    rel_path: str,
    *,
    supported: bool = True,
    converted: bool = False,
    previewed: bool = False,
    size_bytes: int = 1,
) -> None:
    conn.execute(
        text(
            "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
            "size_bytes, discovered_at, last_scanned_at, is_video_supported, converted_at, "
            "has_preview_asset, created_at, updated_at) "
            "VALUES (:id, :sid, :did, :rel, :name, :ext, :size, :now, :now, :supported, :converted_at, "
            ":previewed, :now, :now)"
        ),
        {
            "id": str(uuid.uuid4()),
            "sid": source_id,
            "did": directory_id,
            "rel": rel_path,
            "name": rel_path.rsplit("/", 1)[-1],
            "ext": rel_path.rsplit(".", 1)[-1],
            "supported": 1 if supported else 0,
            "converted_at": _now() if converted else None,
            "previewed": 1 if previewed else 0,
            "size": size_bytes,
            "now": _now(),
        },
    )


def _seed_library(engine, source_id: str) -> None:
    """Root with dirs `a`, `a/b`, `ab` (the `ab` name checks that the `a/%`
    prefix match doesn't leak into sibling directories with the same prefix),
    plus test artifacts and an unsupported file that must never be counted."""
    with engine.begin() as conn:
        root = _add_dir(conn, source_id, "", None)
        a = _add_dir(conn, source_id, "a", "")
        a_b = _add_dir(conn, source_id, "a/b", "a")
        ab = _add_dir(conn, source_id, "ab", "")
        _add_dir(conn, source_id, "empty", "")

        _add_file(conn, source_id, root, "top.mp4")
        _add_file(conn, source_id, a, "a/x.mp4", converted=True, previewed=True)
        _add_file(conn, source_id, a_b, "a/b/y.mp4", converted=True, previewed=True)
        _add_file(conn, source_id, ab, "ab/z.mp4")
        # Excluded from every count: test-mode artifacts and unsupported files.
        _add_file(conn, source_id, a, "a/x.original.mp4")
        _add_file(conn, source_id, a, "a/x.variant-crf28.mp4")
        _add_file(conn, source_id, a, "a/note.txt", supported=False)


def test_compute_directory_status_subtree_scoping_and_exclusions(engine, source):
    _seed_library(engine, source["id"])

    with engine.connect() as conn:
        root_status = compute_directory_status(conn, source["id"], "")
        # top.mp4, a/x.mp4, a/b/y.mp4, ab/z.mp4 — artifacts and note.txt excluded.
        assert root_status["total_supported_files"] == 4
        assert root_status["converted_count"] == 2
        assert root_status["preview_count"] == 2
        assert root_status["conversion_complete"] is False
        assert root_status["preview_complete"] is False

        # `a` subtree: a/x.mp4 + a/b/y.mp4, both complete; `ab/z.mp4` must
        # not leak in despite sharing the `a` prefix, and the unconverted
        # `.original.`/`.variant-` artifacts must not break completeness.
        a_status = compute_directory_status(conn, source["id"], "a")
        assert a_status["total_supported_files"] == 2
        assert a_status["conversion_complete"] is True
        assert a_status["preview_complete"] is True

        ab_status = compute_directory_status(conn, source["id"], "ab")
        assert ab_status["total_supported_files"] == 1
        assert ab_status["converted_count"] == 0


def test_compute_directory_status_empty_directory_counts_as_complete(engine, source):
    _seed_library(engine, source["id"])
    with engine.connect() as conn:
        status = compute_directory_status(conn, source["id"], "empty")
    assert status["total_supported_files"] == 0
    assert status["conversion_complete"] is True
    assert status["preview_complete"] is True


def test_compute_directory_status_total_size_bytes(engine, source):
    _seed_library(engine, source["id"])
    with engine.connect() as conn:
        root_status = compute_directory_status(conn, source["id"], "")
        a_status = compute_directory_status(conn, source["id"], "a")

    # top.mp4, a/x.mp4, a/b/y.mp4, ab/z.mp4 -- each seeded with size_bytes=1;
    # test-artifacts and unsupported files must not be counted (same
    # exclusions as total_supported_files).
    assert root_status["total_size_bytes"] == 4
    assert a_status["total_size_bytes"] == 2


def test_compute_directory_status_top_variant_tags(engine, source):
    with engine.begin() as conn:
        clips = _add_dir(conn, source["id"], "clips", "")
        # Two sibling groups sweeping dimension: 1000px appears in both, so
        # it must rank above the dimensions that only appear once.
        _add_file(conn, source["id"], clips, "clips/a.variant-d1000.mp4")
        _add_file(conn, source["id"], clips, "clips/a.variant-d1080.mp4")
        _add_file(conn, source["id"], clips, "clips/b.variant-d1000.mp4")
        _add_file(conn, source["id"], clips, "clips/b.variant-d720.mp4")

    with engine.connect() as conn:
        status = compute_directory_status(conn, source["id"], "clips")

    top_tags = status["top_variant_tags"]
    assert top_tags[0] == {"param": "dimension", "value": 1000}
    assert len(top_tags) == 3


def _client_with_seeded_source(tmp_path, monkeypatch) -> tuple[TestClient, str]:
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)
    db_module.init_db()
    engine = db_module.get_engine()

    source_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sources (id, name, protocol, root_path, is_active, created_at, updated_at) "
                "VALUES (:id, 'Test', 'local', :root, 1, :now, :now)"
            ),
            {"id": source_id, "root": str(tmp_path / "src"), "now": _now()},
        )
    _seed_library(engine, source_id)
    return TestClient(app), source_id


def test_tree_include_status_and_depth(tmp_path, monkeypatch):
    client, _ = _client_with_seeded_source(tmp_path, monkeypatch)
    with client:
        r = client.get("/api/tree", params={"include_status": "true"})
        assert r.status_code == 200
        tree = r.json()
        assert tree["path"] == ""
        assert tree["status"]["total_supported_files"] == 4
        children = {c["name"]: c for c in tree["children"]}
        assert children["a"]["status"]["conversion_complete"] is True
        assert children["ab"]["status"]["conversion_complete"] is False
        assert [c["path"] for c in children["a"]["children"]] == ["a/b"]

        # depth limits recursion; status is still computed for visible nodes.
        r = client.get("/api/tree", params={"depth": 0, "include_status": "true"})
        assert r.json()["children"] == []
        assert r.json()["status"]["total_supported_files"] == 4

        # Without include_status no status key is present.
        r = client.get("/api/tree")
        assert "status" not in r.json()


def test_tree_unknown_path_404(tmp_path, monkeypatch):
    client, _ = _client_with_seeded_source(tmp_path, monkeypatch)
    with client:
        r = client.get("/api/tree", params={"path": "nope"})
        assert r.status_code == 404
        assert r.json()["detail"]["error"]["code"] == "directory_not_found"
