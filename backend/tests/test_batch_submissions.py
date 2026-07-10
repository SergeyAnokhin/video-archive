"""Unit tests for `app/batch_submissions.py` (user request -- persisted
batch-tagging submissions that survive a service restart) and its two
router endpoints (`GET/DELETE /api/jobs/batch-submissions...`).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.db as db_module
from app import batch_submissions, provider_entries
from app.jobs import service
from app.main import app


def _make_entry(engine) -> dict:
    return provider_entries.create_entry(
        engine,
        {"provider_type": "gemini", "display_name": "gemini", "enabled": True, "api_key": "gm-test", "batch_enabled": True},
    )


def _make_job(engine) -> dict:
    job = service.create_job(engine, "tag", "source", None, {"path": ""})
    service.start_job(engine, job["id"])
    return job


def test_create_and_get_submission_roundtrip(engine):
    entry = _make_entry(engine)
    job = _make_job(engine)
    submission = batch_submissions.create_submission(
        engine,
        job_id=job["id"],
        provider_entry_id=entry["id"],
        provider_type="gemini",
        model_name="gemini-2.5-flash",
        external_batch_id="batches/123",
        tag_ids=["tag-1", "tag-2"],
        top_tag_count=5,
        items=[{"file_id": "f1", "item_id": "i1", "relative_path": "a.mp4"}],
    )

    assert submission["status"] == batch_submissions.STATUS_POLLING
    fetched = batch_submissions.get_submission(engine, submission["id"])
    assert fetched["external_batch_id"] == "batches/123"
    assert fetched["job_id"] == job["id"]


def test_get_pending_for_job_only_returns_polling_rows(engine):
    entry = _make_entry(engine)
    job = _make_job(engine)
    submission = batch_submissions.create_submission(
        engine, job_id=job["id"], provider_entry_id=entry["id"], provider_type="gemini", model_name=None,
        external_batch_id="batches/1", tag_ids=[], top_tag_count=5, items=[],
    )

    assert batch_submissions.get_pending_for_job(engine, job["id"])["id"] == submission["id"]

    batch_submissions.mark_resolved(engine, submission["id"], batch_submissions.STATUS_SUCCEEDED)
    assert batch_submissions.get_pending_for_job(engine, job["id"]) is None


def test_list_active_only_includes_polling(engine):
    entry = _make_entry(engine)
    job = _make_job(engine)
    polling = batch_submissions.create_submission(
        engine, job_id=job["id"], provider_entry_id=entry["id"], provider_type="gemini", model_name=None,
        external_batch_id="batches/1", tag_ids=[], top_tag_count=5, items=[],
    )
    resolved = batch_submissions.create_submission(
        engine, job_id=job["id"], provider_entry_id=entry["id"], provider_type="gemini", model_name=None,
        external_batch_id="batches/2", tag_ids=[], top_tag_count=5, items=[],
    )
    batch_submissions.mark_resolved(engine, resolved["id"], batch_submissions.STATUS_SUCCEEDED)

    active_ids = {row["id"] for row in batch_submissions.list_active(engine)}
    assert active_ids == {polling["id"]}


def test_forget_marks_forgotten_and_rejects_already_resolved(engine):
    entry = _make_entry(engine)
    job = _make_job(engine)
    submission = batch_submissions.create_submission(
        engine, job_id=job["id"], provider_entry_id=entry["id"], provider_type="gemini", model_name=None,
        external_batch_id="batches/1", tag_ids=[], top_tag_count=5, items=[],
    )

    assert batch_submissions.forget(engine, submission["id"]) is True
    assert batch_submissions.get_submission(engine, submission["id"])["status"] == batch_submissions.STATUS_FORGOTTEN
    # already resolved -- forgetting again is a no-op failure, not an error
    assert batch_submissions.forget(engine, submission["id"]) is False


def test_forget_unknown_id_returns_false(engine):
    assert batch_submissions.forget(engine, "does-not-exist") is False


def test_requeue_stalled_jobs_only_touches_running_jobs_with_pending_batches(engine):
    entry = _make_entry(engine)
    running_job = _make_job(engine)
    batch_submissions.create_submission(
        engine, job_id=running_job["id"], provider_entry_id=entry["id"], provider_type="gemini", model_name=None,
        external_batch_id="batches/1", tag_ids=[], top_tag_count=5, items=[],
    )

    # A second job with no batch submission at all -- must be left alone.
    other_job = _make_job(engine)

    # A third job whose submission already resolved -- must be left alone.
    resolved_job = _make_job(engine)
    resolved_submission = batch_submissions.create_submission(
        engine, job_id=resolved_job["id"], provider_entry_id=entry["id"], provider_type="gemini", model_name=None,
        external_batch_id="batches/2", tag_ids=[], top_tag_count=5, items=[],
    )
    batch_submissions.mark_resolved(engine, resolved_submission["id"], batch_submissions.STATUS_SUCCEEDED)

    requeued = batch_submissions.requeue_stalled_jobs(engine)

    assert requeued == 1
    assert service.get_job(engine, running_job["id"])["status"] == "queued"
    assert service.get_job(engine, other_job["id"])["status"] == "running"
    assert service.get_job(engine, resolved_job["id"])["status"] == "running"


def test_requeue_stalled_jobs_is_idempotent(engine):
    entry = _make_entry(engine)
    job = _make_job(engine)
    batch_submissions.create_submission(
        engine, job_id=job["id"], provider_entry_id=entry["id"], provider_type="gemini", model_name=None,
        external_batch_id="batches/1", tag_ids=[], top_tag_count=5, items=[],
    )

    assert batch_submissions.requeue_stalled_jobs(engine) == 1
    # second call: the job is 'queued' now, not 'running' -- nothing left to requeue
    assert batch_submissions.requeue_stalled_jobs(engine) == 0


# --- router ------------------------------------------------------------------


def _fresh_client(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)
    return TestClient(app)


def test_batch_submissions_router_list_and_forget(tmp_path, monkeypatch):
    with _fresh_client(tmp_path, monkeypatch) as client:
        engine = db_module.get_engine()
        entry = _make_entry(engine)
        job = _make_job(engine)
        submission = batch_submissions.create_submission(
            engine, job_id=job["id"], provider_entry_id=entry["id"], provider_type="gemini",
            model_name="gemini-2.5-flash", external_batch_id="batches/1", tag_ids=[], top_tag_count=5,
            items=[{"file_id": "f1", "item_id": "i1", "relative_path": "a.mp4"}],
        )

        res = client.get("/api/jobs/batch-submissions")
        assert res.status_code == 200
        body = res.json()
        assert len(body["submissions"]) == 1
        assert body["submissions"][0]["provider_type"] == "gemini"
        assert body["submissions"][0]["model_name"] == "gemini-2.5-flash"
        assert body["submissions"][0]["item_count"] == 1
        assert body["submissions"][0]["status"] == batch_submissions.STATUS_POLLING

        res = client.delete(f"/api/jobs/batch-submissions/{submission['id']}")
        assert res.status_code == 200
        assert res.json() == {"forgotten": True}

        res = client.get("/api/jobs/batch-submissions")
        assert res.json()["submissions"] == []


def test_batch_submissions_router_forget_unknown_id_404s(tmp_path, monkeypatch):
    with _fresh_client(tmp_path, monkeypatch) as client:
        res = client.delete("/api/jobs/batch-submissions/does-not-exist")
        assert res.status_code == 404
