"""Google Gemini vision scoring (Tech Stack: "Vision scoring; batch API
support" — batch submission is not implemented in this stage, see
`docs/code-map.md`).
"""

from __future__ import annotations

import httpx

from app.providers.base import ProviderError, build_prompt, encode_image_base64, parse_scores

API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-2.5-flash"
TIMEOUT_SECONDS = 60


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
