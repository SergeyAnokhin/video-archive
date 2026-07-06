"""Similar video detection tests (Stage 9, Specification §13, Data Model
§10): signature computation/storage/lookup, the `preview` job's best-effort
hook, and the `GET /api/files/{id}/similar` endpoint.

Signature computation shells out to real ffmpeg/ffprobe (skipped
automatically if neither is on PATH), same convention as `test_preview.py`.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import similarity
from app.jobs import preview as preview_job
from app.jobs import service
from app.scan import scan_source

from .conftest import make_video

pytestmark = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not on PATH",
)


def make_black_video(path, *, size: str = "160x120", duration: float = 0.5) -> None:
    """A visually distinct video (solid black) so distance-based similarity
    tests have a clear negative case, unlike two `make_video()` clips which
    both render the same deterministic `testsrc` pattern."""
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"color=c=black:size={size}:duration={duration}:rate=5",
            "-pix_fmt", "yuv420p",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )


def test_compute_signature_returns_none_for_unprobeable_file(tmp_path):
    bogus = tmp_path / "not_a_video.mp4"
    bogus.write_bytes(b"not a real video")
    assert similarity.compute_signature(bogus) is None


def test_store_and_find_similar(engine, source):
    make_video(source["root"] / "a.mp4", duration=1.0, size="160x120")
    make_video(source["root"] / "b.mp4", duration=1.0, size="160x120")
    make_black_video(source["root"] / "c.mp4", duration=1.0, size="160x120")
    scan_source(engine, source["id"], source["root"])

    with engine.connect() as conn:
        rows = {r.relative_path: r for r in conn.execute(text("SELECT * FROM files")).all()}

    for rel in ("a.mp4", "b.mp4", "c.mp4"):
        signature = similarity.compute_signature(source["root"] / rel)
        assert signature is not None
        similarity.store_signature(engine, rows[rel].id, signature)

    similar_to_a = similarity.find_similar(engine, source["id"], rows["a.mp4"].id, threshold=15)
    similar_ids = {r["file_id"] for r in similar_to_a}
    assert rows["b.mp4"].id in similar_ids
    assert rows["c.mp4"].id not in similar_ids


def test_find_similar_returns_empty_without_a_signature(engine, source):
    make_video(source["root"] / "a.mp4", duration=1.0, size="160x120")
    scan_source(engine, source["id"], source["root"])
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'a.mp4'")).fetchone()
    assert similarity.find_similar(engine, source["id"], row.id) == []


def test_preview_job_stores_similarity_signature(engine, source):
    make_video(source["root"] / "clip.mp4", duration=1.0, size="160x120")
    scan_source(engine, source["id"], source["root"])
    with engine.connect() as conn:
        file_row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'clip.mp4'")).fetchone()

    job = service.create_job(engine, "preview", "file", file_row.id, {"file_id": file_row.id})
    service.start_job(engine, job["id"])
    status, _message = preview_job.run_preview_job(engine, job)
    assert status == "completed"

    with engine.connect() as conn:
        signature_row = conn.execute(
            text("SELECT * FROM file_similarity_signatures WHERE file_id = :id"), {"id": file_row.id}
        ).fetchone()
    assert signature_row is not None
    assert signature_row.signature_type == "perceptual_hash"


def test_similar_files_endpoint(engine, source):
    from app.main import app

    make_video(source["root"] / "a.mp4", duration=1.0, size="160x120")
    make_video(source["root"] / "b.mp4", duration=1.0, size="160x120")
    scan_source(engine, source["id"], source["root"])
    with engine.connect() as conn:
        rows = {r.relative_path: r for r in conn.execute(text("SELECT * FROM files")).all()}

    with TestClient(app) as client:
        assert client.get("/api/files/nonexistent/similar").status_code == 404

        r = client.get(f"/api/files/{rows['a.mp4'].id}/similar")
        assert r.status_code == 200
        assert r.json() == {"similar": []}  # no signature stored yet

        for rel, row in rows.items():
            signature = similarity.compute_signature(source["root"] / rel)
            similarity.store_signature(engine, row.id, signature)

        r = client.get(f"/api/files/{rows['a.mp4'].id}/similar")
        assert r.status_code == 200
        assert any(entry["file_id"] == rows["b.mp4"].id for entry in r.json()["similar"])
