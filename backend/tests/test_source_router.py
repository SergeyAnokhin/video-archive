"""HTTP-layer tests for `/api/source*` (API §2, Specification §5): the
pre-Stage-7 `local` flow (regression) plus the Stage 7 `smb` flow — test
connection, connect (with credential storage + scan), and reconnect — driven
against the in-memory `fake_smb` fixture (`conftest.py`) since no real SMB
server is available in this environment.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

import app.db as db_module
from app import secrets_store, tags as tags_service
from app.main import app

_FINISHED_STATUSES = {"completed", "failed", "cancelled"}


def _wait_for_job(client: TestClient, job_id: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if client.get(f"/api/jobs/{job_id}").json()["status"] in _FINISHED_STATUSES:
            return
        time.sleep(0.05)
    raise AssertionError("job did not finish via HTTP in time")


def test_local_source_connect_and_test_connection(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    root = tmp_path / "library"
    root.mkdir()
    (root / "clip.mp4").write_bytes(b"0")

    with TestClient(app) as client:
        r = client.post("/api/source/test-connection", json={"name": "L", "protocol": "local", "root_path": str(root)})
        assert r.json()["ok"] is True

        r = client.put("/api/source", json={"name": "L", "protocol": "local", "root_path": str(root)})
        assert r.status_code == 200
        body = r.json()
        assert body["protocol"] == "local"
        assert body["detected_backups"] == []
        _wait_for_job(client, body["scan_job"]["id"])

        r = client.get("/api/source")
        assert r.json()["root_path"] == str(root.resolve())

        r = client.get("/api/files")
        assert len(r.json()["files"]) == 1

        r = client.post("/api/source/reconnect")
        assert r.json()["ok"] is True


def test_smb_source_test_connection_and_connect(tmp_path, monkeypatch, fake_smb):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    fake_smb.seed("clips/movie.mp4", b"0" * 42)

    with TestClient(app) as client:
        r = client.post(
            "/api/source/test-connection",
            json={
                "name": "NAS", "protocol": "smb", "host": fake_smb.host, "port": 445,
                "root_path": fake_smb.share, "username": "user", "password": "pass",
            },
        )
        assert r.json()["ok"] is True

        r = client.put(
            "/api/source",
            json={
                "name": "NAS", "protocol": "smb", "host": fake_smb.host, "port": 445,
                "root_path": fake_smb.share, "username": "user", "password": "pass",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["protocol"] == "smb"
        assert body["host"] == fake_smb.host
        _wait_for_job(client, body["scan_job"]["id"])

        r = client.get("/api/source")
        assert r.json()["host"] == fake_smb.host

        r = client.get("/api/files")
        assert len(r.json()["files"]) == 1
        assert r.json()["files"][0]["file_name"] == "movie.mp4"

        r = client.post("/api/source/reconnect")
        assert r.json()["ok"] is True


def test_smb_sources_keep_independent_credentials(tmp_path, monkeypatch, fake_smb):
    """Regression: SMB credentials used to be stored under one fixed key
    pair (`secrets_store.SOURCE_USERNAME_REF`/`SOURCE_SECRET_REF`), so
    saving a second SMB source would silently overwrite the first one's
    password. Each saved source now gets its own key pair via
    `set_source_credentials_for`."""
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.put(
            "/api/source",
            json={
                "name": "NAS1", "protocol": "smb", "host": fake_smb.host, "port": 445,
                "root_path": f"{fake_smb.share}/one", "username": "user1", "password": "pass1",
            },
        )
        assert r.status_code == 200
        source_1_id = r.json()["id"]

        r = client.put(
            "/api/source",
            json={
                "name": "NAS2", "protocol": "smb", "host": fake_smb.host, "port": 445,
                "root_path": f"{fake_smb.share}/two", "username": "user2", "password": "pass2",
            },
        )
        assert r.status_code == 200
        source_2_id = r.json()["id"]

        engine = db_module.get_engine()
        with engine.connect() as conn:
            row1 = conn.execute(text("SELECT * FROM sources WHERE id = :id"), {"id": source_1_id}).fetchone()
            row2 = conn.execute(text("SELECT * FROM sources WHERE id = :id"), {"id": source_2_id}).fetchone()

        assert row1.username_ref != row2.username_ref
        assert secrets_store.get_source_credentials_for(row1.username_ref, row1.secret_ref) == ("user1", "pass1")
        assert secrets_store.get_source_credentials_for(row2.username_ref, row2.secret_ref) == ("user2", "pass2")


def test_smb_source_requires_host(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.put("/api/source", json={"name": "NAS", "protocol": "smb", "root_path": "share"})
        assert r.status_code == 400
        assert r.json()["detail"]["error"]["code"] == "host_required"


def test_switching_sources_backs_up_and_auto_restores_from_saved_backup(tmp_path, monkeypatch):
    """Switching to a different source (Specification §5.2, updated for
    multiple saved sources): the outgoing source's own metadata (here, a
    file tag -- expensive to regenerate) is auto-backed-up to its own disk
    before the local wipe, and auto-restored (scoped tables only) the next
    time that same source becomes active again. Job history itself is
    never part of a backup (`app/backup.py`), so it's gone for good either
    way -- only re-checked here to confirm the wipe still happens."""
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    root_a = tmp_path / "library_a"
    root_a.mkdir()
    (root_a / "clip.mp4").write_bytes(b"0")
    root_b = tmp_path / "library_b"
    root_b.mkdir()
    (root_b / "other.mp4").write_bytes(b"0")

    with TestClient(app) as client:
        r = client.put("/api/source", json={"name": "A", "protocol": "local", "root_path": str(root_a)})
        assert r.status_code == 200
        _wait_for_job(client, r.json()["scan_job"]["id"])

        engine = db_module.get_engine()
        with engine.connect() as conn:
            file_row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'clip.mp4'")).fetchone()
        tag = tags_service.create_tag(engine, {"display_name": "sunset"})
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO file_tags (id, file_id, tag_id, score, provider_name, model_name, assigned_at) "
                    "VALUES (:id, :fid, :tid, 90, 'openrouter', 'test-model', :now)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "fid": file_row.id,
                    "tid": tag["id"],
                    "now": datetime.now(timezone.utc).isoformat(),
                },
            )

        r = client.post("/api/jobs/cleanup-stale-records")
        _wait_for_job(client, r.json()["id"])
        assert client.get("/api/jobs").json()["jobs"]

        # Switching to B backs A up (onto A's own disk) before wiping --
        # including the old job history, so the only job left right after
        # the switch is the new source's own reconciling scan.
        r = client.put("/api/source", json={"name": "B", "protocol": "local", "root_path": str(root_b)})
        assert r.status_code == 200
        assert r.json()["root_path"] == str(root_b.resolve())
        scan_job_b = r.json()["scan_job"]
        assert [j["id"] for j in client.get("/api/jobs").json()["jobs"]] == [scan_job_b["id"]]
        _wait_for_job(client, scan_job_b["id"])
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM file_tags")).scalar() == 0

        # Switching back to A auto-restores its tag from that backup.
        r = client.put("/api/source", json={"name": "A", "protocol": "local", "root_path": str(root_a)})
        assert r.status_code == 200
        assert r.json()["auto_restored"] is not None
        scan_job_a = r.json()["scan_job"]
        assert [j["id"] for j in client.get("/api/jobs").json()["jobs"]] == [scan_job_a["id"]]
        _wait_for_job(client, scan_job_a["id"])
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM file_tags")).scalar() == 1


def test_resubmitting_the_active_source_is_a_noop(tmp_path, monkeypatch):
    """Resubmitting the identical (protocol, host, port, root_path) while
    it's already the active source is how a saved source is renamed or has
    its credentials refreshed (see `put_source()`'s dedupe match) -- not a
    switch, so nothing gets backed up/wiped/restored and job history
    survives."""
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    root = tmp_path / "library"
    root.mkdir()
    (root / "clip.mp4").write_bytes(b"0")

    with TestClient(app) as client:
        r = client.put("/api/source", json={"name": "L", "protocol": "local", "root_path": str(root)})
        assert r.status_code == 200

        r = client.post("/api/jobs/cleanup-stale-records")
        _wait_for_job(client, r.json()["id"])
        assert client.get("/api/jobs").json()["jobs"]

        r = client.put("/api/source", json={"name": "L (renamed)", "protocol": "local", "root_path": str(root)})
        assert r.status_code == 200
        assert r.json()["name"] == "L (renamed)"
        assert r.json()["scan_job"] is None
        assert client.get("/api/jobs").json()["jobs"]


def test_active_smb_source_reconnect_updates_connection_params_without_rescan(tmp_path, monkeypatch, fake_smb):
    """User request: editing the active SMB source's connection parameters
    (port, username, password, name) while the underlying data is unchanged
    (same protocol + root_path) is a reconnect, not a switch -- same source
    id, no backup/wipe, no rescan job, and job history survives. Contrast
    with `test_switching_sources_backs_up_and_auto_restores_from_saved_backup`,
    where root_path actually changes."""
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    fake_smb.seed("clips/movie.mp4", b"0" * 42)

    with TestClient(app) as client:
        r = client.put(
            "/api/source",
            json={
                "name": "NAS", "protocol": "smb", "host": fake_smb.host, "port": 445,
                "root_path": fake_smb.share, "username": "user", "password": "pass",
            },
        )
        assert r.status_code == 200
        source_id = r.json()["id"]
        _wait_for_job(client, r.json()["scan_job"]["id"])

        r = client.post("/api/jobs/cleanup-stale-records")
        _wait_for_job(client, r.json()["id"])
        jobs_before = [j["id"] for j in client.get("/api/jobs").json()["jobs"]]
        assert jobs_before

        r = client.put(
            "/api/source",
            json={
                "name": "NAS (renamed)", "protocol": "smb", "host": fake_smb.host, "port": 4450,
                "root_path": fake_smb.share, "username": "user2", "password": "pass2",
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["id"] == source_id
        assert body["name"] == "NAS (renamed)"
        assert body["port"] == 4450
        assert body["scan_job"] is None
        assert body["detected_backups"] == []

        assert [j["id"] for j in client.get("/api/jobs").json()["jobs"]] == jobs_before

        r = client.get("/api/source")
        assert r.json()["port"] == 4450

        engine = db_module.get_engine()
        with engine.connect() as conn:
            row = conn.execute(text("SELECT * FROM sources WHERE id = :id"), {"id": source_id}).fetchone()
        assert secrets_store.get_source_credentials_for(row.username_ref, row.secret_ref) == ("user2", "pass2")


def test_active_smb_source_reconnect_rejects_bad_connection(tmp_path, monkeypatch, fake_smb):
    """A pre-flight `smb_test_connection()` check runs before an in-place
    reconnect is committed, so a bad host/password surfaces as a clean 400
    instead of an unhandled exception deeper in `switch_active_source()` --
    and the active source's row is left untouched."""
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.put(
            "/api/source",
            json={
                "name": "NAS", "protocol": "smb", "host": fake_smb.host, "port": 445,
                "root_path": fake_smb.share, "username": "user", "password": "pass",
            },
        )
        assert r.status_code == 200
        source_id = r.json()["id"]

        fake_smb.fail_next.append(RuntimeError("boom"))
        r = client.put(
            "/api/source",
            json={
                "name": "NAS", "protocol": "smb", "host": fake_smb.host, "port": 445,
                "root_path": fake_smb.share, "username": "user2", "password": "pass2",
            },
        )
        assert r.status_code == 400
        assert r.json()["detail"]["error"]["code"] == "connection_failed"

        engine = db_module.get_engine()
        with engine.connect() as conn:
            row = conn.execute(text("SELECT * FROM sources WHERE id = :id"), {"id": source_id}).fetchone()
        assert secrets_store.get_source_credentials_for(row.username_ref, row.secret_ref) == ("user", "pass")


def test_source_status_local(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    root = tmp_path / "library"
    root.mkdir()

    with TestClient(app) as client:
        r = client.get("/api/source/status")
        assert r.status_code == 404

        r = client.put("/api/source", json={"name": "L", "protocol": "local", "root_path": str(root)})
        assert r.status_code == 200

        r = client.get("/api/source/status")
        assert r.status_code == 200
        body = r.json()
        assert body == {"ok": True, "message": None, "direct_access_enabled": False, "direct_access_active": None}


def test_source_status_smb_direct_access(tmp_path, monkeypatch, fake_smb):
    from app.sources import smb_backend

    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.put(
            "/api/source",
            json={
                "name": "NAS", "protocol": "smb", "host": fake_smb.host, "port": 445,
                "root_path": fake_smb.share, "username": "user", "password": "pass",
                "direct_access_enabled": False,
            },
        )
        assert r.status_code == 200

        # Direct access disabled on the source: reachable, but the flag
        # itself says the fast path never applies.
        r = client.get("/api/source/status")
        body = r.json()
        assert body["ok"] is True
        assert body["direct_access_enabled"] is False
        assert body["direct_access_active"] is None

        r = client.put(
            "/api/source",
            json={
                "name": "NAS", "protocol": "smb", "host": fake_smb.host, "port": 445,
                "root_path": fake_smb.share, "username": "user", "password": "pass",
                "direct_access_enabled": True,
            },
        )
        assert r.status_code == 200

        monkeypatch.setattr(smb_backend.windows_unc, "available", lambda *a, **k: True)
        r = client.get("/api/source/status")
        body = r.json()
        assert body["ok"] is True
        assert body["direct_access_enabled"] is True
        assert body["direct_access_active"] is True

        monkeypatch.setattr(smb_backend.windows_unc, "available", lambda *a, **k: False)
        r = client.get("/api/source/status")
        body = r.json()
        assert body["direct_access_active"] is False


def test_smb_lock_status_and_release(tmp_path, monkeypatch):
    from app.sources import smb_backend

    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.get("/api/source/smb-lock-status")
        assert r.status_code == 200
        assert r.json() == {"held": False, "held_since": None, "seconds_held": None, "description": None}

        with smb_backend._locked("test operation"):
            r = client.get("/api/source/smb-lock-status")
            body = r.json()
            assert body["held"] is True
            assert body["description"] == "test operation"

            r = client.post("/api/source/smb-lock-status/release")
            assert r.json()["held"] is False

        # The (now-abandoned) holder's own `finally` must not resurrect the
        # cleared state once it "finishes" past the `with` block above.
        assert client.get("/api/source/smb-lock-status").json()["held"] is False


def test_unsupported_protocol_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.put("/api/source", json={"name": "X", "protocol": "webdav", "root_path": "/x"})
        assert r.status_code == 400
        assert r.json()["detail"]["error"]["code"] == "unsupported_protocol"
