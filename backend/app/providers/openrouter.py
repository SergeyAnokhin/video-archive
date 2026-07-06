"""OpenRouter vision scoring (Tech Stack: "Gateway to many vision models").

OpenRouter exposes an OpenAI-compatible chat completions endpoint, so a
single request can carry the text prompt plus any number of `image_url`
parts (used as data URIs here since frames never leave the local machine as
files).
"""

from __future__ import annotations

import httpx

from app.providers.base import ProviderError, build_prompt, encode_image_base64, parse_scores

API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-2.5-flash"
TIMEOUT_SECONDS = 60


def score_tags(images: list[bytes], tags: list[str], model: str | None, api_key: str) -> list[int]:
    prompt = build_prompt(tags)
    content = [{"type": "text", "text": prompt}]
    for image_bytes in images:
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{encode_image_base64(image_bytes)}"},
            }
        )

    try:
        response = httpx.post(
            API_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model or DEFAULT_MODEL, "messages": [{"role": "user", "content": content}]},
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        text_reply = data["choices"][0]["message"]["content"]
    except httpx.HTTPError as exc:
        raise ProviderError(f"OpenRouter request failed: {exc}") from exc
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"Unexpected OpenRouter response shape: {exc}") from exc

    return parse_scores(text_reply, len(tags))
