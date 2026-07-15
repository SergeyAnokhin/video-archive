"""Mistral (Pixtral) vision scoring (Tech Stack: "Vision scoring; batch API
support"). Mistral's chat completions endpoint is OpenAI-compatible, same
request shape as `app/providers/openrouter.py`.

Batch tagging (Specification §12.3 "Gemini-style and Mistral-style batch
flows should be supported when available", Stage 9) uses Mistral's Batch
API, which mirrors OpenAI's file-based batch pattern: upload a JSONL of
per-request bodies keyed by `custom_id` (here, the video-archive file id),
then create a batch job against that input file. `create_batch()` only does
that much and returns the job id; `poll_batch()` is a single status check
(downloading and parsing the JSONL output once the job reports success),
called independently and repeatedly by the caller (`app/jobs/tag.py`, every
30s -- user request "the batch task should survive a service restart")
rather than this module blocking in its own retry loop, so the job id can
be persisted (`app/batch_submissions.py`) before any waiting starts. This
has been built against the publicly documented Mistral Batch API shape but
has **not been exercised against the real endpoint** in this environment
(no live batch job was run during development, only mocked HTTP calls in
tests) -- same "best-effort, verify before relying on it in production"
caveat this codebase already carries for `app/providers/fal.py`. A batch
submission failure is caught by the caller and falls back to the per-file
synchronous path below, so a wrong assumption here degrades gracefully
instead of failing the whole tagging job.
"""

from __future__ import annotations

import json

import httpx

from app.providers.base import BatchPollResult, ProviderError, UsageInfo, build_prompt, encode_image_base64, parse_scores

API_URL = "https://api.mistral.ai/v1/chat/completions"
FILES_URL = "https://api.mistral.ai/v1/files"
BATCH_JOBS_URL = "https://api.mistral.ai/v1/batch/jobs"
MODELS_URL = "https://api.mistral.ai/v1/models"
DEFAULT_MODEL = "pixtral-12b-2409"
TIMEOUT_SECONDS = 60
SUPPORTS_BATCH = True
_DONE_STATUSES = {"SUCCESS", "FAILED", "TIMEOUT_EXCEEDED", "CANCELLED", "CANCELLATION_REQUESTED"}


def list_models(api_key: str) -> list[str]:
    """Lists models available to this Mistral account, for the
    provider-entry "Load models" flow."""
    try:
        response = httpx.get(MODELS_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        models = response.json()["data"]
    except httpx.HTTPError as exc:
        raise ProviderError(f"Mistral model list request failed: {exc}") from exc
    except (KeyError, TypeError) as exc:
        raise ProviderError(f"Unexpected Mistral model list response shape: {exc}") from exc

    return sorted(m["id"] for m in models)


def _usage_from_response(usage: dict | None) -> UsageInfo:
    if not usage:
        return UsageInfo()
    return UsageInfo(tokens_in=usage.get("prompt_tokens"), tokens_out=usage.get("completion_tokens"))


def score_tags(
    images: list[bytes], tags: list[str], model: str | None, api_key: str, *, timeout: float | None = None
) -> tuple[list[int], UsageInfo]:
    prompt = build_prompt(tags)
    content = [{"type": "text", "text": prompt}]
    for image_bytes in images:
        content.append(
            {
                "type": "image_url",
                "image_url": f"data:image/jpeg;base64,{encode_image_base64(image_bytes)}",
            }
        )

    try:
        response = httpx.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model or DEFAULT_MODEL, "messages": [{"role": "user", "content": content}]},
            timeout=timeout or TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        text_reply = data["choices"][0]["message"]["content"]
    except httpx.HTTPError as exc:
        raise ProviderError(f"Mistral request failed: {exc}") from exc
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"Unexpected Mistral response shape: {exc}") from exc

    usage_info = _usage_from_response(data.get("usage"))
    usage_info.raw_text = text_reply
    usage_info.raw_full_response = data
    return parse_scores(text_reply, len(tags)), usage_info


def _build_batch_request_line(key: str, images: list[bytes], prompt: str, model: str | None) -> str:
    content = [{"type": "text", "text": prompt}]
    for image_bytes in images:
        content.append(
            {"type": "image_url", "image_url": f"data:image/jpeg;base64,{encode_image_base64(image_bytes)}"}
        )
    return json.dumps(
        {
            "custom_id": key,
            "body": {"model": model or DEFAULT_MODEL, "messages": [{"role": "user", "content": content}]},
        }
    )


def create_batch(items: list[tuple[str, list[bytes]]], tags: list[str], model: str | None, api_key: str) -> str:
    """Uploads a JSONL of every `(key, images)` pair in `items`, keyed by
    `key` (the caller's file id) via the JSONL `custom_id` field, and
    creates a batch job against it. Returns the job id -- does not wait for
    completion; poll it later with `poll_batch()`."""
    prompt = build_prompt(tags)
    auth_headers = {"Authorization": f"Bearer {api_key}"}
    jsonl_body = ("\n".join(_build_batch_request_line(key, images, prompt, model) for key, images in items) + "\n")

    try:
        upload = httpx.post(
            FILES_URL,
            headers=auth_headers,
            files={"file": ("tagging_batch_input.jsonl", jsonl_body.encode("utf-8"), "application/jsonl")},
            data={"purpose": "batch"},
            timeout=TIMEOUT_SECONDS,
        )
        upload.raise_for_status()
        input_file_id = upload.json()["id"]

        create = httpx.post(
            BATCH_JOBS_URL,
            headers={**auth_headers, "Content-Type": "application/json"},
            json={"input_files": [input_file_id], "endpoint": "/v1/chat/completions", "model": model or DEFAULT_MODEL},
            timeout=TIMEOUT_SECONDS,
        )
        create.raise_for_status()
        return create.json()["id"]
    except httpx.HTTPError as exc:
        raise ProviderError(f"Mistral batch request failed: {exc}") from exc
    except (KeyError, TypeError) as exc:
        raise ProviderError(f"Unexpected Mistral batch response shape: {exc}") from exc


def poll_batch(external_batch_id: str, tags: list[str], api_key: str) -> BatchPollResult:
    """One status check of a batch job `create_batch()` already created."""
    auth_headers = {"Authorization": f"Bearer {api_key}"}
    try:
        status_resp = httpx.get(f"{BATCH_JOBS_URL}/{external_batch_id}", headers=auth_headers, timeout=TIMEOUT_SECONDS)
        status_resp.raise_for_status()
        status_data = status_resp.json()
    except httpx.HTTPError as exc:
        raise ProviderError(f"Mistral batch poll failed: {exc}") from exc

    status = status_data.get("status")
    if status not in _DONE_STATUSES:
        return BatchPollResult(done=False)
    if status != "SUCCESS":
        return BatchPollResult(done=True, error=f"Mistral batch job ended with status: {status}")

    output_file_id = status_data.get("output_file")
    if not output_file_id:
        return BatchPollResult(done=True, error="Mistral batch job succeeded but returned no output file.")

    try:
        content_resp = httpx.get(
            f"{FILES_URL}/{output_file_id}/content", headers=auth_headers, timeout=TIMEOUT_SECONDS
        )
        content_resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise ProviderError(f"Mistral batch output download failed: {exc}") from exc

    results: dict[str, list[int] | None] = {}
    raw_texts: dict[str, str] = {}
    tokens_in_total = 0
    tokens_out_total = 0
    saw_usage = False
    for line in content_resp.text.splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        key = record.get("custom_id")
        if key is None:
            continue
        body = record.get("response", {}).get("body", {})
        try:
            text_reply = body["choices"][0]["message"]["content"]
            raw_texts[key] = text_reply
            results[key] = parse_scores(text_reply, len(tags))
        except (KeyError, IndexError, TypeError, ProviderError):
            results[key] = None
        usage = body.get("usage")
        if usage:
            saw_usage = True
            tokens_in_total += usage.get("prompt_tokens") or 0
            tokens_out_total += usage.get("completion_tokens") or 0

    usage_info = UsageInfo(tokens_in_total, tokens_out_total) if saw_usage else UsageInfo()
    return BatchPollResult(done=True, results=results, usage=usage_info, raw_texts=raw_texts)
