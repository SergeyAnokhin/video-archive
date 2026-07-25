"""Single-file move/delete operations (user request; API §3).

Domain logic extracted from `routers/files.py` so the router stays thin
(architecture convention: routers validate + delegate). Both operations also
remove/relocate the file's sibling preview assets (the `<name>.jpg` collage
next to the video and the flattened GIF in `.video-archive/previews/`) via
the `app/sources/` layer, so they work for `local` and `smb` sources alike.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import PurePosixPath

from sqlalchemy import text

from app.media import preview_gif_relative_path
from app.sources import get_source_access


class FileOperationError(Exception):
    """A move/delete cannot proceed. `code` matches the API error code:
    `file_not_found`, `directory_not_found`, `same_location`, or
    `destination_collision` -- the router maps it to an HTTP status."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_with_source_lookup(conn, file_id: str):
    # f.id is deliberately excluded from the select list: s.* also carries an
    # `id` column (the source's), and the caller already has file_id in hand
    # (mirrors the same avoidance in routers/files.py's _preview_lookup()).
    return conn.execute(
        text(
            """
            SELECT f.relative_path, f.file_name, f.extension, f.directory_id, f.source_id, s.*
            FROM files f
            JOIN sources s ON s.id = f.source_id
            WHERE f.id = :id AND s.is_active = 1
            """
        ),
        {"id": file_id},
    ).fetchone()


def _has_sibling_jpg_collage(row) -> bool:
    """A `.jpg`/`.jpeg` file is its own collage-sibling candidate under
    `with_suffix(".jpg")` (e.g. `photo.jpeg` -> sibling `photo.jpg`, an
    unrelated file, not itself). Only a video (or any non-jpg file) can
    meaningfully have a separate `<stem>.jpg` collage sibling -- skip the
    sibling-cleanup step entirely for a standalone jpg/jpeg image to avoid
    deleting/renaming an unrelated same-stem `.jpg` neighbor."""
    return row.extension.lower() not in ("jpg", "jpeg")


def delete_file_rows(conn, file_id: str) -> None:
    """Deletes a file's `files`/`file_tags`/`file_similarity_signatures` rows
    (job history rows referencing the file are left as-is, same as the
    cleanup job). Callers are responsible for removing the file itself (and
    any sibling preview assets) from the source beforehand -- this only
    touches the database, so it's also reusable for a file whose disk removal
    happened elsewhere (e.g. the orphaned-previews cleanup)."""
    conn.execute(text("DELETE FROM file_tags WHERE file_id = :id"), {"id": file_id})
    conn.execute(text("DELETE FROM file_similarity_signatures WHERE file_id = :id"), {"id": file_id})
    conn.execute(text("DELETE FROM files WHERE id = :id"), {"id": file_id})


def delete_file(engine, file_id: str) -> None:
    """Removes the file plus its sibling preview assets from the source, then
    its DB rows via `delete_file_rows()`."""
    with engine.begin() as conn:
        row = _file_with_source_lookup(conn, file_id)
        if row is None:
            raise FileOperationError("file_not_found", f"File not found: {file_id}")

        access = get_source_access(row)
        if access.exists(row.relative_path):
            access.remote_remove(row.relative_path)

        if _has_sibling_jpg_collage(row):
            jpg_rel = str(PurePosixPath(row.relative_path).with_suffix(".jpg"))
            if access.exists(jpg_rel):
                access.remote_remove(jpg_rel)

        gif_rel = preview_gif_relative_path(row.relative_path)
        if access.exists(gif_rel):
            access.remote_remove(gif_rel)

        delete_file_rows(conn, file_id)


def move_file(engine, file_id: str, target_directory: str):
    """Relocates a file to another already-scanned directory in the same
    source (renaming its sibling preview assets alongside) and returns the
    updated `files` row joined with its new directory path."""
    with engine.begin() as conn:
        row = _file_with_source_lookup(conn, file_id)
        if row is None:
            raise FileOperationError("file_not_found", f"File not found: {file_id}")

        target_dir_row = conn.execute(
            text("SELECT id FROM directories WHERE source_id = :sid AND relative_path = :path"),
            {"sid": row.source_id, "path": target_directory},
        ).fetchone()
        if target_dir_row is None:
            raise FileOperationError("directory_not_found", f"Directory not found: {target_directory}")

        new_rel = f"{target_directory}/{row.file_name}" if target_directory else row.file_name
        if new_rel == row.relative_path:
            raise FileOperationError("same_location", "File is already in this folder.")

        collision = conn.execute(
            text("SELECT id FROM files WHERE source_id = :sid AND relative_path = :path"),
            {"sid": row.source_id, "path": new_rel},
        ).fetchone()
        if collision is not None:
            raise FileOperationError(
                "destination_collision", "A file with this name already exists in the destination folder."
            )

        access = get_source_access(row)
        access.remote_rename(row.relative_path, new_rel)

        if _has_sibling_jpg_collage(row):
            old_jpg_rel = str(PurePosixPath(row.relative_path).with_suffix(".jpg"))
            new_jpg_rel = str(PurePosixPath(new_rel).with_suffix(".jpg"))
            if access.exists(old_jpg_rel):
                access.remote_rename(old_jpg_rel, new_jpg_rel)

        old_gif_rel = preview_gif_relative_path(row.relative_path)
        new_gif_rel = preview_gif_relative_path(new_rel)
        if access.exists(old_gif_rel):
            access.ensure_dir(str(PurePosixPath(new_gif_rel).parent))
            access.remote_rename(old_gif_rel, new_gif_rel)

        conn.execute(
            text(
                """
                UPDATE files
                SET relative_path = :new_rel, directory_id = :dir_id, updated_at = :now
                WHERE id = :id
                """
            ),
            {"new_rel": new_rel, "dir_id": target_dir_row.id, "now": _now(), "id": file_id},
        )

        return conn.execute(
            text(
                """
                SELECT f.*, d.relative_path AS directory_path
                FROM files f
                JOIN directories d ON d.id = f.directory_id
                WHERE f.id = :id
                """
            ),
            {"id": file_id},
        ).fetchone()
