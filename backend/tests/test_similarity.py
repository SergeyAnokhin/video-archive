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

from app import provider_entries, similarity
from app import tags as tags_service
from app.jobs import preview as preview_job
from app.jobs import service
from app.jobs import tag as tag_job
from app.providers import registry
from app.scan import scan_source

from .conftest import make_image, make_video

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


def test_compute_image_signature_roundtrip(tmp_path):
    image_path = tmp_path / "photo.jpg"
    make_image(image_path, size=(160, 120))
    signature = similarity.compute_image_signature(image_path)
    assert signature is not None
    assert signature["sample_count"] == 1
    assert signature["signature_type"] == "perceptual_hash"


def test_compute_image_signature_returns_none_for_undecodable_file(tmp_path):
    bogus = tmp_path / "not-an-image.jpg"
    bogus.write_bytes(b"not a real image")
    assert similarity.compute_image_signature(bogus) is None


def test_find_similar_scopes_to_same_kind(engine, source):
    """Video and image signatures never cross-compare (post-V1, user
    request -- "similar images", image-vs-image only), even when their
    hashes happen to be identical."""
    make_video(source["root"] / "clip.mp4", duration=1.0, size="160x120")
    make_image(source["root"] / "photo.jpg", size=(160, 120), color=(0, 0, 0))
    make_image(source["root"] / "twin.png", size=(160, 120), color=(0, 0, 0))
    scan_source(engine, source["id"], source["root"])

    with engine.connect() as conn:
        rows = {r.relative_path: r for r in conn.execute(text("SELECT * FROM files")).all()}

    video_signature = similarity.compute_signature(source["root"] / "clip.mp4")
    similarity.store_signature(engine, rows["clip.mp4"].id, video_signature)
    photo_signature = similarity.compute_image_signature(source["root"] / "photo.jpg")
    similarity.store_signature(engine, rows["photo.jpg"].id, photo_signature)
    twin_signature = similarity.compute_image_signature(source["root"] / "twin.png")
    similarity.store_signature(engine, rows["twin.png"].id, twin_signature)

    similar_to_photo = similarity.find_similar(engine, source["id"], rows["photo.jpg"].id, threshold=64)
    similar_ids = {r["file_id"] for r in similar_to_photo}
    assert similar_ids == {rows["twin.png"].id}
    assert rows["clip.mp4"].id not in similar_ids


def test_tag_job_stores_image_signature(engine, source, monkeypatch):
    """Similarity detection for a standalone image piggybacks on the tag
    job as a best-effort side effect (post-V1, user request), the same way
    the preview job does for video."""

    def fake_fallback(engine, entries, images, tags, dead_entry_ids, **_kwargs):
        return [90], entries[0]

    monkeypatch.setattr(registry, "score_tags_with_fallback", fake_fallback)
    provider_entries.create_entry(
        engine, {"provider_type": "openrouter", "display_name": "openrouter", "enabled": True, "api_key": "sk-test"}
    )
    tags_service.create_tag(engine, {"display_name": "Beach"})

    make_image(source["root"] / "photo.jpg", size=(160, 120))
    scan_source(engine, source["id"], source["root"])
    with engine.connect() as conn:
        file_row = conn.execute(text("SELECT * FROM files WHERE relative_path = 'photo.jpg'")).fetchone()

    job = service.create_job(engine, "tag", "file", file_row.id, {"file_id": file_row.id})
    service.start_job(engine, job["id"])
    status, _message = tag_job.run_tag_job(engine, job)
    assert status == "completed"

    with engine.connect() as conn:
        signature_row = conn.execute(
            text("SELECT * FROM file_similarity_signatures WHERE file_id = :id"), {"id": file_row.id}
        ).fetchone()
    assert signature_row is not None
    assert signature_row.signature_type == "perceptual_hash"


def test_similar_files_endpoint_lazily_computes_image_signature(engine, source):
    """An image that was never tagged has no signature yet -- `/similar`
    computes and stores one on the spot instead of always returning empty."""
    from app.main import app

    make_image(source["root"] / "photo.jpg", size=(160, 120), color=(10, 20, 30))
    make_image(source["root"] / "twin.png", size=(160, 120), color=(10, 20, 30))
    scan_source(engine, source["id"], source["root"])
    with engine.connect() as conn:
        rows = {r.relative_path: r for r in conn.execute(text("SELECT * FROM files")).all()}

    # Pre-store the twin's signature so the target's lazy computation has
    # something to match against; the target itself has none yet.
    twin_signature = similarity.compute_image_signature(source["root"] / "twin.png")
    similarity.store_signature(engine, rows["twin.png"].id, twin_signature)

    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT 1 FROM file_similarity_signatures WHERE file_id = :id"), {"id": rows["photo.jpg"].id}
            ).fetchone()
            is None
        )

    with TestClient(app) as client:
        r = client.get(f"/api/files/{rows['photo.jpg'].id}/similar")
        assert r.status_code == 200
        assert any(entry["file_id"] == rows["twin.png"].id for entry in r.json()["similar"])

    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT 1 FROM file_similarity_signatures WHERE file_id = :id"), {"id": rows["photo.jpg"].id}
            ).fetchone()
            is not None
        )


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
