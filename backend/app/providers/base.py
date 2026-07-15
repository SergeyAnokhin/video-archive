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
from dataclasses import dataclass


class ProviderError(Exception):
    """Raised when a provider request fails or its response can't be parsed
    into scores. Callers (the tagging job) treat this as a failed job item,
    never as something that should invent placeholder tags.

    `raw_text`/`raw_full_response` carry whatever of the provider's actual
    reply was successfully received before the failure (user request -- the
    model's raw answer should still be inspectable even when interpreting it
    fails, e.g. "Unexpected Gemini response shape"). Both are `None` when
    nothing was received yet (e.g. the HTTP request itself failed)."""

    def __init__(self, message: str, *, raw_text: str | None = None, raw_full_response: dict | None = None):
        super().__init__(message)
        self.raw_text = raw_text
        self.raw_full_response = raw_full_response


@dataclass
class UsageInfo:
    """Token usage for one provider call, parsed from whatever usage
    metadata that provider's response exposes (user request -- usage
    statistics with tokens/cost per model). `None` fields mean the provider
    didn't report that count (e.g. FAL, which has no fixed response schema
    to parse one from) rather than a real zero."""

    tokens_in: int | None = None
    tokens_out: int | None = None
    raw_text: str | None = None
    """The provider's raw reply text before parsing (user request -- Tag Lab
    shows the exact model output). For OpenRouter/Gemini/Mistral this is the
    model's message/content text (the same string `parse_scores()` reads);
    for FAL, which has no fixed response schema, this is the full JSON
    response body serialized back to text, same as `BatchPollResult.
    raw_texts`'s per-file convention on the batch path."""
    raw_full_response: dict | None = None
    """The provider's complete parsed JSON response body (user request --
    `raw_text` alone dropped technical fields like usage/model/finish reason
    that live outside the message content; Tag Lab shows this one as
    formatted JSON so those fields are inspectable too)."""


@dataclass
class BatchPollResult:
    """One poll of a persisted batch submission (user request -- batch
    tagging must survive a service restart). `done=False` means keep
    waiting; a caller polls again later rather than treating this as an
    error. `done=True` with `error` set means the provider-side job itself
    failed (as opposed to individual files not being resolved, which is
    represented in `results` the same way `submit_batch()` always has: a
    `None` value for that key)."""

    done: bool
    results: dict[str, list[int] | None] | None = None
    usage: UsageInfo | None = None
    error: str | None = None
    raw_texts: dict[str, str] | None = None
    """Each file's raw provider reply text, keyed the same as `results` (user
    request -- log the exact model output before it's parsed/ranked, so a
    parsing or scoring bug downstream still leaves a record of what the
    model actually said). Only populated once the batch resolves
    successfully; absent entries mean that key's response couldn't even be
    extracted (see each provider's `poll_batch()`)."""


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


def parse_scores(response_text: str, expected_count: int, *, raw_full_response: dict | None = None) -> list[int]:
    match = _ARRAY_RE.search(response_text or "")
    if not match:
        raise ProviderError(
            "Provider response did not contain a JSON array of scores.",
            raw_text=response_text, raw_full_response=raw_full_response,
        )
    try:
        values = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ProviderError(
            f"Provider response was not valid JSON: {exc}",
            raw_text=response_text, raw_full_response=raw_full_response,
        ) from exc
    if not isinstance(values, list):
        raise ProviderError(
            "Provider response JSON array was expected but not found.",
            raw_text=response_text, raw_full_response=raw_full_response,
        )

    scores = [max(0, min(100, int(v))) for v in values[:expected_count]]
    while len(scores) < expected_count:
        scores.append(0)
    return scores
