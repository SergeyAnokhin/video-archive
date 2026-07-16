"""Unit tests for the four vision-provider clients (Specification §12.3,
§18): request construction and response parsing for each of
`app/providers/{openrouter,gemini,mistral,fal}.py`, with `httpx.post`
monkeypatched so no real network call is ever made. Real-provider behavior
(actually reaching OpenRouter) was verified manually — see `docs/spec/roadmap.md`
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

    scores, usage = openrouter.score_tags([FAKE_IMAGE], TAGS, "openai/gpt-4o-mini", "sk-test")

    assert scores == [80, 20]
    assert usage.tokens_in is None
    assert usage.tokens_out is None
    assert usage.raw_text == "[80, 20]"
    assert captured["url"] == openrouter.API_URL
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["json"]["model"] == "openai/gpt-4o-mini"
    content = captured["json"]["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_openrouter_parses_usage_when_present(monkeypatch):
    monkeypatch.setattr(
        httpx, "post",
        lambda *a, **k: FakeResponse(
            {"choices": [{"message": {"content": "[80, 20]"}}], "usage": {"prompt_tokens": 150, "completion_tokens": 6}}
        ),
    )
    _scores, usage = openrouter.score_tags([FAKE_IMAGE], TAGS, None, "sk-test")
    assert usage.tokens_in == 150
    assert usage.tokens_out == 6


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
    with pytest.raises(ProviderError) as excinfo:
        openrouter.score_tags([FAKE_IMAGE], TAGS, None, "sk-test")
    # The raw response body must still be attached to the error even though
    # the expected `choices` shape wasn't found (user request -- always show
    # what the model actually replied, even on a parse failure).
    assert excinfo.value.raw_full_response == {"unexpected": "shape"}


def test_openrouter_list_models_filters_to_vision_capable(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **k: FakeResponse(
            {
                "data": [
                    {"id": "vendor/vision-model", "architecture": {"input_modalities": ["text", "image"]}},
                    {"id": "vendor/text-only-model", "architecture": {"input_modalities": ["text"]}},
                ]
            }
        ),
    )
    models = openrouter.list_models("sk-test")
    assert models == ["vendor/vision-model"]


def test_openrouter_list_models_falls_back_to_full_list_without_modalities(monkeypatch):
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: FakeResponse({"data": [{"id": "vendor/b"}, {"id": "vendor/a"}]})
    )
    models = openrouter.list_models("sk-test")
    assert models == ["vendor/a", "vendor/b"]


def test_openrouter_list_models_raises_provider_error_on_http_error(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse({}, status_code=500))
    with pytest.raises(ProviderError):
        openrouter.list_models("sk-test")


# --- Gemini --------------------------------------------------------------


def test_gemini_builds_expected_request_and_parses_scores(monkeypatch):
    captured = {}

    def fake_post(url, *, params, json, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["json"] = json
        return FakeResponse({"candidates": [{"content": {"parts": [{"text": "[55, 5]"}]}}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    scores, usage = gemini.score_tags([FAKE_IMAGE], TAGS, "gemini-2.5-flash", "gm-test")

    assert scores == [55, 5]
    assert usage.tokens_in is None
    assert usage.tokens_out is None
    assert usage.raw_text == "[55, 5]"
    assert captured["url"] == gemini.API_URL_TEMPLATE.format(model="gemini-2.5-flash")
    assert captured["params"] == {"key": "gm-test"}
    parts = captured["json"]["contents"][0]["parts"]
    assert parts[0]["text"]  # prompt text first
    assert parts[1]["inline_data"]["mime_type"] == "image/jpeg"


def test_gemini_parses_usage_metadata_when_present(monkeypatch):
    monkeypatch.setattr(
        httpx, "post",
        lambda *a, **k: FakeResponse(
            {
                "candidates": [{"content": {"parts": [{"text": "[55, 5]"}]}}],
                "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 8},
            }
        ),
    )
    _scores, usage = gemini.score_tags([FAKE_IMAGE], TAGS, None, "gm-test")
    assert usage.tokens_in == 120
    assert usage.tokens_out == 8


def test_gemini_raises_provider_error_on_malformed_response(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse({"candidates": []}))
    with pytest.raises(ProviderError) as excinfo:
        gemini.score_tags([FAKE_IMAGE], TAGS, None, "gm-test")
    assert excinfo.value.raw_full_response == {"candidates": []}


def test_gemini_raises_provider_error_with_raw_text_on_unparseable_scores(monkeypatch):
    # The Gemini-shape extraction succeeds (a `text` reply comes back), but
    # it doesn't contain a JSON scores array -- the raw text the model
    # actually said must still reach the caller.
    monkeypatch.setattr(
        httpx, "post",
        lambda *a, **k: FakeResponse({"candidates": [{"content": {"parts": [{"text": "I cannot help with that."}]}}]}),
    )
    with pytest.raises(ProviderError) as excinfo:
        gemini.score_tags([FAKE_IMAGE], TAGS, None, "gm-test")
    assert excinfo.value.raw_text == "I cannot help with that."


def test_gemini_list_models_filters_to_generate_content_and_strips_prefix(monkeypatch):
    monkeypatch.setattr(
        httpx,
        "get",
        lambda *a, **k: FakeResponse(
            {
                "models": [
                    {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
                    {"name": "models/embedding-001", "supportedGenerationMethods": ["embedContent"]},
                ]
            }
        ),
    )
    assert gemini.list_models("gm-test") == ["gemini-2.5-flash"]


def test_gemini_list_models_raises_provider_error_on_http_error(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse({}, status_code=401))
    with pytest.raises(ProviderError):
        gemini.list_models("gm-bad")


# --- Mistral ---------------------------------------------------------------


def test_mistral_builds_expected_request_and_parses_scores(monkeypatch):
    captured = {}

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse({"choices": [{"message": {"content": "[10, 90]"}}]})

    monkeypatch.setattr(httpx, "post", fake_post)

    scores, usage = mistral.score_tags([FAKE_IMAGE], TAGS, None, "ms-test")

    assert scores == [10, 90]
    assert usage.tokens_in is None
    assert usage.tokens_out is None
    assert usage.raw_text == "[10, 90]"
    assert captured["url"] == mistral.API_URL
    assert captured["headers"]["Authorization"] == "Bearer ms-test"
    assert captured["json"]["model"] == mistral.DEFAULT_MODEL
    content = captured["json"]["messages"][0]["content"]
    # Mistral's image_url is a bare data-URI string, unlike OpenRouter's {"url": ...}
    assert isinstance(content[1]["image_url"], str)
    assert content[1]["image_url"].startswith("data:image/jpeg;base64,")


def test_mistral_parses_usage_when_present(monkeypatch):
    monkeypatch.setattr(
        httpx, "post",
        lambda *a, **k: FakeResponse(
            {"choices": [{"message": {"content": "[10, 90]"}}], "usage": {"prompt_tokens": 200, "completion_tokens": 4}}
        ),
    )
    _scores, usage = mistral.score_tags([FAKE_IMAGE], TAGS, None, "ms-test")
    assert usage.tokens_in == 200
    assert usage.tokens_out == 4


def test_mistral_raises_provider_error_on_http_error(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse({}, status_code=500))
    with pytest.raises(ProviderError):
        mistral.score_tags([FAKE_IMAGE], TAGS, None, "ms-test")


def test_mistral_raises_provider_error_on_malformed_response(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse({"unexpected": "shape"}))
    with pytest.raises(ProviderError) as excinfo:
        mistral.score_tags([FAKE_IMAGE], TAGS, None, "ms-test")
    assert excinfo.value.raw_full_response == {"unexpected": "shape"}


def test_mistral_list_models_sorted(monkeypatch):
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: FakeResponse({"data": [{"id": "mistral-large"}, {"id": "pixtral-12b"}]})
    )
    assert mistral.list_models("ms-test") == ["mistral-large", "pixtral-12b"]


def test_mistral_list_models_raises_provider_error_on_http_error(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: FakeResponse({}, status_code=401))
    with pytest.raises(ProviderError):
        mistral.list_models("ms-bad")


# --- FAL -------------------------------------------------------------------
# No `list_models()` here, deliberately: FAL has no fixed vision-chat schema
# and its model-listing API mixes every model type (image-gen, LoRA, audio,
# ...), not a clean vision-tagging subset -- see `app/providers/fal.py` and
# `app/providers/registry.py`'s `_MODEL_LIST_CLIENTS`.


def test_fal_builds_expected_request_and_parses_scores(monkeypatch):
    captured = {}

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse({"output": "[33, 67]"})

    monkeypatch.setattr(httpx, "post", fake_post)

    scores, usage = fal.score_tags([FAKE_IMAGE], TAGS, "fal-ai/moondream2/visual-query", "fal-test")

    assert scores == [33, 67]
    assert usage.tokens_in is None
    assert usage.tokens_out is None
    assert usage.raw_text == json.dumps({"output": "[33, 67]"})
    assert captured["url"] == fal.API_URL_TEMPLATE.format(model="fal-ai/moondream2/visual-query")
    assert captured["headers"]["Authorization"] == "Key fal-test"
    assert captured["json"]["image_url"].startswith("data:image/jpeg;base64,")
    assert "prompt" in captured["json"]


def test_fal_routes_non_fal_model_ids_through_the_openrouter_gateway(monkeypatch):
    # user request: a "vendor/model" id (not a literal "fal-ai/..." app
    # path) picks a real vision LLM through FAL's openrouter/router/vision
    # gateway instead of trying (and failing) to call it as a FAL app.
    captured = {}

    def fake_post(url, *, headers, json, timeout):
        captured["url"] = url
        captured["json"] = json
        return FakeResponse({"output": "[10, 90]"})

    monkeypatch.setattr(httpx, "post", fake_post)

    scores, _usage = fal.score_tags([FAKE_IMAGE], TAGS, "anthropic/claude-sonnet-4.5", "fal-test")

    assert scores == [10, 90]
    assert captured["url"] == fal.ROUTER_URL
    assert captured["json"]["model"] == "anthropic/claude-sonnet-4.5"
    assert len(captured["json"]["image_urls"]) == 1
    assert captured["json"]["image_urls"][0].startswith("data:image/jpeg;base64,")
    assert "image_url" not in captured["json"]


def test_fal_searches_whole_response_body_for_score_array(monkeypatch):
    # FAL has no fixed response schema; parse_scores is handed json.dumps(data)
    # of the *entire* body, so the array can be nested anywhere.
    monkeypatch.setattr(
        httpx, "post", lambda *a, **k: FakeResponse({"result": {"nested": {"scores": [12, 34]}}})
    )
    scores, _usage = fal.score_tags([FAKE_IMAGE], TAGS, None, "fal-test")
    assert scores == [12, 34]


def test_fal_raises_provider_error_without_images():
    with pytest.raises(ProviderError):
        fal.score_tags([], TAGS, None, "fal-test")


def test_fal_raises_provider_error_with_raw_body_when_no_array_found(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse({"result": "no scores here"}))
    with pytest.raises(ProviderError) as excinfo:
        fal.score_tags([FAKE_IMAGE], TAGS, None, "fal-test")
    assert excinfo.value.raw_full_response == {"result": "no scores here"}


def test_fal_raises_provider_error_on_http_error(monkeypatch):
    monkeypatch.setattr(httpx, "post", lambda *a, **k: FakeResponse({}, status_code=403))
    with pytest.raises(ProviderError):
        fal.score_tags([FAKE_IMAGE], TAGS, None, "fal-test")
