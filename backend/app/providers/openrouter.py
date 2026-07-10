"""OpenRouter vision scoring (Tech Stack: "Gateway to many vision models").

OpenRouter exposes an OpenAI-compatible chat completions endpoint, so a
single request can carry the text prompt plus any number of `image_url`
parts (used as data URIs here since frames never leave the local machine as
files).
"""

from __future__ import annotations

import httpx

from app.providers.base import ProviderError, UsageInfo, build_prompt, encode_image_base64, parse_scores

API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS_URL = "https://openrouter.ai/api/v1/models"
DEFAULT_MODEL = "google/gemini-2.5-flash"
TIMEOUT_SECONDS = 60


def list_models(api_key: str) -> list[str]:
    """Lists OpenRouter models, filtered to vision-capable ones when the
    response exposes `architecture.input_modalities` (OpenRouter proxies
    hundreds of text-only models that aren't useful for this vision-tagging
    tool). Falls back to the full unfiltered list if that field is absent.
    No auth is required for this endpoint, but `api_key` is accepted for a
    consistent call shape with the other providers' `list_models()`.
    """
    try:
        response = httpx.get(MODELS_URL, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
        models = response.json()["data"]
    except httpx.HTTPError as exc:
        raise ProviderError(f"OpenRouter model list request failed: {exc}") from exc
    except (KeyError, TypeError) as exc:
        raise ProviderError(f"Unexpected OpenRouter model list response shape: {exc}") from exc

    vision_models = [
        m["id"] for m in models if "image" in m.get("architecture", {}).get("input_modalities", [])
    ]
    names = vision_models if vision_models else [m["id"] for m in models]
    return sorted(names)


def score_tags(images: list[bytes], tags: list[str], model: str | None, api_key: str) -> tuple[list[int], UsageInfo]:
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

    usage = data.get("usage") or {}
    usage_info = UsageInfo(tokens_in=usage.get("prompt_tokens"), tokens_out=usage.get("completion_tokens"))
    return parse_scores(text_reply, len(tags)), usage_info
