"""Tests for `app/provider_usage.py` (user request -- persisted usage stats
per model, with tokens/estimated cost) and for the logging hook in
`app/providers/registry.py` that writes a row on every provider call,
success or failure.
"""

from __future__ import annotations

from app import provider_usage
from app.providers import registry
from app.providers.base import ProviderError, UsageInfo


def test_estimate_cost_usd_known_model(engine):
    # Seeded by app/model_pricing.py's seed_default_prices() at migration 28.
    cost = provider_usage.estimate_cost_usd(engine, "gemini", "gemini-2.5-flash", tokens_in=1_000_000, tokens_out=1_000_000)
    assert cost == 0.30 + 2.50


def test_estimate_cost_usd_unknown_model_returns_none(engine):
    assert provider_usage.estimate_cost_usd(engine, "gemini", "some-custom-model", tokens_in=100, tokens_out=10) is None


def test_estimate_cost_usd_missing_tokens_returns_none(engine):
    assert provider_usage.estimate_cost_usd(engine, "gemini", "gemini-2.5-flash", tokens_in=None, tokens_out=10) is None
    assert provider_usage.estimate_cost_usd(engine, "gemini", None, tokens_in=100, tokens_out=10) is None


def test_log_usage_and_get_usage_summary_aggregates_across_calls(engine):
    provider_usage.log_usage(
        engine, provider_type="gemini", model_name="gemini-2.5-flash", request_kind="sync",
        success=True, tokens_in=1000, tokens_out=200,
    )
    provider_usage.log_usage(
        engine, provider_type="gemini", model_name="gemini-2.5-flash", request_kind="sync",
        success=False, error_message="boom",
    )
    provider_usage.log_usage(
        engine, provider_type="fal", model_name="fal-ai/moondream2/visual-query", request_kind="sync",
        success=True,
    )

    summary = provider_usage.get_usage_summary(engine)
    by_model = {(row["provider_type"], row["model_name"]): row for row in summary}

    gemini_row = by_model[("gemini", "gemini-2.5-flash")]
    assert gemini_row["call_count"] == 2
    assert gemini_row["success_count"] == 1
    assert gemini_row["total_tokens_in"] == 1000
    assert gemini_row["total_tokens_out"] == 200
    assert gemini_row["total_estimated_cost_usd"] is not None

    fal_row = by_model[("fal", "fal-ai/moondream2/visual-query")]
    assert fal_row["call_count"] == 1
    assert fal_row["total_tokens_in"] is None  # FAL never reports usage
    assert fal_row["total_estimated_cost_usd"] is None


def test_score_tags_with_entry_logs_success(engine, monkeypatch):
    entry = {"id": "e1", "provider_type": "gemini", "vision_model": "gemini-2.5-flash", "enabled": True}
    monkeypatch.setitem(
        registry._CLIENTS, "gemini", lambda images, tags, model, api_key, **_kwargs: ([80], UsageInfo(50, 5))
    )
    monkeypatch.setattr(registry, "_resolve_entry_api_key", lambda e: "gm-test")

    scores, usage = registry.score_tags_with_entry(engine, entry, [b"img"], ["cat"])
    assert scores == [80]
    assert usage.tokens_in == 50

    summary = provider_usage.get_usage_summary(engine)
    assert summary[0]["provider_type"] == "gemini"
    assert summary[0]["success_count"] == 1
    assert summary[0]["total_tokens_in"] == 50


def test_score_tags_with_entry_logs_failure(engine, monkeypatch):
    entry = {"id": "e1", "provider_type": "gemini", "vision_model": "gemini-2.5-flash", "enabled": True}

    def failing(images, tags, model, api_key, **_kwargs):
        raise ProviderError("quota exceeded")

    monkeypatch.setitem(registry._CLIENTS, "gemini", failing)
    monkeypatch.setattr(registry, "_resolve_entry_api_key", lambda e: "gm-test")

    try:
        registry.score_tags_with_entry(engine, entry, [b"img"], ["cat"])
    except ProviderError:
        pass

    summary = provider_usage.get_usage_summary(engine)
    assert summary[0]["call_count"] == 1
    assert summary[0]["success_count"] == 0
