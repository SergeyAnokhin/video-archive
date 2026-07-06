"""Shared vision-provider request scaffolding (Specification §12.3, §18).

Every provider module builds its own request against its own API shape, but
they all send the same prompt (score each vocabulary tag 0-100 against the
attached image(s)) and expect the same reply shape back: a single JSON array
of integers, one per tag, in the exact order the tags were listed. Indexed
scoring (rather than asking the model to echo tag text) avoids any
case/whitespace text-matching ambiguity when parsing the reply.
"""

from __future__ import annotations

import base64
import json
import re


class ProviderError(Exception):
    """Raised when a provider request fails or its response can't be parsed
    into scores. Callers (the tagging job) treat this as a failed job item,
    never as something that should invent placeholder tags."""


def encode_image_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode("ascii")


def build_prompt(tags: list[str]) -> str:
    numbered = "\n".join(f"{i}: {tag}" for i, tag in enumerate(tags))
    return (
        "You are scoring how well a fixed vocabulary of tags matches the attached image(s), "
        "which are sampled frames from one video.\n"
        "Score each tag's relevance from 0 (not present/not applicable) to 100 (clearly present).\n\n"
        f"Tags:\n{numbered}\n\n"
        "Respond with ONLY a JSON array of integers, one score per tag, in the exact order listed "
        "above (same length, same order). Do not include tag names, explanations, or any other text."
    )


_ARRAY_RE = re.compile(r"\[[\s\S]*\]")


def parse_scores(response_text: str, expected_count: int) -> list[int]:
    match = _ARRAY_RE.search(response_text or "")
    if not match:
        raise ProviderError("Provider response did not contain a JSON array of scores.")
    try:
        values = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ProviderError(f"Provider response was not valid JSON: {exc}") from exc
    if not isinstance(values, list):
        raise ProviderError("Provider response JSON array was expected but not found.")

    scores = [max(0, min(100, int(v))) for v in values[:expected_count]]
    while len(scores) < expected_count:
        scores.append(0)
    return scores
