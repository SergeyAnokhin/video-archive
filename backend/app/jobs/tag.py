"""`tag` job execution (Specification §12): resolves the active tag
vocabulary, tagging settings, and configured provider once at launch (same
"settings snapshot at launch time" convention as the `preview` job), then for
each video builds sampled-frame images (`app/tagging.py`), sends them to the
provider (`app/providers/registry.py`), and replaces the file's `file_tags`
with the top-N scoring tags (Data Model §9 "Re-tagging replaces the file's
previous tag set").
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app import provider_configs, tagging, tagging_settings, tags as tags_service
from app.jobs import service
from app.media import is_test_artifact
from app.providers import registry
from app.sources import SourceAccess, get_source_access


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _assign_tags(engine, file_id: str, scored_tags: list[dict], provider_name: str, model_name: str | None) -> None:
    now = _now()
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM file_tags WHERE file_id = :file_id"), {"file_id": file_id})
        for entry in scored_tags:
            conn.execute(
                text(
                    """
                    INSERT INTO file_tags (id, file_id, tag_id, score, provider_name, model_name, assigned_at)
                    VALUES (:id, :file_id, :tag_id, :score, :provider_name, :model_name, :now)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "file_id": file_id,
                    "tag_id": entry["id"],
                    "score": entry["score"],
                    "provider_name": provider_name,
                    "model_name": model_name,
                    "now": now,
                },
            )
        conn.execute(
            text("UPDATE files SET tagged_at = :now, updated_at = :now WHERE id = :id"),
            {"now": now, "id": file_id},
        )


def _tag_one_file(
    engine, access: SourceAccess, file_row, vocabulary: list[dict], settings: dict, provider_name: str, model_name: str | None
) -> str:
    if not access.exists(file_row.relative_path):
        raise RuntimeError("Source file no longer exists on the source.")

    with access.local_copy(file_row.relative_path) as video_path:
        images = tagging.build_tagging_images(
            video_path, settings["sample_frame_count"], settings["combine_into_collage"]
        )
    display_names = [tag["display_name"] for tag in vocabulary]
    scores = registry.score_tags_with_provider(engine, provider_name, images, display_names)

    ranked = sorted(zip(vocabulary, scores), key=lambda pair: pair[1], reverse=True)
    top = ranked[: settings["top_tag_count"]]
    scored_tags = [{"id": tag["id"], "score": score} for tag, score in top]

    _assign_tags(engine, file_row.id, scored_tags, provider_name, model_name)
    return f"{len(scored_tags)} tag(s) assigned"


def run_tag_job(engine, job: dict) -> tuple[str, str]:
    params = job["parameters"] or {}
    provider_name = params.get("provider_name")
    if not provider_name:
        raise RuntimeError("No tagging provider configured.")

    vocabulary = tags_service.list_tags(engine, active_only=True)
    if not vocabulary:
        raise RuntimeError("Tag vocabulary is empty; add tags in settings before tagging.")

    settings = tagging_settings.get_settings(engine)
    provider_config = provider_configs.get_provider(engine, provider_name)
    model_name = provider_config["vision_model"] if provider_config else None

    with engine.connect() as conn:
        source_row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()
    if source_row is None:
        raise RuntimeError("No active source is configured.")
    access = get_source_access(source_row)

    if job["scope_type"] == "file":
        return _run_file_scope(engine, job, access, params, vocabulary, settings, provider_name, model_name)
    return _run_directory_scope(engine, job, access, params, vocabulary, settings, provider_name, model_name)


def _run_file_scope(
    engine, job: dict, access: SourceAccess, params: dict, vocabulary: list[dict], settings: dict,
    provider_name: str, model_name: str | None,
) -> tuple[str, str]:
    file_id = params.get("file_id")
    with engine.connect() as conn:
        row = conn.execute(text("SELECT * FROM files WHERE id = :id"), {"id": file_id}).fetchone()
    if row is None:
        raise RuntimeError("File not found.")

    item_id = service.create_job_item(engine, job["id"], file_id=row.id, step_name="tag_file")
    service.start_job_item(engine, item_id)
    try:
        message = _tag_one_file(engine, access, row, vocabulary, settings, provider_name, model_name)
        service.complete_job_item(engine, item_id, output_ref=None, message=message)
        service.log_event(engine, job["id"], row.id, "info", "job_item_completed", f"Tagged {row.relative_path}: {message}")
        return "completed", message
    except Exception as exc:  # noqa: BLE001 - failure is reported through the job, not raised further
        service.fail_job_item(engine, item_id, message=str(exc))
        service.log_event(
            engine, job["id"], row.id, "error", "job_item_failed", f"Failed to tag {row.relative_path}: {exc}"
        )
        return "failed", str(exc)


def _run_directory_scope(
    engine, job: dict, access: SourceAccess, params: dict, vocabulary: list[dict], settings: dict,
    provider_name: str, model_name: str | None,
) -> tuple[str, str]:
    relative_path = params.get("path", "") or ""
    skip_processed = params.get("skip_processed", True)

    with engine.connect() as conn:
        source_id = conn.execute(text("SELECT id FROM sources WHERE is_active = 1 LIMIT 1")).fetchone().id

        clauses = ["source_id = :sid", "is_video_supported = 1"]
        query_params: dict = {"sid": source_id}
        if relative_path:
            clauses.append("(relative_path = :rel OR relative_path LIKE :prefix)")
            query_params["rel"] = relative_path
            query_params["prefix"] = f"{relative_path}/%"

        rows = conn.execute(
            text(f"SELECT * FROM files WHERE {' AND '.join(clauses)} ORDER BY relative_path"),
            query_params,
        ).all()

    candidates = [row for row in rows if not is_test_artifact(row.file_name)]

    processed = 0
    skipped = 0
    failed = 0
    total = len(candidates)
    cancelled = False

    for row in candidates:
        if service.is_cancel_requested(job["id"]):
            cancelled = True
            break

        item_id = service.create_job_item(engine, job["id"], file_id=row.id, step_name="tag_file")

        if skip_processed and row.tagged_at:
            service.skip_job_item(engine, item_id, "Already tagged; skipped.")
            service.log_event(
                engine, job["id"], row.id, "debug", "job_item_skipped", f"Skipped {row.relative_path} (already tagged)."
            )
            skipped += 1
            continue

        service.start_job_item(engine, item_id)
        try:
            message = _tag_one_file(engine, access, row, vocabulary, settings, provider_name, model_name)
            service.complete_job_item(engine, item_id, output_ref=None, message=message)
            service.log_event(engine, job["id"], row.id, "info", "job_item_completed", f"Tagged {row.relative_path}: {message}")
            processed += 1
        except Exception as exc:  # noqa: BLE001 - one file's failure must not abort the job
            failed += 1
            service.fail_job_item(engine, item_id, message=str(exc))
            service.log_event(
                engine, job["id"], row.id, "error", "job_item_failed", f"Failed to tag {row.relative_path}: {exc}"
            )

    if cancelled:
        message = f"Cancelled after {processed} of {total} file(s)."
        service.log_event(engine, job["id"], None, "info", "job_cancel_honored", message)
        return "cancelled", message

    summary = f"Tagged {processed} of {total} file(s)"
    if skipped:
        summary += f", {skipped} skipped"
    if failed:
        summary += f", {failed} failed"

    status = "failed" if failed and processed == 0 and total > 0 else "completed"
    return status, summary
