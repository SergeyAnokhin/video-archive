"""Google Gemini vision scoring (Tech Stack: "Vision scoring; batch API
support").

Batch tagging (Specification §12.3, Stage 9) uses Gemini's Batch API in its
"inlined requests" mode: every request is embedded directly in the batch
creation call (no separate file upload step, appropriate for the small
per-tagging-job batch sizes this app produces), submitted as a long-running
`batches/{id}` operation. `create_batch()` only submits and returns that
operation name; `poll_batch()` is a single status check, called
independently and repeatedly by the caller (`app/jobs/tag.py`, every 30s --
user request "the batch task should survive a service restart") rather than
this module blocking in its own retry loop, so the operation name can be
persisted (`app/batch_submissions.py`) before any waiting starts and a
process restart mid-wait doesn't lose track of it. Result-to-file
correlation relies on the inlined responses coming back in the same order
the requests were submitted in, since the `metadata.key` field is not
guaranteed to be echoed back per-response in this mode -- `poll_batch()`
takes the same `ordered_keys` list the batch was created with. Like
`app/providers/mistral.py`'s batch support, this has been built against the
publicly documented API shape but **not verified against a real batch job**
in this environment; a submission failure is caught by the caller and falls
back to `score_tags()` per file.
"""

from __future__ import annotations

import httpx

from app.providers.base import BatchPollResult, ProviderError, UsageInfo, build_prompt, encode_image_base64, parse_scores

API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
BATCH_CREATE_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:batchGenerateContent"
BATCH_POLL_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/{name}"
MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.5-flash"
TIMEOUT_SECONDS = 60
SUPPORTS_BATCH = True


def list_models(api_key: str) -> list[str]:
    """Lists Gemini models that support `generateContent` (i.e. can score
    tags), for the provider-entry "Load models" flow."""
    try:
        response = httpx.get(MODELS_URL, params={"key": api_key}, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        models = response.json()["models"]
    except httpx.HTTPError as exc:
        raise ProviderError(f"Gemini model list request failed: {exc}") from exc
    except (KeyError, TypeError) as exc:
        raise ProviderError(f"Unexpected Gemini model list response shape: {exc}") from exc

    names = [
        m["name"].removeprefix("models/")
        for m in models
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]
    return sorted(names)


def _usage_from_metadata(usage_metadata: dict | None) -> UsageInfo:
    if not usage_metadata:
        return UsageInfo()
    return UsageInfo(
        tokens_in=usage_metadata.get("promptTokenCount"),
        tokens_out=usage_metadata.get("candidatesTokenCount"),
    )


def score_tags(images: list[bytes], tags: list[str], model: str | None, api_key: str) -> tuple[list[int], UsageInfo]:
    prompt = build_prompt(tags)
    parts = [{"text": prompt}]
    for image_bytes in images:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": encode_image_base64(image_bytes)}})

    url = API_URL_TEMPLATE.format(model=model or DEFAULT_MODEL)
    try:
        response = httpx.post(
            url,
            params={"key": api_key},
            json={"contents": [{"parts": parts}]},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        text_reply = data["candidates"][0]["content"]["parts"][0]["text"]
    except httpx.HTTPError as exc:
        raise ProviderError(f"Gemini request failed: {exc}") from exc
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"Unexpected Gemini response shape: {exc}") from exc

    usage_info = _usage_from_metadata(data.get("usageMetadata"))
    usage_info.raw_text = text_reply
    return parse_scores(text_reply, len(tags)), usage_info


def create_batch(items: list[tuple[str, list[bytes]]], tags: list[str], model: str | None, api_key: str) -> str:
    """Submits every `(key, images)` pair in `items` as one Gemini Batch API
    job (inlined-requests mode). Returns the operation name -- does not wait
    for completion; poll it later with `poll_batch()`."""
    prompt = build_prompt(tags)
    inline_requests = []
    for key, images in items:
        parts = [{"text": prompt}]
        for image_bytes in images:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": encode_image_base64(image_bytes)}})
        inline_requests.append({"request": {"contents": [{"parts": parts}]}, "metadata": {"key": key}})

    resolved_model = model or DEFAULT_MODEL
    create_url = BATCH_CREATE_URL_TEMPLATE.format(model=resolved_model)
    try:
        create = httpx.post(
            create_url,
            params={"key": api_key},
            json={
                "batch": {
                    "display_name": "video-archive-tagging",
                    "input_config": {"requests": {"requests": inline_requests}},
                }
            },
            timeout=TIMEOUT_SECONDS,
        )
        create.raise_for_status()
        return create.json()["name"]
    except httpx.HTTPError as exc:
        raise ProviderError(f"Gemini batch request failed: {exc}") from exc
    except (KeyError, TypeError) as exc:
        raise ProviderError(f"Unexpected Gemini batch response shape: {exc}") from exc


def poll_batch(external_batch_id: str, ordered_keys: list[str], tags: list[str], api_key: str) -> BatchPollResult:
    """One status check of a batch `create_batch()` already submitted.
    `ordered_keys` must be the same `key` order the batch was created with
    (see module docstring on correlation-by-order)."""
    try:
        poll = httpx.get(
            BATCH_POLL_URL_TEMPLATE.format(name=external_batch_id),
            params={"key": api_key},
            timeout=TIMEOUT_SECONDS,
        )
        poll.raise_for_status()
        poll_data = poll.json()
    except httpx.HTTPError as exc:
        raise ProviderError(f"Gemini batch poll failed: {exc}") from exc

    if not poll_data.get("done"):
        return BatchPollResult(done=False)

    if "error" in poll_data:
        return BatchPollResult(done=True, error=str(poll_data["error"]))

    try:
        inlined_responses = poll_data["response"]["inlinedResponses"]["inlinedResponses"]
    except (KeyError, TypeError) as exc:
        return BatchPollResult(done=True, error=f"Unexpected Gemini batch response shape: {exc}")

    results: dict[str, list[int] | None] = {}
    raw_texts: dict[str, str] = {}
    tokens_in_total = 0
    tokens_out_total = 0
    saw_usage = False
    for key, entry in zip(ordered_keys, inlined_responses):
        try:
            text_reply = entry["response"]["candidates"][0]["content"]["parts"][0]["text"]
            raw_texts[key] = text_reply
            results[key] = parse_scores(text_reply, len(tags))
        except (KeyError, IndexError, TypeError, ProviderError):
            results[key] = None
        usage = entry.get("response", {}).get("usageMetadata")
        if usage:
            saw_usage = True
            tokens_in_total += usage.get("promptTokenCount") or 0
            tokens_out_total += usage.get("candidatesTokenCount") or 0

    usage_info = UsageInfo(tokens_in_total, tokens_out_total) if saw_usage else UsageInfo()
    return BatchPollResult(done=True, results=results, usage=usage_info, raw_texts=raw_texts)
