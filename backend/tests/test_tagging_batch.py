"""Batch tagging tests (Stage 9, Specification §12.3): provider-level request
construction/response parsing for `submit_batch()` on the two providers with
a real Batch API (Gemini, Mistral -- see Tech Stack), plus the `tag` job's
directory-scope orchestration (batch success, partial fallback, and
whole-batch-failure fallback), all against mocked HTTP/`registry` calls so no
real network access happens and no real ffmpeg dependency is needed for the
orchestration tests.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import text

from app import provider_configs, tagging, tagging_settings
from app import tags as tags_service
from app.jobs import service
from app.jobs import tag as tag_job
from app.providers import gemini, mistral
from app.providers import registry
from app.providers.base import ProviderError


class FakeJsonResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://example.invalid")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self):
        return self._json_data


class FakeTextResponse:
    def __init__(self, text_body, status_code=200):
        self.text = text_body
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=httpx.Request("GET", "https://example.invalid"), response=None)


FAKE_IMAGE = b"\xff\xd8fake-jpeg-bytes"
TAGS = ["cat", "beach"]


# --- provider-level: Mistral batch -----------------------------------------


def test_mistral_submit_batch_happy_path(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(("POST", url, kwargs))
        if url == mistral.FILES_URL:
            return FakeJsonResponse({"id": "file-in-1"})
        if url == mistral.BATCH_JOBS_URL:
            return FakeJsonResponse({"id": "job-1"})
        raise AssertionError(f"unexpected POST {url}")

    def fake_get(url, **kwargs):
        calls.append(("GET", url, kwargs))
        if url == f"{mistral.BATCH_JOBS_URL}/job-1":
            return FakeJsonResponse({"status": "SUCCESS", "output_file": "file-out-1"})
        if url == f"{mistral.FILES_URL}/file-out-1/content":
            body = (
                '{"custom_id": "file-a", "response": {"body": {"choices": [{"message": {"content": "[80, 20]"}}]}}}\n'
                '{"custom_id": "file-b", "response": {"body": {"choices": [{"message": {"content": "not json"}}]}}}\n'
            )
            return FakeTextResponse(body)
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(mistral.time, "sleep", lambda _s: None)

    results = mistral.submit_batch(
        [("file-a", [FAKE_IMAGE]), ("file-b", [FAKE_IMAGE])], TAGS, None, "ms-test"
    )

    assert results["file-a"] == [80, 20]
    assert results["file-b"] is None  # malformed content -> caller falls back per-file


def test_mistral_submit_batch_raises_on_job_failure(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda url, **k: FakeJsonResponse({"id": "x"}))
    monkeypatch.setattr(httpx, "get", lambda url, **k: FakeJsonResponse({"status": "FAILED"}))
    monkeypatch.setattr(mistral.time, "sleep", lambda _s: None)

    with pytest.raises(ProviderError):
        mistral.submit_batch([("file-a", [FAKE_IMAGE])], TAGS, None, "ms-test")


# --- provider-level: Gemini batch -------------------------------------------


def test_gemini_submit_batch_happy_path(monkeypatch):
    def fake_post(url, **kwargs):
        assert url == gemini.BATCH_CREATE_URL_TEMPLATE.format(model=gemini.DEFAULT_MODEL)
        requests = kwargs["json"]["batch"]["input_config"]["requests"]["requests"]
        assert len(requests) == 2
        return FakeJsonResponse({"name": "batches/123"})

    def fake_get(url, **kwargs):
        assert url == gemini.BATCH_POLL_URL_TEMPLATE.format(name="batches/123")
        return FakeJsonResponse(
            {
                "done": True,
                "response": {
                    "inlinedResponses": {
                        "inlinedResponses": [
                            {"response": {"candidates": [{"content": {"parts": [{"text": "[70, 30]"}]}}]}},
                            {"error": {"message": "boom"}},
                        ]
                    }
                },
            }
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(gemini.time, "sleep", lambda _s: None)

    results = gemini.submit_batch(
        [("file-a", [FAKE_IMAGE]), ("file-b", [FAKE_IMAGE])], TAGS, None, "gm-test"
    )

    assert results["file-a"] == [70, 30]
    assert results["file-b"] is None  # entry had no candidates -> caller falls back per-file


# --- job orchestration: directory-scope batch tagging -----------------------


def _make_file_row(engine, source_id, directory_id, root, name: str):
    (root / name).write_bytes(b"0")  # local_copy()/exists() need a real file on disk
    now = datetime.now(timezone.utc).isoformat()
    file_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO files (id, source_id, directory_id, relative_path, file_name, extension, "
                "size_bytes, discovered_at, last_scanned_at, is_video_supported, created_at, updated_at) "
                "VALUES (:id, :sid, :did, :name, :name, 'mp4', 1, :now, :now, 1, :now, :now)"
            ),
            {"id": file_id, "sid": source_id, "did": directory_id, "name": name, "now": now},
        )
    return file_id


@pytest.fixture()
def two_files(engine, source):
    now = datetime.now(timezone.utc).isoformat()
    dir_id = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO directories (id, source_id, relative_path, name, parent_relative_path, "
                "has_folder_preview, last_scanned_at, created_at, updated_at) "
                "VALUES (:id, :sid, '', 'root', NULL, 0, :now, :now, :now)"
            ),
            {"id": dir_id, "sid": source["id"], "now": now},
        )
    file_a = _make_file_row(engine, source["id"], dir_id, source["root"], "a.mp4")
    file_b = _make_file_row(engine, source["id"], dir_id, source["root"], "b.mp4")
    tags_service.create_tag(engine, {"display_name": "Beach"})
    tags_service.create_tag(engine, {"display_name": "Snow"})
    provider_configs.update_provider(
        engine, "gemini", {"enabled": True, "api_key": "gm-test", "batch_enabled": True}
    )
    tagging_settings.update_settings(engine, {"default_provider": "gemini", "top_tag_count": 2})
    return file_a, file_b


@pytest.fixture(autouse=False)
def stub_build_images(monkeypatch):
    monkeypatch.setattr(tagging, "build_tagging_images", lambda video_path, count, combine: [FAKE_IMAGE])


def _run_directory_tag_job(engine):
    job = service.create_job(engine, "tag", "source", None, {"path": "", "provider_name": "gemini"})
    service.start_job(engine, job["id"])
    return tag_job.run_tag_job(engine, job)


def test_directory_batch_tagging_all_succeed(engine, source, two_files, stub_build_images, monkeypatch):
    file_a, file_b = two_files

    def fake_batch(engine_, provider_name, items, tags):
        assert provider_name == "gemini"
        assert {key for key, _images in items} == {file_a, file_b}
        return {file_a: [90, 10], file_b: [10, 90]}

    monkeypatch.setattr(registry, "score_tags_batch_with_provider", fake_batch)
    called_single = []
    monkeypatch.setattr(
        registry, "score_tags_with_provider", lambda *a, **k: called_single.append(1) or [0, 0]
    )

    status, message = _run_directory_tag_job(engine)

    assert status == "completed"
    assert "2 of 2" in message
    assert not called_single  # batch resolved everything; no per-file fallback needed

    with engine.connect() as conn:
        tagged_count = conn.execute(
            text("SELECT COUNT(*) FROM files WHERE tagged_at IS NOT NULL")
        ).scalar()
    assert tagged_count == 2


def test_directory_batch_tagging_partial_fallback(engine, source, two_files, stub_build_images, monkeypatch):
    file_a, file_b = two_files

    def fake_batch(engine_, provider_name, items, tags):
        return {file_a: [90, 10], file_b: None}  # b unresolved by the batch

    monkeypatch.setattr(registry, "score_tags_batch_with_provider", fake_batch)
    fallback_calls = []

    def fake_single(engine_, provider_name, images, tags):
        fallback_calls.append(1)
        return [20, 80]

    monkeypatch.setattr(registry, "score_tags_with_provider", fake_single)

    status, message = _run_directory_tag_job(engine)

    assert status == "completed"
    assert "2 of 2" in message
    assert len(fallback_calls) == 1  # only file_b needed the per-file fallback

    with engine.connect() as conn:
        tagged_count = conn.execute(
            text("SELECT COUNT(*) FROM files WHERE tagged_at IS NOT NULL")
        ).scalar()
    assert tagged_count == 2


def test_directory_batch_tagging_submission_failure_falls_back_for_all(
    engine, source, two_files, stub_build_images, monkeypatch
):
    def fake_batch(engine_, provider_name, items, tags):
        raise ProviderError("batch endpoint unavailable")

    monkeypatch.setattr(registry, "score_tags_batch_with_provider", fake_batch)
    fallback_calls = []

    def fake_single(engine_, provider_name, images, tags):
        fallback_calls.append(1)
        return [50, 50]

    monkeypatch.setattr(registry, "score_tags_with_provider", fake_single)

    status, message = _run_directory_tag_job(engine)

    assert status == "completed"
    assert "2 of 2" in message
    assert len(fallback_calls) == 2  # both files fell back to per-file scoring
