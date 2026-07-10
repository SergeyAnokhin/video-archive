"""Persisted Gemini/Mistral batch status and the 30-second poll pass."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app import model_usage, provider_entries, tags as tags_service
from app.jobs import service
from app.providers import registry


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_run(engine, job_id: str, entry: dict, external_id: str, vocabulary: list[dict], pairs: list[tuple]) -> None:
    run_id, now = str(uuid.uuid4()), _now()
    with engine.begin() as conn:
        conn.execute(text("""INSERT INTO external_batch_runs (id, job_id, provider_entry_id, provider_name, model_name, external_id, tag_ids_json, status, item_count, submitted_at)
            VALUES (:id, :job, :entry, :provider, :model, :external, :tags, 'submitted', :count, :now)"""),
            {"id": run_id, "job": job_id, "entry": entry["id"], "provider": entry["provider_type"], "model": entry["vision_model"], "external": external_id, "tags": json.dumps([tag["id"] for tag in vocabulary]), "count": len(pairs), "now": now})
        conn.execute(text("INSERT INTO external_batch_items (id, batch_run_id, file_id, job_item_id) VALUES (:id, :run, :file, :item)"),
            [{"id": str(uuid.uuid4()), "run": run_id, "file": row.id, "item": item_id} for row, item_id in pairs])
    model_usage.record(engine, entry["provider_type"], entry["vision_model"], requests=1, files=len(pairs), batches=1)


def list_active(engine) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM external_batch_runs WHERE status = 'submitted' ORDER BY submitted_at DESC")).all()
    return [dict(row._mapping) for row in rows]


def poll_pending_batches(engine) -> None:
    for run in list_active(engine):
        try:
            _poll_one(engine, run)
        except Exception as exc:
            with engine.begin() as conn:
                conn.execute(text("UPDATE external_batch_runs SET status = 'failed', completed_at = :now, error_message = :error WHERE id = :id"), {"now": _now(), "error": str(exc), "id": run["id"]})
            service.finish_job(engine, run["job_id"], "failed", f"External batch failed: {exc}")


def _poll_one(engine, run: dict) -> None:
    with engine.begin() as conn:
        conn.execute(text("UPDATE external_batch_runs SET last_polled_at = :now WHERE id = :id"), {"now": _now(), "id": run["id"]})
        rows = conn.execute(text("SELECT file_id, job_item_id FROM external_batch_items WHERE batch_run_id = :id"), {"id": run["id"]}).all()
    entry = next((item for item in provider_entries.list_entries(engine) if item["id"] == run["provider_entry_id"]), None)
    if entry is None:
        raise RuntimeError("Provider entry was deleted while its batch was running.")
    all_tags = {tag["id"]: tag for tag in tags_service.list_tags(engine, active_only=False)}
    vocabulary = [all_tags[tag_id] for tag_id in json.loads(run["tag_ids_json"]) if tag_id in all_tags]
    done, results = registry.poll_tags_batch_with_entry(engine, entry, run["external_id"], [row.file_id for row in rows], [tag["display_name"] for tag in vocabulary])
    if not done:
        return
    from app.jobs.tag import _assign_tags
    completed = 0
    for row in rows:
        scores = results.get(row.file_id)
        if scores is None:
            service.fail_job_item(engine, row.job_item_id, "Batch returned no parseable result.")
            continue
        ranked = sorted(zip(vocabulary, scores), key=lambda pair: pair[1], reverse=True)
        _assign_tags(engine, row.file_id, [{"id": tag["id"], "score": score} for tag, score in ranked[:10]], run["provider_name"], run["model_name"], execution_mode="batch", response_payload=json.dumps(scores), record_request=False)
        service.complete_job_item(engine, row.job_item_id, None, f"{min(10, len(ranked))} tag(s) assigned (batch)")
        completed += 1
    with engine.begin() as conn:
        conn.execute(text("UPDATE external_batch_runs SET status = 'completed', completed_at = :now WHERE id = :id"), {"now": _now(), "id": run["id"]})
    service.finish_job(engine, run["job_id"], "completed", f"Batch tagged {completed} of {len(rows)} file(s)")
