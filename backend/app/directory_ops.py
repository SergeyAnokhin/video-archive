"""Folder create/delete/favorite operations (user request; API §3).

Domain logic kept out of `routers/directories.py` so the router stays thin,
mirroring the move/delete split already done for files in `app/file_ops.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app.sources import get_source_access


class DirectoryOperationError(Exception):
    """A create/delete/favorite operation cannot proceed. `code` matches the
    API error code: `directory_not_found`, `invalid_name`,
    `destination_collision`, or `directory_not_empty` -- the router maps it
    to an HTTP status."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _active_source(conn):
    return conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()


def _directory_row(conn, source_id: str, path: str):
    return conn.execute(
        text("SELECT * FROM directories WHERE source_id = :sid AND relative_path = :path"),
        {"sid": source_id, "path": path},
    ).fetchone()


def create_directory(engine, parent_path: str, name: str):
    """Creates a new subdirectory under the already-scanned `parent_path`,
    both on the source and as a `directories` row, and returns the new row."""
    name = name.strip()
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        raise DirectoryOperationError("invalid_name", "Folder name is empty or contains invalid characters.")

    with engine.begin() as conn:
        source = _active_source(conn)
        if source is None:
            raise DirectoryOperationError("directory_not_found", f"Directory not found: {parent_path}")

        if parent_path and _directory_row(conn, source.id, parent_path) is None:
            raise DirectoryOperationError("directory_not_found", f"Directory not found: {parent_path}")

        new_rel = f"{parent_path}/{name}" if parent_path else name

        if _directory_row(conn, source.id, new_rel) is not None:
            raise DirectoryOperationError("destination_collision", "A folder with this name already exists.")

        access = get_source_access(source)
        if access.exists(new_rel):
            raise DirectoryOperationError("destination_collision", "A file or folder with this name already exists.")
        access.remote_mkdir(new_rel)

        now = _now()
        dir_id = str(uuid.uuid4())
        conn.execute(
            text(
                """
                INSERT INTO directories
                    (id, source_id, relative_path, name, parent_relative_path, created_at, updated_at)
                VALUES (:id, :sid, :path, :name, :parent, :now, :now)
                """
            ),
            {"id": dir_id, "sid": source.id, "path": new_rel, "name": name, "parent": parent_path, "now": now},
        )

        return _directory_row(conn, source.id, new_rel)


def delete_directory(engine, path: str):
    """Removes an empty directory (no files, no subdirectories) from both the
    source and the `directories` table. Non-empty directories are rejected
    rather than deleted recursively, to avoid destroying video files."""
    if not path:
        raise DirectoryOperationError("invalid_name", "Cannot delete the root directory.")

    with engine.begin() as conn:
        source = _active_source(conn)
        if source is None:
            raise DirectoryOperationError("directory_not_found", f"Directory not found: {path}")

        row = _directory_row(conn, source.id, path)
        if row is None:
            raise DirectoryOperationError("directory_not_found", f"Directory not found: {path}")

        has_child_dir = conn.execute(
            text("SELECT id FROM directories WHERE source_id = :sid AND parent_relative_path = :path LIMIT 1"),
            {"sid": source.id, "path": path},
        ).fetchone()
        if has_child_dir is not None:
            raise DirectoryOperationError("directory_not_empty", "Folder contains subfolders.")

        has_child_file = conn.execute(
            text("SELECT id FROM files WHERE directory_id = :id LIMIT 1"),
            {"id": row.id},
        ).fetchone()
        if has_child_file is not None:
            raise DirectoryOperationError("directory_not_empty", "Folder contains files.")

        access = get_source_access(source)
        if access.exists(path):
            access.remote_rmdir(path)

        conn.execute(text("DELETE FROM directories WHERE id = :id"), {"id": row.id})


def set_favorite(engine, path: str, favorite: bool):
    with engine.begin() as conn:
        source = _active_source(conn)
        if source is None:
            raise DirectoryOperationError("directory_not_found", f"Directory not found: {path}")

        row = _directory_row(conn, source.id, path)
        if row is None:
            raise DirectoryOperationError("directory_not_found", f"Directory not found: {path}")

        conn.execute(
            text(
                """
                UPDATE directories
                SET is_favorite = :fav, favorited_at = :favorited_at, updated_at = :now
                WHERE id = :id
                """
            ),
            {
                "fav": 1 if favorite else 0,
                "favorited_at": _now() if favorite else None,
                "now": _now(),
                "id": row.id,
            },
        )

        return _directory_row(conn, source.id, path)


def list_favorites(engine) -> list[dict]:
    with engine.connect() as conn:
        source = _active_source(conn)
        if source is None:
            return []

        rows = conn.execute(
            text(
                "SELECT relative_path, name FROM directories "
                "WHERE source_id = :sid AND is_favorite = 1 "
                "ORDER BY favorited_at"
            ),
            {"sid": source.id},
        ).all()
        return [{"path": row.relative_path, "name": row.name} for row in rows]
