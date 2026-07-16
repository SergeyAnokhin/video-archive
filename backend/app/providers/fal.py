"""FAL vision scoring (Tech Stack: "Vision workloads").

Unlike the other three providers, FAL has no single fixed chat/vision API
shape shared across its model catalog — each model endpoint defines its own
request/response schema. This client dual-routes depending on the
configured model string (user request — give real model choice through FAL,
not just the one small default):

- A literal FAL app path (starts with `"fal-ai/"`, e.g.
  `"fal-ai/moondream2/visual-query"`) calls that endpoint directly via
  `fal.run/{model}` with a `prompt` + single `image_url` (data URI) payload
  — the shape small, single-purpose FAL vision-language models accept.
- Anything else (an OpenRouter-style `"vendor/model"` id, e.g.
  `"anthropic/claude-sonnet-4.5"`) is routed through FAL's own
  `openrouter/router/vision` gateway instead, which fronts a much larger set
  of general-purpose vision LLMs (Claude, GPT, Gemini, Llama, Qwen,
  Pixtral...) behind one endpoint — its request shape is `image_urls` (a
  list, plural) + `model` + `prompt`, unlike the direct-endpoint shape above.

Either way, the response has no fixed schema, so this client searches the
*entire* JSON response body for the expected score array rather than
assuming one specific field name. Only the first sampled/collage image is
sent (FAL model schemas rarely accept more than one). Treat this
integration as best-effort compared to OpenRouter/Gemini/Mistral.
"""

from __future__ import annotations

import json

import httpx

from app.providers.base import _ARRAY_RE, ProviderError, UsageInfo, build_prompt, encode_image_base64, parse_scores

API_URL_TEMPLATE = "https://fal.run/{model}"
ROUTER_URL = "https://fal.run/openrouter/router/vision"
DEFAULT_MODEL = "fal-ai/moondream2/visual-query"
TIMEOUT_SECONDS = 60


def _find_score_text(data: object) -> str | None:
    """Recursively search a parsed FAL response for the score array (bug
    found via live testing against the real API, not the mocked unit tests
    -- moondream2 sometimes pretty-prints its `"output"` string with real
    newlines, e.g. `"[\\n  0,\\n  1\\n]"`). Returning that *actual* string
    value (already un-escaped by `response.json()`) rather than re-encoding
    the whole response with `json.dumps()` first and regex-searching *that*
    matters: real newlines inside a JSON string get escaped to a literal
    backslash-n in the dumped text, which is not valid JSON once the regex
    slices out just the `[...]` portion, so `parse_scores()` would fail on a
    perfectly fine reply. A plain list of numbers found anywhere in the
    structure is re-serialized with `json.dumps()` too, but a bare number
    list never contains characters that need escaping, so that path was
    never actually affected."""
    if isinstance(data, str):
        return data if _ARRAY_RE.search(data) else None
    if isinstance(data, list):
        if data and all(isinstance(item, (int, float)) for item in data):
            return json.dumps(data)
        for item in data:
            found = _find_score_text(item)
            if found:
                return found
        return None
    if isinstance(data, dict):
        for value in data.values():
            found = _find_score_text(value)
            if found:
                return found
    return None


def score_tags(
    images: list[bytes], tags: list[str], model: str | None, api_key: str, *, timeout: float | None = None
) -> tuple[list[int], UsageInfo]:
    if not images:
        raise ProviderError("No images to send.")
    prompt = build_prompt(tags)
    image_data_uri = f"data:image/jpeg;base64,{encode_image_base64(images[0])}"
    selected_model = model or DEFAULT_MODEL

    if selected_model.startswith("fal-ai/"):
        url = API_URL_TEMPLATE.format(model=selected_model)
        payload = {"prompt": prompt, "image_url": image_data_uri}
    else:
        url = ROUTER_URL
        payload = {"prompt": prompt, "image_urls": [image_data_uri], "model": selected_model}

    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Key {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout or TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        raise ProviderError(f"FAL request failed: {exc}") from exc

    # FAL has no fixed response schema (see module docstring), so there's no
    # reliable field to pull token usage from -- usage stats log the call
    # itself but never tokens/cost for this provider. The "raw text" (shown
    # to the user in Tag Lab) is still the whole response body serialized
    # back to text, but *parsing* the score array searches the actual parsed
    # structure instead (`_find_score_text()`) rather than regexing that same
    # dumped text, to avoid the escaped-newline bug documented above.
    raw_text = json.dumps(data)
    score_text = _find_score_text(data) or raw_text
    return (
        parse_scores(score_text, len(tags), raw_full_response=data),
        UsageInfo(raw_text=raw_text, raw_full_response=data),
    )
