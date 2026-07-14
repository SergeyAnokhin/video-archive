"""Tag Lab domain logic (user request): a synchronous, single-file
alternative to the `tag` job for comparing AI providers/models. Unlike
`jobs/tag.py`'s `_tag_one_file()` (which tries every enabled provider entry
in priority order until one succeeds and writes the result immediately),
`run_tag_lab()` calls exactly the one provider entry the caller picked --
no fallback chain, no batch API, nothing written -- and returns everything
the review UI needs (the images sent, the prompt, the raw model reply,
usage/cost, and every vocabulary tag ranked by score) so the caller can
review/edit the suggestion before choosing to `apply_tag_lab_result()` it.

Domain logic extracted into its own module (routers stay thin, architecture
convention) rather than folded into `routers/tag_lab.py` directly.
"""

from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image
from sqlalchemy import text

from app import provider_entries, provider_usage, tagging, tagging_settings
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


def run_tag_lab(engine, file_id: str, provider_entry_id: str) -> dict:
    with engine.connect() as conn:
        row = _file_with_active_source(conn, file_id)
    if row is None:
        raise TagLabError("file_not_found", f"File not found: {file_id}")

    entry = provider_entries.get_entry(engine, provider_entry_id)
    if entry is None:
        raise TagLabError("provider_entry_not_found", f"Unknown provider entry: {provider_entry_id}")

    vocabulary = tags_service.list_tags(engine, active_only=True)
    if not vocabulary:
        raise TagLabError("empty_tag_vocabulary", "Add at least one active tag in settings before tagging.")

    access = get_source_access(row)
    if not access.exists(row.relative_path):
        raise TagLabError("source_file_missing", "Source file no longer exists on the source.")

    settings = tagging_settings.get_settings(engine)
    is_video = bool(row.is_video_supported)
    try:
        with access.local_copy(row.relative_path) as local_path:
            images = tagging.build_tagging_images_for_file(
                local_path, is_video,
                settings["sample_frame_count"], settings["combine_into_collage"], settings["image_resolution"],
            )
    except tagging.TaggingInputError as exc:
        raise TagLabError("tag_lab_failed", str(exc)) from exc

    display_names = [tag["display_name"] for tag in vocabulary]
    prompt = build_prompt(display_names)

    try:
        scores, usage = registry.score_tags_with_entry(engine, entry, images, display_names)
    except registry.ProviderNotConfiguredError as exc:
        raise TagLabError("provider_not_configured", str(exc)) from exc
    except ProviderError as exc:
        raise TagLabError("tag_lab_failed", str(exc)) from exc

    ranked = sorted(zip(vocabulary, scores), key=lambda pair: pair[1], reverse=True)
    tags_out = [{"tag_id": tag["id"], "display_name": tag["display_name"], "score": score} for tag, score in ranked]

    images_out = []
    for image_bytes in images:
        width, height = Image.open(BytesIO(image_bytes)).size
        data_url = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")
        images_out.append({"data_url": data_url, "width": width, "height": height})

    return {
        "images": images_out,
        "prompt": prompt,
        "raw_response": usage.raw_text,
        "tokens_in": usage.tokens_in,
        "tokens_out": usage.tokens_out,
        "estimated_cost_usd": provider_usage.estimate_cost_usd(entry["vision_model"], usage.tokens_in, usage.tokens_out),
        "provider_type": entry["provider_type"],
        "model_name": entry["vision_model"],
        "tags": tags_out,
    }


def apply_tag_lab_result(
    engine, file_id: str, tags: list[dict], provider_type: str, model_name: str | None
) -> None:
    """`tags`: each item is either `{"tag_id": str, "score": int}` (a tag
    Tag Lab's model run suggested, kept in the review list) or
    `{"display_name": str}` (typed fresh by the user during review). Model-
    sourced entries are recorded under `provider_type`/`model_name` with
    their real score; user-typed ones use the same `provider_name='manual',
    score=100` convention `tags.assign_file_tag()` already uses for a
    hand-picked tag."""
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
