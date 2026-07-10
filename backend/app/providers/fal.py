"""FAL vision scoring (Tech Stack: "Vision workloads").

Unlike the other three providers, FAL has no single fixed chat/vision API
shape shared across its model catalog — each model endpoint defines its own
request/response schema. This client targets FAL's generic synchronous
`fal.run/{model}` endpoint with a `prompt` + single `image_url` (data URI)
payload, the shape most FAL vision-language models accept, and searches the
*entire* JSON response body for the expected score array rather than
assuming one specific field name. Only the first sampled/collage image is
sent, since FAL model schemas rarely accept an image array. Treat this
integration as best-effort compared to OpenRouter/Gemini/Mistral.
"""

from __future__ import annotations

import json

import httpx

from app.providers.base import ProviderError, UsageInfo, build_prompt, encode_image_base64, parse_scores

API_URL_TEMPLATE = "https://fal.run/{model}"
DEFAULT_MODEL = "fal-ai/moondream2/visual-query"
TIMEOUT_SECONDS = 60


def score_tags(images: list[bytes], tags: list[str], model: str | None, api_key: str) -> tuple[list[int], UsageInfo]:
    if not images:
        raise ProviderError("No images to send.")
    prompt = build_prompt(tags)
    image_data_uri = f"data:image/jpeg;base64,{encode_image_base64(images[0])}"

    url = API_URL_TEMPLATE.format(model=model or DEFAULT_MODEL)
    try:
        response = httpx.post(
            url,
            headers={"Authorization": f"Key {api_key}", "Content-Type": "application/json"},
            json={"prompt": prompt, "image_url": image_data_uri},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as exc:
        raise ProviderError(f"FAL request failed: {exc}") from exc

    # FAL has no fixed response schema (see module docstring), so there's no
    # reliable field to pull token usage from -- usage stats log the call
    # itself but never tokens/cost for this provider.
    return parse_scores(json.dumps(data), len(tags)), UsageInfo()
