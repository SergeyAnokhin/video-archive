"""`app.conversion_script` tests: the "generate conversion script" feature
(user request) -- a PowerShell script the user can run standalone, built
from the exact same encoder-resolution/params-merge logic real conversion
jobs use, plus the router endpoint that serves it.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

from app import conversion_profiles, conversion_script
from app.main import app


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _insert_dir(engine, source_id, relative_path, name, parent):
    dir_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO directories (id, source_id, relative_path, name, parent_relative_path, "
                "has_folder_preview, last_scanned_at, created_at, updated_at) "
                "VALUES (:id, :sid, :rel, :name, :parent, 0, :now, :now, :now)"
            ),
            {"id": dir_id, "sid": source_id, "rel": relative_path, "name": name, "parent": parent, "now": _now()},
        )
    return dir_id


def _insert_video_file(engine, source_id, dir_id, relative_path, file_name):
    file_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, has_preview_asset, "
                "created_at, updated_at) "
                "VALUES (:id, :sid, :did, :rel, :name, 'mp4', 1, :now, :now, 1, 0, :now, :now)"
            ),
            {"id": file_id, "sid": source_id, "did": dir_id, "rel": relative_path, "name": file_name, "now": _now()},
        )
    return file_id


def test_enumerate_directory_files_excludes_test_artifacts(engine, source):
    root_id = _insert_dir(engine, source["id"], "", "Root", None)
    clips_id = _insert_dir(engine, source["id"], "clips", "clips", "")
    _insert_video_file(engine, source["id"], root_id, "clip.mp4", "clip.mp4")
    _insert_video_file(engine, source["id"], clips_id, "clips/nested.mp4", "nested.mp4")
    _insert_video_file(
        engine, source["id"], root_id, "clip.variant-crf28.mp4", "clip.variant-crf28.mp4",
    )
    _insert_video_file(engine, source["id"], root_id, "clip.original.mp4", "clip.original.mp4")

    all_files = conversion_script.enumerate_directory_files(engine, source["id"], "")
    assert set(all_files) == {"clip.mp4", "clips/nested.mp4"}

    scoped = conversion_script.enumerate_directory_files(engine, source["id"], "clips")
    assert scoped == ["clips/nested.mp4"]


def test_generate_powershell_script_software_encoder():
    profile = {
        "video_codec": "h265",
        "container": "mp4",
        "crf": 26,
        "drop_audio": True,
        "max_dimension": 1080,
        "hardware_accel": "off",
        "preset": "veryfast",
        "extra_encoder_args": None,
    }
    script, container = conversion_script.generate_powershell_script(
        profile=profile,
        overrides=None,
        root_hint=r"C:\archive",
        relative_paths=["clip.mp4", "clips/nested.mp4"],
    )

    assert container == "mp4"
    assert "libx265" in script
    assert "-preset" in script and "veryfast" in script
    assert "'clip.mp4'" in script
    assert "'clips/nested.mp4'" in script
    assert "Move-Item" in script
    assert "$MaxDimension = 1080" in script


def test_generate_powershell_script_omits_preset_for_hardware_encoder():
    profile = {
        "video_codec": "h264",
        "container": "mp4",
        "crf": 23,
        "drop_audio": False,
        "max_dimension": None,
        "hardware_accel": "qsv",
        "preset": "fast",
        "extra_encoder_args": None,
    }
    script, _container = conversion_script.generate_powershell_script(
        profile=profile, overrides=None, root_hint=r"C:\archive", relative_paths=["clip.mp4"],
    )

    assert "$UsingHardwareEncoder = $true" in script
    assert "if (-not $UsingHardwareEncoder)" in script


def test_generate_conversion_script_endpoint(engine, source):
    profile = conversion_profiles.create_profile(
        engine, {"name": "P", "video_codec": "h265", "crf": 28, "preset": "fast"}
    )
    root_id = _insert_dir(engine, source["id"], "", "Root", None)
    _insert_video_file(engine, source["id"], root_id, "clip.mp4", "clip.mp4")

    with TestClient(app) as client:
        res = client.post(
            "/api/jobs/generate-conversion-script",
            json={"path": "", "profile_id": profile["id"], "overrides": {"crf": 30}},
        )

    assert res.status_code == 200
    body = res.json()
    assert body["file_count"] == 1
    assert body["container"] == "mp4"
    assert "-crf" in body["script"] and "30" in body["script"]


def test_generate_conversion_script_unknown_profile_is_404(source):
    with TestClient(app) as client:
        res = client.post(
            "/api/jobs/generate-conversion-script",
            json={"path": "", "profile_id": "does-not-exist"},
        )
    assert res.status_code == 404
