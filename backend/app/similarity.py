"""Approximate near-duplicate video detection (Specification §13, Data Model
§10). Optional and secondary: a failure here must never block preview or
conversion completion -- callers always wrap signature computation/storage in
a best-effort try/except (see `app/jobs/preview.py`).

Exact binary hashing isn't sufficient because videos may be re-encoded
(Specification §13), so each video is reduced to a small set of 64-bit
average-hashes (aHash), one per sampled interior frame -- the same sampling
strategy already used for previews (`app/sampling.py`), the "preferred first
integration point" per the spec. aHash is tolerant of re-encoding, resizing,
and minor compression artifacts, unlike an exact content hash.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from sqlalchemy import text

from app import conversion
from app.preview import extract_frame_image, fill_missing_frames
from app.sampling import sample_interior_timestamps

SAMPLE_COUNT = 8
SIGNATURE_TYPE = "perceptual_hash"
HASH_SIZE = 8  # 8x8 grayscale -> 64-bit hash
DEFAULT_SIMILARITY_THRESHOLD = 10  # average Hamming distance out of 64 bits


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _average_hash(image_bgr) -> str:
    pil_image = Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)).convert("L")
    small = pil_image.resize((HASH_SIZE, HASH_SIZE), Image.LANCZOS)
    # tobytes() over deprecated getdata(); identical ints for a single-band "L" image.
    pixels = list(small.tobytes())
    average = sum(pixels) / len(pixels)
    bits = "".join("1" if p >= average else "0" for p in pixels)
    return f"{int(bits, 2):0{HASH_SIZE * HASH_SIZE // 4}x}"


def compute_signature(video_path: Path, sample_count: int = SAMPLE_COUNT) -> dict | None:
    """Returns `None` when the video can't be probed/sampled at all -- callers
    treat that as "no signature available" rather than an error."""
    info = conversion.probe_media(video_path)
    if info is None or not info.get("has_video_stream") or not info.get("duration"):
        return None

    timestamps = sample_interior_timestamps(info["duration"], sample_count)
    if not timestamps:
        return None
    images = fill_missing_frames([extract_frame_image(video_path, ts) for ts in timestamps])
    hashes = [_average_hash(img) for img in images if img is not None]
    if not hashes:
        return None
    return {"sample_count": len(hashes), "signature_type": SIGNATURE_TYPE, "hashes": hashes}


def compute_image_signature(image_path: Path) -> dict | None:
    """Image sibling of `compute_signature()` (post-V1, user request --
    "similar images"): no ffprobe/sampling involved, just a single aHash over
    the whole image -- shaped identically (`sample_count: 1`) so
    `store_signature()`/`find_similar()` need no further changes. Windows
    non-ASCII-path safe (`np.fromfile()` + `cv2.imdecode()`, never
    `cv2.imread()`, same convention as `preview.py`)."""
    data = np.fromfile(str(image_path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        return None
    return {"sample_count": 1, "signature_type": SIGNATURE_TYPE, "hashes": [_average_hash(image)]}


def store_signature(engine, file_id: str, signature: dict, job_id: str | None = None) -> None:
    now = _now()
    payload = json.dumps({"hashes": signature["hashes"]})
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM file_similarity_signatures WHERE file_id = :file_id"), {"file_id": file_id}
        ).fetchone()
        if existing:
            conn.execute(
                text(
                    """
                    UPDATE file_similarity_signatures
                    SET sample_count = :sample_count, signature_type = :signature_type,
                        signature_payload = :payload, generated_from_job_id = :job_id, updated_at = :now
                    WHERE file_id = :file_id
                    """
                ),
                {
                    "sample_count": signature["sample_count"],
                    "signature_type": signature["signature_type"],
                    "payload": payload,
                    "job_id": job_id,
                    "now": now,
                    "file_id": file_id,
                },
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO file_similarity_signatures
                        (id, file_id, sample_count, signature_type, signature_payload,
                         generated_from_job_id, created_at, updated_at)
                    VALUES (:id, :file_id, :sample_count, :signature_type, :payload, :job_id, :now, :now)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "file_id": file_id,
                    "sample_count": signature["sample_count"],
                    "signature_type": signature["signature_type"],
                    "payload": payload,
                    "job_id": job_id,
                    "now": now,
                },
            )


def _hex_hamming(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def _signature_distance(hashes_a: list[str], hashes_b: list[str]) -> float:
    """Average, over each hash in A, of its closest match in B -- tolerant of
    the two videos being sampled at slightly different interior timestamps
    (e.g. different durations after a re-encode)."""
    if not hashes_a or not hashes_b:
        return float("inf")
    total = sum(min(_hex_hamming(ha, hb) for hb in hashes_b) for ha in hashes_a)
    return total / len(hashes_a)


def find_similar(
    engine, source_id: str, file_id: str, threshold: int = DEFAULT_SIMILARITY_THRESHOLD, limit: int = 20
) -> list[dict]:
    with engine.connect() as conn:
        target = conn.execute(
            text(
                """
                SELECT s.signature_payload, f.is_video_supported
                FROM file_similarity_signatures s JOIN files f ON f.id = s.file_id
                WHERE s.file_id = :id
                """
            ),
            {"id": file_id},
        ).fetchone()
        if target is None:
            return []
        target_hashes = json.loads(target.signature_payload)["hashes"]

        rows = conn.execute(
            text(
                """
                SELECT s.file_id, s.signature_payload, f.relative_path, f.file_name
                FROM file_similarity_signatures s
                JOIN files f ON f.id = s.file_id
                WHERE f.source_id = :source_id AND s.file_id != :file_id
                  AND f.is_video_supported = :is_video
                """
            ),
            {"source_id": source_id, "file_id": file_id, "is_video": target.is_video_supported},
        ).all()

    results = []
    for row in rows:
        candidate_hashes = json.loads(row.signature_payload)["hashes"]
        distance = _signature_distance(target_hashes, candidate_hashes)
        if distance <= threshold:
            results.append(
                {
                    "file_id": row.file_id,
                    "relative_path": row.relative_path,
                    "file_name": row.file_name,
                    "distance": round(distance, 2),
                }
            )

    results.sort(key=lambda r: r["distance"])
    return results[:limit]
