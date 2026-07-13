"""Batch tagging tests (Stage 9, Specification §12.3): provider-level request
construction/response parsing for `create_batch()`/`poll_batch()` on the two
providers with a real Batch API (Gemini, Mistral -- see Tech Stack), plus the
`tag` job's directory-scope orchestration (batch success, partial fallback,
whole-batch-failure fallback, and resuming a submission that survived a
restart), all against mocked HTTP/`registry` calls so no real network access
happens and no real ffmpeg dependency is needed for the orchestration tests.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import text

from app import batch_submissions, provider_entries, tagging, tagging_settings
from app import tags as tags_service
from app.jobs import service
from app.jobs import tag as tag_job
from app.providers import gemini, mistral
from app.providers import registry
from app.providers.base import BatchPollResult, ProviderError, UsageInfo


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


def test_mistral_create_batch_uploads_and_creates_job(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        if url == mistral.FILES_URL:
            return FakeJsonResponse({"id": "file-in-1"})
        if url == mistral.BATCH_JOBS_URL:
            return FakeJsonResponse({"id": "job-1"})
        raise AssertionError(f"unexpected POST {url}")

    monkeypatch.setattr(httpx, "post", fake_post)

    external_batch_id = mistral.create_batch(
        [("file-a", [FAKE_IMAGE]), ("file-b", [FAKE_IMAGE])], TAGS, None, "ms-test"
    )

    assert external_batch_id == "job-1"
    assert len(calls) == 2


def test_mistral_poll_batch_not_done_yet(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, **k: FakeJsonResponse({"status": "RUNNING"}))
    result = mistral.poll_batch("job-1", TAGS, "ms-test")
    assert result.done is False


def test_mistral_poll_batch_success_parses_results_and_usage(monkeypatch):
    def fake_get(url, **kwargs):
        if url == f"{mistral.BATCH_JOBS_URL}/job-1":
            return FakeJsonResponse({"status": "SUCCESS", "output_file": "file-out-1"})
        if url == f"{mistral.FILES_URL}/file-out-1/content":
            body = (
                '{"custom_id": "file-a", "response": {"body": {"choices": [{"message": {"content": "[80, 20]"}}], '
                '"usage": {"prompt_tokens": 100, "completion_tokens": 5}}}}\n'
                '{"custom_id": "file-b", "response": {"body": {"choices": [{"message": {"content": "not json"}}], '
                '"usage": {"prompt_tokens": 120, "completion_tokens": 7}}}}\n'
            )
            return FakeTextResponse(body)
        raise AssertionError(f"unexpected GET {url}")

    monkeypatch.setattr(httpx, "get", fake_get)

    result = mistral.poll_batch("job-1", TAGS, "ms-test")

    assert result.done is True
    assert result.error is None
    assert result.results["file-a"] == [80, 20]
    assert result.results["file-b"] is None  # malformed content -> caller falls back per-file
    assert result.usage.tokens_in == 220
    assert result.usage.tokens_out == 12


def test_mistral_poll_batch_reports_job_failure(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, **k: FakeJsonResponse({"status": "FAILED"}))
    result = mistral.poll_batch("job-1", TAGS, "ms-test")
    assert result.done is True
    assert result.error is not None


# --- provider-level: Gemini batch -------------------------------------------


def test_gemini_create_batch_submits_all_requests(monkeypatch):
    def fake_post(url, **kwargs):
        assert url == gemini.BATCH_CREATE_URL_TEMPLATE.format(model=gemini.DEFAULT_MODEL)
        requests = kwargs["json"]["batch"]["input_config"]["requests"]["requests"]
        assert len(requests) == 2
        return FakeJsonResponse({"name": "batches/123"})

    monkeypatch.setattr(httpx, "post", fake_post)

    external_batch_id = gemini.create_batch(
        [("file-a", [FAKE_IMAGE]), ("file-b", [FAKE_IMAGE])], TAGS, None, "gm-test"
    )
    assert external_batch_id == "batches/123"


def test_gemini_poll_batch_not_done_yet(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, **k: FakeJsonResponse({"done": False}))
    result = gemini.poll_batch("batches/123", ["file-a"], TAGS, "gm-test")
    assert result.done is False


def test_gemini_poll_batch_success_correlates_by_order_and_sums_usage(monkeypatch):
    def fake_get(url, **kwargs):
        assert url == gemini.BATCH_POLL_URL_TEMPLATE.format(name="batches/123")
        return FakeJsonResponse(
            {
                "done": True,
                "response": {
                    "inlinedResponses": {
                        "inlinedResponses": [
                            {
                                "response": {
                                    "candidates": [{"content": {"parts": [{"text": "[70, 30]"}]}}],
                                    "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 6},
                                }
                            },
                            {"error": {"message": "boom"}},
                        ]
                    }
                },
            }
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    result = gemini.poll_batch("batches/123", ["file-a", "file-b"], TAGS, "gm-test")

    assert result.done is True
    assert result.error is None
    assert result.results["file-a"] == [70, 30]
    assert result.results["file-b"] is None  # entry had no candidates -> caller falls back per-file
    assert result.usage.tokens_in == 100
    assert result.usage.tokens_out == 6


def test_gemini_poll_batch_reports_operation_error(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, **k: FakeJsonResponse({"done": True, "error": {"message": "boom"}}))
    result = gemini.poll_batch("batches/123", ["file-a"], TAGS, "gm-test")
    assert result.done is True
    assert result.error is not None


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
    provider_entries.create_entry(
        engine,
        {"provider_type": "gemini", "display_name": "gemini", "enabled": True, "api_key": "gm-test", "batch_enabled": True},
    )
    tagging_settings.update_settings(engine, {"top_tag_count": 2})
    return file_a, file_b


@pytest.fixture(autouse=False)
def stub_build_images(monkeypatch):
    monkeypatch.setattr(
        tagging, "build_tagging_images", lambda video_path, count, combine, resolution=None: [FAKE_IMAGE]
    )


def _run_directory_tag_job(engine):
    job = service.create_job(engine, "tag", "source", None, {"path": ""})
    service.start_job(engine, job["id"])
    return tag_job.run_tag_job(engine, job)


def test_directory_batch_tagging_all_succeed(engine, source, two_files, stub_build_images, monkeypatch):
    file_a, file_b = two_files

    monkeypatch.setattr(registry, "create_batch_with_entry", lambda engine_, entry, items, tags: "ext-batch-1")
    monkeypatch.setattr(
        registry, "poll_batch_with_entry",
        lambda engine_, entry, external_id, ordered_keys, tags, **_kwargs: BatchPollResult(
            done=True, results={file_a: [90, 10], file_b: [10, 90]}, usage=UsageInfo()
        ),
    )
    called_fallback = []
    monkeypatch.setattr(
        registry,
        "score_tags_with_fallback",
        lambda engine_, entries, images, tags, dead, **_kwargs: (called_fallback.append(1), ([0, 0], entries[0]))[1],
    )

    status, message = _run_directory_tag_job(engine)

    assert status == "completed"
    assert "2 of 2" in message
    assert not called_fallback  # batch resolved everything; no per-file fallback needed

    with engine.connect() as conn:
        tagged_count = conn.execute(
            text("SELECT COUNT(*) FROM files WHERE tagged_at IS NOT NULL")
        ).scalar()
    assert tagged_count == 2
    assert batch_submissions.list_active(engine) == []  # resolved submissions aren't "active" anymore


def test_directory_batch_tagging_logs_provider_and_model_used(engine, source, two_files, stub_build_images, monkeypatch):
    """User request -- same as the per-file path, batch-resolved tag scores
    should also be logged with the provider/model that produced them."""
    file_a, file_b = two_files

    monkeypatch.setattr(registry, "create_batch_with_entry", lambda engine_, entry, items, tags: "ext-batch-1")
    monkeypatch.setattr(
        registry, "poll_batch_with_entry",
        lambda engine_, entry, external_id, ordered_keys, tags, **_kwargs: BatchPollResult(
            done=True, results={file_a: [90, 10], file_b: [10, 90]}, usage=UsageInfo()
        ),
    )

    status, _message = _run_directory_tag_job(engine)
    assert status == "completed"

    with engine.connect() as conn:
        events = conn.execute(
            text("SELECT message FROM app_events WHERE event_type = 'job_item_tags'")
        ).all()

    assert len(events) == 2
    assert all("via gemini/" in event.message for event in events)


def test_directory_batch_tagging_partial_fallback(engine, source, two_files, stub_build_images, monkeypatch):
    file_a, file_b = two_files

    monkeypatch.setattr(registry, "create_batch_with_entry", lambda engine_, entry, items, tags: "ext-batch-1")
    monkeypatch.setattr(
        registry, "poll_batch_with_entry",
        lambda engine_, entry, external_id, ordered_keys, tags, **_kwargs: BatchPollResult(
            done=True, results={file_a: [90, 10], file_b: None}, usage=UsageInfo()
        ),
    )
    fallback_calls = []

    def fake_fallback(engine_, entries, images, tags, dead_entry_ids, **_kwargs):
        fallback_calls.append(1)
        return [20, 80], entries[0]

    monkeypatch.setattr(registry, "score_tags_with_fallback", fake_fallback)

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
    def fake_create(engine_, entry, items, tags):
        raise ProviderError("batch endpoint unavailable")

    monkeypatch.setattr(registry, "create_batch_with_entry", fake_create)
    fallback_calls = []

    def fake_fallback(engine_, entries, images, tags, dead_entry_ids, **_kwargs):
        fallback_calls.append(1)
        return [50, 50], entries[0]

    monkeypatch.setattr(registry, "score_tags_with_fallback", fake_fallback)

    status, message = _run_directory_tag_job(engine)

    assert status == "completed"
    assert "2 of 2" in message
    assert len(fallback_calls) == 2  # both files fell back to per-file scoring
    assert batch_submissions.list_active(engine) == []  # submission never even got persisted


def test_directory_batch_poll_failure_falls_back_for_all(engine, source, two_files, stub_build_images, monkeypatch):
    """Unlike a submission failure, a batch that was *accepted* by the
    provider but resolves with an error (rate limit, malformed job, ...)
    still needs the per-file fallback for every file it covered."""
    monkeypatch.setattr(registry, "create_batch_with_entry", lambda engine_, entry, items, tags: "ext-batch-1")
    monkeypatch.setattr(
        registry, "poll_batch_with_entry",
        lambda engine_, entry, external_id, ordered_keys, tags, **_kwargs: BatchPollResult(
            done=True, error="rate limited"
        ),
    )
    fallback_calls = []

    def fake_fallback(engine_, entries, images, tags, dead_entry_ids, **_kwargs):
        fallback_calls.append(1)
        return [50, 50], entries[0]

    monkeypatch.setattr(registry, "score_tags_with_fallback", fake_fallback)

    status, message = _run_directory_tag_job(engine)

    assert status == "completed"
    assert len(fallback_calls) == 2
    with engine.connect() as conn:
        resolved = conn.execute(text("SELECT status FROM batch_submissions")).scalar()
    assert resolved == batch_submissions.STATUS_FAILED


def test_directory_batch_submission_failure_marks_entry_dead_before_fallback(
    engine, source, two_files, stub_build_images, monkeypatch
):
    """On a total batch submission failure, the batch entry should already be
    in `dead_entries` by the time the per-file fallback chain runs, so the
    fallback never wastes a call retrying the entry we already know is
    broken (Specification: fallback design, `app/jobs/tag_batch.py::run_batch`)."""

    def fake_create(engine_, entry, items, tags):
        raise ProviderError("batch endpoint unavailable")

    monkeypatch.setattr(registry, "create_batch_with_entry", fake_create)
    seen_dead_ids: list[set] = []

    def fake_fallback(engine_, entries, images, tags, dead_entry_ids, **_kwargs):
        seen_dead_ids.append(set(dead_entry_ids))
        return [50, 50], entries[0]

    monkeypatch.setattr(registry, "score_tags_with_fallback", fake_fallback)

    status, _message = _run_directory_tag_job(engine)

    assert status == "completed"
    batch_entry = provider_entries.list_entries(engine)[0]
    assert all(batch_entry["id"] in dead_ids for dead_ids in seen_dead_ids)


def test_per_file_fallback_tries_next_entry_after_first_fails(engine, source, monkeypatch):
    """A single-file job with two enabled entries: the first fails, the
    second succeeds -- the real (unpatched) `score_tags_with_fallback`
    should be exercised here, not a stub, to prove the fallback chain
    itself works end-to-end."""
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
    file_id = _make_file_row(engine, source["id"], dir_id, source["root"], "a.mp4")
    tags_service.create_tag(engine, {"display_name": "Beach"})
    tags_service.create_tag(engine, {"display_name": "Snow"})

    provider_entries.create_entry(
        engine, {"provider_type": "openrouter", "display_name": "broken", "enabled": True, "api_key": "or-test"}
    )
    provider_entries.create_entry(
        engine, {"provider_type": "gemini", "display_name": "working", "enabled": True, "api_key": "gm-test"}
    )

    monkeypatch.setattr(
        tagging, "build_tagging_images", lambda video_path, count, combine, resolution=None: [FAKE_IMAGE]
    )

    def fake_score(images, tags, model, api_key):
        raise ProviderError("openrouter is down")

    def fake_score_gemini(images, tags, model, api_key):
        return [10, 90], UsageInfo()

    # `registry._CLIENTS` captured `openrouter.score_tags`/`gemini.score_tags`
    # by reference at import time, so patching the provider modules'
    # attributes wouldn't reach calls made through the registry's dict --
    # patch the dict entries themselves instead.
    monkeypatch.setitem(registry._CLIENTS, "openrouter", fake_score)
    monkeypatch.setitem(registry._CLIENTS, "gemini", fake_score_gemini)

    job = service.create_job(engine, "tag", "file", file_id, {"file_id": file_id})
    service.start_job(engine, job["id"])
    status, message = tag_job.run_tag_job(engine, job)

    assert status == "completed"
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT provider_name FROM file_tags WHERE file_id = :fid LIMIT 1"), {"fid": file_id}
        ).fetchone()
    assert row.provider_name == "gemini"


# --- batch persistence: resume after a simulated restart --------------------


def test_batch_submission_persisted_before_polling_starts(engine, source, two_files, stub_build_images, monkeypatch):
    """The submission row must exist (with the real external id) as soon as
    the provider accepts the batch, before any polling happens -- that's the
    whole point (user request: survive a restart mid-poll)."""
    file_a, file_b = two_files
    poll_calls = []

    monkeypatch.setattr(registry, "create_batch_with_entry", lambda engine_, entry, items, tags: "ext-batch-1")

    def fake_poll(engine_, entry, external_id, ordered_keys, tags, **_kwargs):
        # By the time polling happens, the submission must already be on disk.
        rows = batch_submissions.list_active(engine)
        assert len(rows) == 1
        assert rows[0]["external_batch_id"] == "ext-batch-1"
        poll_calls.append(1)
        return BatchPollResult(done=True, results={file_a: [90, 10], file_b: [10, 90]}, usage=UsageInfo())

    monkeypatch.setattr(registry, "poll_batch_with_entry", fake_poll)

    status, _message = _run_directory_tag_job(engine)
    assert status == "completed"
    assert poll_calls == [1]


def test_resume_pending_batch_finishes_job_without_rescanning_directory(
    engine, source, two_files, stub_build_images, monkeypatch
):
    """Simulates the post-restart path directly: a `batch_submissions` row
    is already `polling` for a job stuck `running` (as if the process died
    mid-poll and `requeue_stalled_jobs()` put it back on the queue) --
    `run_tag_job()` must resume that submission instead of re-scanning the
    directory and creating a second batch."""
    file_a, file_b = two_files
    tag_ids = [tag["id"] for tag in tags_service.list_tags(engine, active_only=True)]
    batch_entry = provider_entries.list_entries(engine)[0]

    job = service.create_job(engine, "tag", "source", None, {"path": ""})
    service.start_job(engine, job["id"])
    service.set_job_total_items(engine, job["id"], 2)
    item_a = service.create_job_item(engine, job["id"], file_id=file_a, step_name="tag_file")
    item_b = service.create_job_item(engine, job["id"], file_id=file_b, step_name="tag_file")
    service.start_job_item(engine, item_a)
    service.start_job_item(engine, item_b)

    submission = batch_submissions.create_submission(
        engine,
        job_id=job["id"],
        provider_entry_id=batch_entry["id"],
        provider_type=batch_entry["provider_type"],
        model_name=batch_entry["vision_model"],
        external_batch_id="ext-batch-1",
        tag_ids=tag_ids,
        top_tag_count=2,
        items=[
            {"file_id": file_a, "item_id": item_a, "relative_path": "a.mp4"},
            {"file_id": file_b, "item_id": item_b, "relative_path": "b.mp4"},
        ],
    )
    assert submission["status"] == batch_submissions.STATUS_POLLING

    create_calls = []
    monkeypatch.setattr(
        registry, "create_batch_with_entry",
        lambda *a, **k: create_calls.append(1) or "should-not-be-called",
    )
    monkeypatch.setattr(
        registry, "poll_batch_with_entry",
        lambda engine_, entry, external_id, ordered_keys, tags, **_kwargs: BatchPollResult(
            done=True, results={file_a: [90, 10], file_b: [10, 90]}, usage=UsageInfo()
        ),
    )

    job = service.get_job(engine, job["id"])
    status, message = tag_job.run_tag_job(engine, job)

    assert status == "completed"
    assert "2 of 2" in message
    assert not create_calls  # a fresh batch was never submitted -- the pending one was resumed
    assert batch_submissions.get_submission(engine, submission["id"])["status"] == batch_submissions.STATUS_SUCCEEDED
    with engine.connect() as conn:
        tagged_count = conn.execute(text("SELECT COUNT(*) FROM files WHERE tagged_at IS NOT NULL")).scalar()
    assert tagged_count == 2


def test_forgotten_submission_falls_back_to_per_file_tagging(
    engine, source, two_files, stub_build_images, monkeypatch
):
    """"Forget locally" (user request -- no provider-side cancel) marks the
    submission `forgotten`; the next poll must notice that and treat it like
    any other batch failure, falling back per-file rather than cancelling
    the whole job."""
    file_a, file_b = two_files
    tag_ids = [tag["id"] for tag in tags_service.list_tags(engine, active_only=True)]
    batch_entry = provider_entries.list_entries(engine)[0]

    job = service.create_job(engine, "tag", "source", None, {"path": ""})
    service.start_job(engine, job["id"])
    service.set_job_total_items(engine, job["id"], 2)
    item_a = service.create_job_item(engine, job["id"], file_id=file_a, step_name="tag_file")
    item_b = service.create_job_item(engine, job["id"], file_id=file_b, step_name="tag_file")
    service.start_job_item(engine, item_a)
    service.start_job_item(engine, item_b)

    submission = batch_submissions.create_submission(
        engine,
        job_id=job["id"],
        provider_entry_id=batch_entry["id"],
        provider_type=batch_entry["provider_type"],
        model_name=batch_entry["vision_model"],
        external_batch_id="ext-batch-1",
        tag_ids=tag_ids,
        top_tag_count=2,
        items=[
            {"file_id": file_a, "item_id": item_a, "relative_path": "a.mp4"},
            {"file_id": file_b, "item_id": item_b, "relative_path": "b.mp4"},
        ],
    )
    assert batch_submissions.forget(engine, submission["id"]) is True

    fallback_calls = []

    def fake_fallback(engine_, entries, images, tags, dead_entry_ids, **_kwargs):
        fallback_calls.append(1)
        return [50, 50], entries[0]

    monkeypatch.setattr(registry, "score_tags_with_fallback", fake_fallback)

    job = service.get_job(engine, job["id"])
    status, message = tag_job.run_tag_job(engine, job)

    assert status == "completed"
    assert len(fallback_calls) == 2
    assert "2 of 2" in message
