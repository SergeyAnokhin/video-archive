"""Unit tests for the four vision-provider clients (Specification §12.3,
§18): request construction and response parsing for each of
`app/providers/{openrouter,gemini,mistral,fal}.py`, with `httpx.post`
monkeypatched so no real network call is ever made. Real-provider behavior
(actually reaching OpenRouter) was verified manually — see `docs/roadmap.md`
Stage 6 "Done when" — this file only protects the request/response
plumbing from regressing silently.
"""

from __future__ import annotations

import json

import httpx
import pytest

from app.providers import fal, gemini, mistral, openrouter
from app.providers.base import ProviderError

FAKE_IMAGE = b"\xff\xd8fake-jpeg-bytes"
TAGS = ["cat", "beach"]


class FakeResponse:
    def __init__(self, json_data, status_code=200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://example.invalid")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("error", request=request, response=response)

    def json(self):
        return self._json_data


# --- OpenRouter --------------------------------------------------------


def test_openrouter_builds_expected_request_and_parses_scores(monkeypatch):
    captured = {}

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse({"choices": [{"message": {"content": "[80, 20]"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    scores = openrouter.score_tags([FAKE_IMAGE], TAGS, "openai/gpt-4o-mini", "sk-test")

    assert scores == [80, 20]
    assert captured["url"] == openrouter.API_URL
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["json"]["model"] == "openai/gpt-4o-mini"
    content = captured["json"]["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_openrouter_uses_default_model_when_none_given(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        httpx, "post",
        lambda url, **kwargs: captured.update(json=kwargs["json"]) or FakeResponse(
            {"choices": [{"message": {"content": "[1, 2]"}}]}
        ),
    )
    openrouter.score_tags([FAKE_IMAGE], TAGS, None, "sk-test")
    assert captured["json"]["model"] == openrouter.DEFAULT_MODEL


def test_openrouter_raises_provider_error_on_http_error(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse({}, status_code=401))
    with pytest.raises(ProviderError):
        openrouter.score_tags([FAKE_IMAGE], TAGS, None, "sk-bad")


def test_openrouter_raises_provider_error_on_malformed_response(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse({"unexpected": "shape"}))
    with pytest.raises(ProviderError):
        openrouter.score_tags([FAKE_IMAGE], TAGS, None, "sk-test")


# --- Gemini --------------------------------------------------------------


def test_gemini_builds_expected_request_and_parses_scores(monkeypatch):
    captured = {}

    def fake_post(url, *, params, json, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["json"] = json
        return FakeResponse({"candidates": [{"content": {"parts": [{"text": "[55, 5]"}]}}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    scores = gemini.score_tags([FAKE_IMAGE], TAGS, "gemini-2.5-flash", "gm-test")

    assert scores == [55, 5]
    assert captured["url"] == gemini.API_URL_TEMPLATE.format(model="gemini-2.5-flash")
    assert captured["params"] == {"key": "gm-test"}
    parts = captured["json"]["contents"][0]["parts"]
    assert parts[0]["text"]  # prompt text first
    assert parts[1]["inline_data"]["mime_type"] == "image/jpeg"


def test_gemini_raises_provider_error_on_malformed_response(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse({"candidates": []}))
    with pytest.raises(ProviderError):
        gemini.score_tags([FAKE_IMAGE], TAGS, None, "gm-test")


# --- Mistral ---------------------------------------------------------------


def test_mistral_builds_expected_request_and_parses_scores(monkeypatch):
    captured = {}

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse({"choices": [{"message": {"content": "[10, 90]"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    scores = mistral.score_tags([FAKE_IMAGE], TAGS, None, "ms-test")

    assert scores == [10, 90]
    assert captured["url"] == mistral.API_URL
    assert captured["headers"]["Authorization"] == "Bearer ms-test"
    assert captured["json"]["model"] == mistral.DEFAULT_MODEL
    content = captured["json"]["messages"][0]["content"]
    # Mistral's image_url is a bare data-URI string, unlike OpenRouter's {"url": ...}
    assert isinstance(content[1]["image_url"], str)
    assert content[1]["image_url"].startswith("data:image/jpeg;base64,")


def test_mistral_raises_provider_error_on_http_error(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse({}, status_code=500))
    with pytest.raises(ProviderError):
        mistral.score_tags([FAKE_IMAGE], TAGS, None, "ms-test")


# --- FAL -------------------------------------------------------------------


def test_fal_builds_expected_request_and_parses_scores(monkeypatch):
    captured = {}

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse({"output": "[33, 67]"})

    monkeypatch.setattr(httpx, "post", fake_post)

    scores = fal.score_tags([FAKE_IMAGE], TAGS, "fal-ai/moondream2/visual-query", "fal-test")

    assert scores == [33, 67]
    assert captured["url"] == fal.API_URL_TEMPLATE.format(model="fal-ai/moondream2/visual-query")
    assert captured["headers"]["Authorization"] == "Key fal-test"
    assert captured["json"]["image_url"].startswith("data:image/jpeg;base64,")
    assert "prompt" in captured["json"]


def test_fal_searches_whole_response_body_for_score_array(monkeypatch):
    # FAL has no fixed response schema; parse_scores is handed json.dumps(data)
    # of the *entire* body, so the array can be nested anywhere.
    monkeypatch.setattr(
        httpx, "post", lambda *a, **k: FakeResponse({"result": {"nested": {"scores": [12, 34]}}})
    )
    scores = fal.score_tags([FAKE_IMAGE], TAGS, None, "fal-test")
    assert scores == [12, 34]


def test_fal_raises_provider_error_without_images():
    with pytest.raises(ProviderError):
        fal.score_tags([], TAGS, None, "fal-test")


def test_fal_raises_provider_error_on_http_error(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse({}, status_code=403))
    with pytest.raises(ProviderError):
        fal.score_tags([FAKE_IMAGE], TAGS, None, "fal-test")
