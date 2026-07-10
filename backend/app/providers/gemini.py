"""Google Gemini vision scoring (Tech Stack: "Vision scoring; batch API
support").

`submit_batch()` (Specification §12.3, Stage 9) uses Gemini's Batch API in
its "inlined requests" mode: every request is embedded directly in the batch
creation call (no separate file upload step, appropriate for the small
per-tagging-job batch sizes this app produces), submitted as a long-running
`batches/{id}` operation that's polled until `done`. Result-to-file
correlation relies on the inlined responses coming back in the same order
the requests were submitted in, since the `metadata.key` field is not
guaranteed to be echoed back per-response in this mode. Like
`app/providers/mistral.py`'s batch support, this has been built against the
publicly documented API shape but **not verified against a real batch job**
in this environment; a submission failure is caught by the caller
(`app/jobs/tag.py`) and falls back to `score_tags()` per file.
"""

from __future__ import annotations

import httpx

from app.providers.base import ProviderError, build_prompt, encode_image_base64, parse_scores

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


def score_tags(images: list[bytes], tags: list[str], model: str | None, api_key: str) -> list[int]:
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

    return parse_scores(text_reply, len(tags))


def submit_batch(
    items: list[tuple[str, list[bytes]]], tags: list[str], model: str | None, api_key: str
) -> str:
    """Scores every `(key, images)` pair in `items` in a single Gemini Batch
    API job (inlined-requests mode).  It returns immediately with the durable
    operation name; `poll_batch()` owns later status/result retrieval."""
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

def poll_batch(external_id: str, items: list[str], tags: list[str], model: str | None, api_key: str) -> tuple[bool, dict[str, list[int] | None]]:
    """Returns `(done, results)`.  Pending operations make no result claim."""
    try:
        poll = httpx.get(BATCH_POLL_URL_TEMPLATE.format(name=external_id), params={"key": api_key}, timeout=TIMEOUT_SECONDS)
        poll.raise_for_status()
        poll_data = poll.json()
    except httpx.HTTPError as exc:
        raise ProviderError(f"Gemini batch poll failed: {exc}") from exc
    if not poll_data.get("done"):
        return False, {}
    if "error" in poll_data:
        raise ProviderError(f"Gemini batch job failed: {poll_data['error']}")
    try:
        inlined_responses = poll_data["response"]["inlinedResponses"]["inlinedResponses"]
    except (KeyError, TypeError) as exc:
        raise ProviderError(f"Unexpected Gemini batch response shape: {exc}") from exc
    results: dict[str, list[int] | None] = {}
    for key, entry in zip(items, inlined_responses):
        try:
            text_reply = entry["response"]["candidates"][0]["content"]["parts"][0]["text"]
            results[key] = parse_scores(text_reply, len(tags))
        except (KeyError, IndexError, TypeError, ProviderError):
            results[key] = None
    return True, results
