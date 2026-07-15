"""Tag Lab domain logic (user request): a synchronous, single-file
alternative to the `tag` job for comparing AI providers/models. Unlike
`jobs/tag.py`'s `_tag_one_file()` (which tries every enabled provider entry
in priority order until one succeeds and writes the result immediately),
`run_tag_lab()` calls exactly the one provider entry the caller picked --
no fallback chain, no batch API, nothing written -- and returns everything
the review UI needs (the images sent, the prompt, the raw model reply,
usage/cost, and every vocabulary tag ranked by score) so the caller can
review/edit the suggestion before choosing to `apply_tag_lab_result()` it.
`prepare_tag_lab()` exposes just the images/prompt half of that (user
request -- show what's about to be sent before waiting on the model), and
both share `_image_cache`'s reuse of the last sampled images for a file
(user request -- switching providers on the same video shouldn't re-sample
it every time).

Domain logic extracted into its own module (routers stay thin, architecture
convention) rather than folded into `routers/tag_lab.py` directly.
"""

from __future__ import annotations

import base64
import uuid
from io import BytesIO

from PIL import Image
from sqlalchemy import text

from app import provider_entries, provider_usage, tag_lab_feedback, tagging, tagging_settings
from app import tags as tags_service
from app.providers import registry
from app.providers.base import ProviderError, build_prompt
from app.sources import get_source_access


class TagLabError(Exception):
    """A Tag Lab run/apply cannot proceed. `code` matches the API error
    code (`file_not_found`, `source_file_missing`, `provider_entry_not_found`,
    `empty_tag_vocabulary`, `provider_not_configured`, `tag_lab_failed`) --
    the router maps it to an HTTP status, same convention as
    `file_ops.FileOperationError`."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


# In-process cache of the last images/prompt built for each file (user
# request -- re-running Tag Lab against the same video, e.g. to compare
# providers, shouldn't re-sample frames from it every time). Keyed by
# file_id, holding only the most recent generation for that file -- a
# fresh run whose tagging settings or vocabulary differ invalidates it.
# Deliberately in-memory only (lost on backend restart), same tradeoff as
# `preview_cache.py`'s on-disk cache but scoped to one process's lifetime.
_image_cache: dict[str, dict] = {}


def _image_cache_signature(settings: dict, is_video: bool, display_names: list[str]) -> tuple:
    return (
        settings["sample_frame_count"],
        settings["combine_into_collage"],
        settings["image_resolution"],
        is_video,
        tuple(display_names),
    )


def _file_with_active_source(conn, file_id: str):
    # f.id is deliberately excluded from the select list: s.* also carries an
    # `id` column (the source's) -- same avoidance as file_ops.py's
    # _file_with_source_lookup().
    return conn.execute(
        text(
            """
            SELECT f.relative_path, f.is_video_supported, s.*
            FROM files f
            JOIN sources s ON s.id = f.source_id
            WHERE f.id = :id AND s.is_active = 1
            """
        ),
        {"id": file_id},
    ).fetchone()


def _file_row(engine, file_id: str):
    with engine.connect() as conn:
        row = _file_with_active_source(conn, file_id)
    if row is None:
        raise TagLabError("file_not_found", f"File not found: {file_id}")
    return row


def _images_and_prompt(engine, file_id: str, row) -> tuple[list[bytes], str, list[dict], list[dict], dict]:
    """Resolves the tag vocabulary and builds (or reuses from `_image_cache`)
    the sampled/collage images for `row`. Returns `(images, prompt,
    images_out, vocabulary, settings)` -- `images` as raw bytes for the
    provider call, `images_out` as the base64 data-url shape the API
    returns."""
    vocabulary = tags_service.list_tags(engine, active_only=True)
    if not vocabulary:
        raise TagLabError("empty_tag_vocabulary", "Add at least one active tag in settings before tagging.")

    access = get_source_access(row)
    if not access.exists(row.relative_path):
        raise TagLabError("source_file_missing", "Source file no longer exists on the source.")

    settings = tagging_settings.get_settings(engine)
    is_video = bool(row.is_video_supported)
    display_names = [tag["display_name"] for tag in vocabulary]
    signature = _image_cache_signature(settings, is_video, display_names)

    cached = _image_cache.get(file_id)
    if cached is not None and cached["signature"] == signature:
        images = cached["images"]
    else:
        try:
            with access.local_copy(row.relative_path) as local_path:
                images = tagging.build_tagging_images_for_file(
                    local_path, is_video,
                    settings["sample_frame_count"], settings["combine_into_collage"], settings["image_resolution"],
                )
        except tagging.TaggingInputError as exc:
            raise TagLabError("tag_lab_failed", str(exc)) from exc
        _image_cache[file_id] = {"signature": signature, "images": images}

    prompt = build_prompt(display_names)

    images_out = []
    for image_bytes in images:
        width, height = Image.open(BytesIO(image_bytes)).size
        data_url = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")
        images_out.append({"data_url": data_url, "width": width, "height": height})

    return images, prompt, images_out, vocabulary, settings


def prepare_tag_lab(engine, file_id: str) -> dict:
    """Builds (or reuses) just the images + prompt a Tag Lab run would send,
    without calling any provider -- lets the review UI show what's about to
    be sent while the (potentially slow) model call is still in flight."""
    row = _file_row(engine, file_id)
    _images, prompt, images_out, _vocabulary, _settings = _images_and_prompt(engine, file_id, row)
    return {"images": images_out, "prompt": prompt}


def run_tag_lab(engine, file_id: str, provider_entry_id: str) -> dict:
    row = _file_row(engine, file_id)

    entry = provider_entries.get_entry(engine, provider_entry_id)
    if entry is None:
        raise TagLabError("provider_entry_not_found", f"Unknown provider entry: {provider_entry_id}")

    images, prompt, images_out, vocabulary, settings = _images_and_prompt(engine, file_id, row)
    display_names = [tag["display_name"] for tag in vocabulary]

    try:
        scores, usage = registry.score_tags_with_entry(
            engine, entry, images, display_names, timeout=settings["request_timeout_seconds"]
        )
    except registry.ProviderNotConfiguredError as exc:
        raise TagLabError("provider_not_configured", str(exc)) from exc
    except ProviderError as exc:
        raise TagLabError("tag_lab_failed", str(exc)) from exc

    ranked = sorted(zip(vocabulary, scores), key=lambda pair: pair[1], reverse=True)
    tags_out = [{"tag_id": tag["id"], "display_name": tag["display_name"], "score": score} for tag, score in ranked]

    run_id = str(uuid.uuid4())
    suggested_tags = [tag for tag in tags_out if tag["score"] > 0]
    tag_lab_feedback.record_run(engine, run_id, entry["provider_type"], entry["vision_model"], file_id, suggested_tags)

    return {
        "run_id": run_id,
        "images": images_out,
        "prompt": prompt,
        "raw_response": usage.raw_text,
        "raw_full_response": usage.raw_full_response,
        "tokens_in": usage.tokens_in,
        "tokens_out": usage.tokens_out,
        "estimated_cost_usd": provider_usage.estimate_cost_usd(
            engine, entry["provider_type"], entry["vision_model"], usage.tokens_in, usage.tokens_out
        ),
        "provider_type": entry["provider_type"],
        "model_name": entry["vision_model"],
        "tags": tags_out,
    }


def apply_tag_lab_result(
    engine, file_id: str, tags: list[dict], provider_type: str, model_name: str | None, run_id: str | None = None
) -> None:
    """`tags`: each item is either `{"tag_id": str, "score": int}` (a tag
    Tag Lab's model run suggested, kept in the review list) or
    `{"display_name": str}` (typed fresh by the user during review). Model-
    sourced entries are recorded under `provider_type`/`model_name` with
    their real score; user-typed ones use the same `provider_name='manual',
    score=100` convention `tags.assign_file_tag()` already uses for a
    hand-picked tag. `run_id`, when given (the run this apply follows),
    records the apply-behavior KPI (unchanged/edited) against that run's
    suggested-tag snapshot -- omitted for an apply with no prior Tag Lab
    run to compare against."""
    with engine.connect() as conn:
        exists = conn.execute(text("SELECT 1 FROM files WHERE id = :id"), {"id": file_id}).fetchone()
    if exists is None:
        raise TagLabError("file_not_found", f"File not found: {file_id}")

    resolved = []
    for item in tags:
        tag_id = item.get("tag_id")
        if tag_id:
            resolved.append(
                {"id": tag_id, "score": item.get("score", 0), "provider_name": provider_type, "model_name": model_name}
            )
        else:
            tag = tags_service.get_or_create_tag(engine, item["display_name"])
            resolved.append({"id": tag["id"], "score": 100, "provider_name": "manual", "model_name": None})

    tags_service.replace_scored_tags(engine, file_id, resolved)

    if run_id:
        tag_lab_feedback.record_apply(engine, run_id, [entry["id"] for entry in resolved])
