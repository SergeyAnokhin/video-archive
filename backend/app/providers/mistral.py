"""Mistral (Pixtral) vision scoring (Tech Stack: "Vision scoring; batch API
support" — batch submission is not implemented in this stage, see
`docs/code-map.md`). Mistral's chat completions endpoint is OpenAI-compatible,
same request shape as `app/providers/openrouter.py`.
"""

from __future__ import annotations

import httpx

from app.providers.base import ProviderError, build_prompt, encode_image_base64, parse_scores

API_URL = "https://api.mistral.ai/v1/chat/completions"
DEFAULT_MODEL = "pixtral-12b-2409"
TIMEOUT_SECONDS = 60


def score_tags(images: list[bytes], tags: list[str], model: str | None, api_key: str) -> list[int]:
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
            timeout=TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()
        text_reply = data["choices"][0]["message"]["content"]
    except httpx.HTTPError as exc:
        raise ProviderError(f"Mistral request failed: {exc}") from exc
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError(f"Unexpected Mistral response shape: {exc}") from exc

    return parse_scores(text_reply, len(tags))
