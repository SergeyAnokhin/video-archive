"""Backup creation, retention, and restore tests (Stage 8, Specification §19,
Backup Format). Exercises `app/backup.py` directly (core logic) plus the
`backup`/`restore`/`cleanup`/`optimize_db` job handlers, against both `local`
and `smb` sources (`fake_smb`).
"""

from __future__ import annotations

import uuid
import zipfile
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

import app.db as db_module
from app import backup, backup_settings, provider_entries
from app import secrets_store as secrets_store_module
from app import tags as tags_service
from app.jobs import service
from app.jobs.backup import run_backup_job
from app.jobs.cleanup import run_cleanup_job
from app.jobs.optimize_db import run_optimize_db_job
from app.jobs.restore import run_restore_job
from app.sources import get_source_access

from .conftest import make_files


def _source_row(engine, source_id: str):
    with engine.connect() as conn:
        return conn.execute(text("SELECT * FROM sources WHERE id = :id"), {"id": source_id}).fetchone()


def _seed_library(engine, source_id: str) -> tuple[str, str]:
    """Populate one directory + one file + a tag assignment for `source_id`."""
    now = datetime.now(timezone.utc).isoformat()
    dir_id = str(uuid.uuid4())
    file_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO directories (id, source_id, relative_path, name, parent_relative_path, "
                "has_folder_preview, last_scanned_at, created_at, updated_at) "
                "VALUES (:id, :sid, 'clips', 'clips', NULL, 0, :now, :now, :now)"
            ),
            {"id": dir_id, "sid": source_id, "now": now},
        )
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, has_preview_asset, "
                "created_at, updated_at) "
                "VALUES (:id, :sid, :did, 'clips/clip_0000.mp4', 'clip_0000.mp4', 'mp4', 1, :now, :now, 1, 0, "
                ":now, :now)"
            ),
            {"id": file_id, "sid": source_id, "did": dir_id, "now": now},
        )
    tag = tags_service.create_tag(engine, {"display_name": "sunset"})
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO file_tags (id, file_id, tag_id, score, provider_name, model_name, assigned_at) "
                "VALUES (:id, :fid, :tid, 90, 'openrouter', 'test-model', :now)"
            ),
            {"id": str(uuid.uuid4()), "fid": file_id, "tid": tag["id"], "now": now},
        )
    return dir_id, file_id


def test_create_backup_writes_zip_with_manifest_and_data(engine, source):
    _seed_library(engine, source["id"])
    row = _source_row(engine, source["id"])
    access = get_source_access(row)

    result = backup.create_backup(engine, access, row)

    zip_path = source["root"] / ".video-archive" / "backups" / result["filename"]
    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        import json

        manifest = json.loads(zf.read("manifest.json"))
        data = json.loads(zf.read("data.json"))

    assert manifest["backup_id"] == result["backup_id"]
    assert manifest["includes_secrets"] is False
    assert len(data["directories"]) == 1
    assert len(data["files"]) == 1
    assert len(data["file_tags"]) == 1
    assert len(data["tag_catalog"]) == 1


def test_list_backups_empty_before_any_backup(engine, source):
    row = _source_row(engine, source["id"])
    access = get_source_access(row)
    assert backup.list_backups(access) == []


def test_retention_removes_oldest_backups(engine, source):
    row = _source_row(engine, source["id"])
    access = get_source_access(row)
    backup_settings.update_settings(engine, {"retention_count": 2})

    for _ in range(3):
        backup.create_backup(engine, access, row)

    assert len(backup.list_backups(access)) == 2


def test_delete_backup(engine, source):
    row = _source_row(engine, source["id"])
    access = get_source_access(row)
    backup.create_backup(engine, access, row)
    backup_id = backup.list_backups(access)[0]["id"]

    assert backup.delete_backup(access, backup_id) is True
    assert backup.list_backups(access) == []
    assert backup.delete_backup(access, backup_id) is False


def test_restore_backup_recreates_wiped_library_under_new_source_id(engine, source):
    _seed_library(engine, source["id"])
    old_row = _source_row(engine, source["id"])
    access = get_source_access(old_row)
    backup.create_backup(engine, access, old_row)
    backup_id = backup.list_backups(access)[0]["id"]

    # Simulate a destructive source switch (Specification §5.2): wipe the old
    # source's rows and connect a *new* source row pointing at the same disk.
    new_source_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM file_tags"))
        conn.execute(text("DELETE FROM files"))
        conn.execute(text("DELETE FROM directories"))
        conn.execute(text("DELETE FROM sources"))
        conn.execute(
            text(
                "INSERT INTO sources (id, name, protocol, root_path, is_active, created_at, updated_at) "
                "VALUES (:id, 'Test', 'local', :root, 1, :now, :now)"
            ),
            {"id": new_source_id, "root": str(source["root"]), "now": now},
        )
    new_row = _source_row(engine, new_source_id)
    new_access = get_source_access(new_row)

    result = backup.restore_backup(engine, new_access, new_row, backup_id)

    assert result["counts"]["files"] == 1
    assert result["counts"]["directories"] == 1
    with engine.connect() as conn:
        file_row = conn.execute(
            text("SELECT * FROM files WHERE source_id = :sid"), {"sid": new_source_id}
        ).fetchone()
        dir_row = conn.execute(
            text("SELECT * FROM directories WHERE source_id = :sid"), {"sid": new_source_id}
        ).fetchone()
        tag_rows = conn.execute(
            text("SELECT * FROM file_tags WHERE file_id = :fid"), {"fid": file_row.id}
        ).all()
    assert file_row.relative_path == "clips/clip_0000.mp4"
    assert dir_row.relative_path == "clips"
    assert len(tag_rows) == 1


def test_restore_backup_rejects_newer_schema_version(engine, source, monkeypatch):
    row = _source_row(engine, source["id"])
    access = get_source_access(row)
    backup.create_backup(engine, access, row)
    backup_id = backup.list_backups(access)[0]["id"]

    monkeypatch.setattr(db_module, "SCHEMA_VERSION", db_module.SCHEMA_VERSION - 1)

    with pytest.raises(backup.RestoreError):
        backup.restore_backup(engine, access, row, backup_id)


def test_restore_backup_missing_package_raises(engine, source):
    row = _source_row(engine, source["id"])
    access = get_source_access(row)
    with pytest.raises(backup.RestoreError):
        backup.restore_backup(engine, access, row, "does-not-exist")


def test_backup_include_secrets_roundtrip(engine, source):
    secrets_store_module.set_entry_api_key("entry-1", "sk-test-123")
    row = _source_row(engine, source["id"])
    access = get_source_access(row)

    backup.create_backup(engine, access, row, include_secrets=True)
    entries = backup.list_backups(access)
    assert entries[0]["includes_secrets"] is True
    backup_id = entries[0]["id"]

    secrets_store_module.SECRETS_PATH.write_text("")
    assert secrets_store_module.has_entry_api_key("entry-1") is False

    backup.restore_backup(engine, access, row, backup_id)
    assert secrets_store_module.has_entry_api_key("entry-1") is True


def test_backup_and_restore_provider_entries(engine, source):
    provider_entries.create_entry(
        engine,
        {"provider_type": "gemini", "display_name": "My Gemini", "enabled": True, "vision_model": "gemini-2.5-flash"},
    )
    row = _source_row(engine, source["id"])
    access = get_source_access(row)
    backup.create_backup(engine, access, row)
    backup_id = backup.list_backups(access)[0]["id"]

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provider_entries"))
    assert provider_entries.list_entries(engine) == []

    backup.restore_backup(engine, access, row, backup_id)
    restored = provider_entries.list_entries(engine)
    assert len(restored) == 1
    assert restored[0]["display_name"] == "My Gemini"
    assert restored[0]["provider_type"] == "gemini"


def test_restore_backup_with_include_global_false_skips_global_tables(engine, source):
    """`include_global=False` (used by the source-switch flow,
    `app/source_switch.py`) must restore only this source's own scoped data
    and leave every global settings/entity table untouched, even though the
    backup package still contains that global data -- app-wide settings are
    shared across every saved source and must never change as a side effect
    of switching (user request)."""
    _seed_library(engine, source["id"])
    provider_entries.create_entry(
        engine,
        {"provider_type": "gemini", "display_name": "My Gemini", "enabled": True, "vision_model": "gemini-2.5-flash"},
    )
    row = _source_row(engine, source["id"])
    access = get_source_access(row)
    backup.create_backup(engine, access, row)
    backup_id = backup.list_backups(access)[0]["id"]

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM file_tags"))
        conn.execute(text("DELETE FROM files"))
        conn.execute(text("DELETE FROM directories"))
        conn.execute(text("DELETE FROM provider_entries"))

    result = backup.restore_backup(engine, access, row, backup_id, include_global=False)

    assert result["counts"]["files"] == 1
    with engine.connect() as conn:
        files_left = conn.execute(
            text("SELECT COUNT(*) FROM files WHERE source_id = :sid"), {"sid": source["id"]}
        ).scalar()
    assert files_left == 1
    assert provider_entries.list_entries(engine) == []


def test_create_and_restore_backup_over_smb(engine, smb_source):
    source_id = smb_source["id"]
    _seed_library(engine, source_id)
    row = _source_row(engine, source_id)
    access = get_source_access(row)

    backup.create_backup(engine, access, row)
    entries = backup.list_backups(access)
    assert len(entries) == 1

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM file_tags"))
        conn.execute(text("DELETE FROM files"))
        conn.execute(text("DELETE FROM directories"))

    result = backup.restore_backup(engine, access, row, entries[0]["id"])
    assert result["counts"]["files"] == 1
    assert result["counts"]["directories"] == 1


def test_backup_and_restore_job_handlers(engine, source):
    _seed_library(engine, source["id"])

    backup_job = service.create_job(engine, "backup", "maintenance", None, {"include_secrets": False})
    status, _message = run_backup_job(engine, backup_job)
    assert status == "completed"

    row = _source_row(engine, source["id"])
    access = get_source_access(row)
    backup_id = backup.list_backups(access)[0]["id"]

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM file_tags"))
        conn.execute(text("DELETE FROM files"))
        conn.execute(text("DELETE FROM directories"))

    restore_job = service.create_job(engine, "restore", "maintenance", backup_id, {"backup_id": backup_id})
    status, _message = run_restore_job(engine, restore_job)
    assert status == "completed"

    with engine.connect() as conn:
        count = conn.execute(
            text("SELECT COUNT(*) FROM files WHERE source_id = :sid"), {"sid": source["id"]}
        ).scalar()
    assert count == 1


def test_restore_job_reports_failure_for_unknown_backup(engine, source):
    job = service.create_job(engine, "restore", "maintenance", "nope", {"backup_id": "nope"})
    status, message = run_restore_job(engine, job)
    assert status == "failed"
    assert "not found" in message.lower()


def test_cleanup_job_removes_stale_records(engine, source):
    _seed_library(engine, source["id"])  # rows only -- nothing written to disk

    job = service.create_job(engine, "cleanup", "maintenance", None, {})
    status, _message = run_cleanup_job(engine, job)
    assert status == "completed"

    with engine.connect() as conn:
        files_left = conn.execute(
            text("SELECT COUNT(*) FROM files WHERE source_id = :sid"), {"sid": source["id"]}
        ).scalar()
        dirs_left = conn.execute(
            text("SELECT COUNT(*) FROM directories WHERE source_id = :sid"), {"sid": source["id"]}
        ).scalar()
        tags_left = conn.execute(text("SELECT COUNT(*) FROM file_tags")).scalar()
    assert files_left == 0
    assert dirs_left == 0
    assert tags_left == 0


def test_cleanup_job_keeps_records_that_still_exist(engine, source):
    make_files(source["root"], 1)  # clips/clip_0000.mp4
    _seed_library(engine, source["id"])

    job = service.create_job(engine, "cleanup", "maintenance", None, {})
    status, _message = run_cleanup_job(engine, job)
    assert status == "completed"

    with engine.connect() as conn:
        files_left = conn.execute(
            text("SELECT COUNT(*) FROM files WHERE source_id = :sid"), {"sid": source["id"]}
        ).scalar()
    assert files_left == 1


def test_optimize_db_job_runs(engine):
    job = service.create_job(engine, "optimize_db", "maintenance", None, {})
    status, _message = run_optimize_db_job(engine, job)
    assert status == "completed"
