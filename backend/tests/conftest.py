"""Shared fixtures: every test gets its own temp SQLite db and never touches
the developer's real `backend/video_archive.db` (which may have a real
worker/dev-server attached to it).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

import app.db as db_module


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)
    db_module.init_db()
    return db_module.get_engine()


@pytest.fixture()
def source(engine, tmp_path):
    """An active `local` source row pointing at an empty temp directory."""
    source_root = tmp_path / "source"
    source_root.mkdir()
    source_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO sources (id, name, protocol, root_path, is_active, created_at, updated_at) "
                "VALUES (:id, 'Test', 'local', :root, 1, :now, :now)"
            ),
            {"id": source_id, "root": str(source_root), "now": now},
        )
    return {"id": source_id, "root": source_root}


def make_files(root: Path, count: int, subdir: str = "clips") -> None:
    folder = root / subdir
    folder.mkdir(parents=True, exist_ok=True)
    for i in range(count):
        (folder / f"clip_{i:04d}.mp4").write_bytes(b"0")


def make_video(path: Path, *, size: str = "160x120", duration: float = 0.5) -> None:
    """Encode a tiny real video with ffmpeg (h264/mp4-ish by default) so
    conversion tests exercise real ffmpeg/ffprobe instead of fixture bytes."""
    import subprocess

    path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"testsrc=duration={duration}:size={size}:rate=5",
            "-pix_fmt", "yuv420p",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to generate test video: {result.stderr[-500:]}")
