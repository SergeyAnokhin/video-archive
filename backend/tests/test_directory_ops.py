"""Folder create/delete/favorite endpoints (user request): `POST /api/directories`,
`DELETE /api/directories`, `PUT /api/directories/favorite`, `GET /api/directories/favorites`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_directory(engine, source_id: str, path: str, name: str, parent: str) -> str:
    dir_id = str(uuid.uuid4())
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO directories (id, source_id, relative_path, name, parent_relative_path, "
                "has_folder_preview, created_at, updated_at) "
                "VALUES (:id, :sid, :path, :name, :parent, 0, :now, :now)"
            ),
            {"id": dir_id, "sid": source_id, "path": path, "name": name, "parent": parent, "now": now},
        )
    return dir_id


def _insert_file(engine, source_id: str, dir_id: str, rel_path: str) -> None:
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, has_preview_asset, "
                "created_at, updated_at) "
                "VALUES (:id, :sid, :did, :rel, :rel, 'mp4', 1, :now, :now, 1, 0, :now, :now)"
            ),
            {"id": str(uuid.uuid4()), "sid": source_id, "did": dir_id, "rel": rel_path, "now": now},
        )


def test_create_directory_at_root_creates_row_and_folder(engine, source):
    _insert_directory(engine, source["id"], "", "Root", None)

    with TestClient(app) as client:
        res = client.post("/api/directories", json={"parent_path": "", "name": "New Folder"})
        assert res.status_code == 200
        assert res.json() == {"path": "New Folder", "name": "New Folder"}

        assert (source["root"] / "New Folder").is_dir()

        children = client.get("/api/directories/children", params={"path": ""}).json()
        assert [d["path"] for d in children["directories"]] == ["New Folder"]
        assert children["directories"][0]["is_favorite"] is False


def test_create_directory_under_existing_parent(engine, source):
    _insert_directory(engine, source["id"], "Parent", "Parent", "")
    (source["root"] / "Parent").mkdir()

    with TestClient(app) as client:
        res = client.post("/api/directories", json={"parent_path": "Parent", "name": "Child"})
        assert res.status_code == 200
        assert res.json()["path"] == "Parent/Child"
        assert (source["root"] / "Parent" / "Child").is_dir()


def test_create_directory_rejects_invalid_name(engine, source):
    with TestClient(app) as client:
        res = client.post("/api/directories", json={"parent_path": "", "name": "a/b"})
        assert res.status_code == 400
        assert res.json()["detail"]["error"]["code"] == "invalid_name"


def test_create_directory_missing_parent(engine, source):
    with TestClient(app) as client:
        res = client.post("/api/directories", json={"parent_path": "Ghost", "name": "Child"})
        assert res.status_code == 404
        assert res.json()["detail"]["error"]["code"] == "directory_not_found"


def test_create_directory_collision(engine, source):
    with TestClient(app) as client:
        res1 = client.post("/api/directories", json={"parent_path": "", "name": "Dup"})
        assert res1.status_code == 200
        res2 = client.post("/api/directories", json={"parent_path": "", "name": "Dup"})
        assert res2.status_code == 409
        assert res2.json()["detail"]["error"]["code"] == "destination_collision"


def test_delete_empty_directory(engine, source):
    _insert_directory(engine, source["id"], "Empty", "Empty", "")
    (source["root"] / "Empty").mkdir()

    with TestClient(app) as client:
        res = client.delete("/api/directories", params={"path": "Empty"})
        assert res.status_code == 200
        assert res.json() == {"deleted": True}
        assert not (source["root"] / "Empty").exists()


def test_delete_directory_rejects_non_empty_with_file(engine, source):
    dir_id = _insert_directory(engine, source["id"], "HasFile", "HasFile", "")
    (source["root"] / "HasFile").mkdir()
    _insert_file(engine, source["id"], dir_id, "HasFile/clip.mp4")

    with TestClient(app) as client:
        res = client.delete("/api/directories", params={"path": "HasFile"})
        assert res.status_code == 400
        assert res.json()["detail"]["error"]["code"] == "directory_not_empty"


def test_delete_directory_rejects_non_empty_with_subdir(engine, source):
    _insert_directory(engine, source["id"], "Parent", "Parent", "")
    _insert_directory(engine, source["id"], "Parent/Child", "Child", "Parent")
    (source["root"] / "Parent" / "Child").mkdir(parents=True)

    with TestClient(app) as client:
        res = client.delete("/api/directories", params={"path": "Parent"})
        assert res.status_code == 400
        assert res.json()["detail"]["error"]["code"] == "directory_not_empty"


def test_delete_directory_not_found(engine, source):
    with TestClient(app) as client:
        res = client.delete("/api/directories", params={"path": "Ghost"})
        assert res.status_code == 404
        assert res.json()["detail"]["error"]["code"] == "directory_not_found"


def test_favorite_toggle_roundtrip(engine, source):
    _insert_directory(engine, source["id"], "Fav", "Fav", "")

    with TestClient(app) as client:
        res = client.put("/api/directories/favorite", json={"path": "Fav", "favorite": True})
        assert res.status_code == 200
        assert res.json() == {"path": "Fav", "name": "Fav", "is_favorite": True}

        favorites = client.get("/api/directories/favorites").json()
        assert favorites == {"favorites": [{"path": "Fav", "name": "Fav"}]}

        res = client.put("/api/directories/favorite", json={"path": "Fav", "favorite": False})
        assert res.status_code == 200
        assert res.json()["is_favorite"] is False

        favorites = client.get("/api/directories/favorites").json()
        assert favorites == {"favorites": []}


def test_favorite_directory_not_found(engine, source):
    with TestClient(app) as client:
        res = client.put("/api/directories/favorite", json={"path": "Ghost", "favorite": True})
        assert res.status_code == 404
        assert res.json()["detail"]["error"]["code"] == "directory_not_found"
