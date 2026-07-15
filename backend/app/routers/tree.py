"""Directory tree endpoint (API §3)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import text

from app.db import get_engine
from app.source_access import get_active_source_or_404
from app.status import compute_directory_status
from app.tags import top_tags_for_directory_subtree

router = APIRouter()


@router.get("/tree")
def get_tree(
    path: str = Query(default=""),
    depth: int | None = Query(default=None),
    include_status: bool = Query(default=False),
    include_top_tags: bool = Query(default=False),
):
    engine = get_engine()
    with engine.connect() as conn:
        source = get_active_source_or_404(conn)

        rows = conn.execute(
            text("SELECT relative_path, name, parent_relative_path FROM directories WHERE source_id = :sid"),
            {"sid": source.id},
        ).all()

        by_path = {row.relative_path: row for row in rows}
        by_parent: dict[str | None, list] = {}
        for row in rows:
            # Keep None (root, no parent) distinct from "" (children of root);
            # collapsing them would make the root its own child.
            by_parent.setdefault(row.parent_relative_path, []).append(row)

        if path != "" and path not in by_path:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "directory_not_found", "message": f"Directory not found: {path}"}},
            )

        def build(rel_path: str, name: str, level: int) -> dict:
            node: dict = {"path": rel_path, "name": name}
            if include_status:
                node["status"] = compute_directory_status(conn, source.id, rel_path)
            if include_top_tags:
                node["top_tags"] = top_tags_for_directory_subtree(conn, source.id, rel_path)

            if depth is None or level < depth:
                children = sorted(by_parent.get(rel_path, []), key=lambda r: r.name.lower())
                node["children"] = [build(c.relative_path, c.name, level + 1) for c in children]
            else:
                node["children"] = []
            return node

        if path == "":
            tree = build("", source.name, 0)
        else:
            tree = build(path, by_path[path].name, 0)

    return tree
