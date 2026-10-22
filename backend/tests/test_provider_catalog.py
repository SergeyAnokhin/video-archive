"""Cached model catalogs (`app/provider_catalog.py`): at-most-daily refresh,
failure handling, and OpenRouter's catalog doubling as the daily price
update. Provider network calls are stubbed throughout."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app import model_pricing, provider_catalog, provider_entries, secrets_store
from app.providers import openrouter, registry


def _stub_listing(monkeypatch, models):
    calls = []

    def fake(provider_type, api_key):
        calls.append((provider_type, api_key))
        if isinstance(models, Exception):
            raise models
        return models

    monkeypatch.setattr(registry, "list_models_for_provider_type", fake)
    return calls


def _age_status(engine, provider_type, hours):
    checked_at = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE provider_catalog_status SET checked_at = :c WHERE provider_type = :t"),
            {"c": checked_at, "t": provider_type},
        )


def test_catalog_is_fetched_once_then_cached_for_a_day(engine, monkeypatch):
    secrets_store.set_provider_api_key("gemini", "sk-g")
    calls = _stub_listing(monkeypatch, ["b-model", "a-model"])

    catalog = provider_catalog.get_catalog(engine, "gemini")
    assert [m["model_id"] for m in catalog["models"]] == ["a-model", "b-model"]
    assert calls == [("gemini", "sk-g")]

    provider_catalog.get_catalog(engine, "gemini")
    _age_status(engine, "gemini", 23)
    provider_catalog.refresh_stale(engine)
    assert len(calls) == 1

    _age_status(engine, "gemini", 25)
    provider_catalog.refresh_stale(engine)
    assert len(calls) == 2

    provider_catalog.refresh_stale(engine, force=True)
    assert len(calls) == 3


def test_no_key_means_no_fetch(engine, monkeypatch):
    calls = _stub_listing(monkeypatch, ["x"])
    provider_catalog.refresh_stale(engine, force=True)
    assert calls == []
    assert provider_catalog.get_catalog(engine, "mistral")["models"] == []


def test_failed_refresh_keeps_old_catalog_and_counts_as_checked(engine, monkeypatch):
    secrets_store.set_provider_api_key("mistral", "sk-m")
    _stub_listing(monkeypatch, ["pixtral"])
    provider_catalog.refresh_catalog(engine, "mistral")
    first = provider_catalog.get_status(engine, "mistral")

    calls = _stub_listing(monkeypatch, registry.ProviderError("401 bad key"))
    _age_status(engine, "mistral", 25)
    catalog = provider_catalog.get_catalog(engine, "mistral")
    assert [m["model_id"] for m in catalog["models"]] == ["pixtral"]
    assert catalog["error"] == "401 bad key"
    assert catalog["fetched_at"] == first["fetched_at"]

    # The failed attempt itself isn't retried until the next day.
    provider_catalog.get_catalog(engine, "mistral")
    assert len(calls) == 1


def test_failed_refresh_error_never_contains_the_key(engine, monkeypatch):
    secrets_store.set_provider_api_key("gemini", "sk-secret-key")
    _stub_listing(monkeypatch, registry.ProviderError("400 for url '...models?key=sk-secret-key'"))
    provider_catalog.refresh_catalog(engine, "gemini")
    assert provider_catalog.get_status(engine, "gemini")["error"] == "400 for url '...models?key=***'"


def test_openrouter_refresh_overwrites_configured_prices_including_manual(engine, monkeypatch):
    secrets_store.set_provider_api_key("openrouter", "sk-or")
    provider_entries.create_entry(engine, {"provider_type": "openrouter", "vision_model": "vendor/vision"})
    model_pricing.upsert_price(engine, "openrouter", "vendor/vision", 9.0, 9.0, "manual")
    monkeypatch.setattr(
        openrouter,
        "fetch_catalog",
        lambda: ([("vendor/vision", (1.0, 2.0))], {"vendor/vision": (1.0, 2.0), "vendor/text": (0.1, 0.2)}),
    )

    provider_catalog.refresh_catalog(engine, "openrouter")

    assert model_pricing.get_price(engine, "openrouter", "vendor/vision") == (1.0, 2.0)
    # Only configured models get a price row.
    assert model_pricing.get_price(engine, "openrouter", "vendor/text") is None
    catalog = provider_catalog.get_catalog(engine, "openrouter", refresh_if_stale=False)
    assert catalog["models"] == [{"model_id": "vendor/vision", "input_per_million": 1.0, "output_per_million": 2.0}]


def test_fill_missing_prices_uses_catalog_only_when_no_price_yet(engine, monkeypatch):
    secrets_store.set_provider_api_key("openrouter", "sk-or")
    monkeypatch.setattr(
        openrouter, "fetch_catalog", lambda: ([("a/one", (1.0, 2.0)), ("a/two", (3.0, 4.0))], {})
    )
    provider_catalog.refresh_catalog(engine, "openrouter")
    model_pricing.upsert_price(engine, "openrouter", "a/two", 5.0, 5.0, "manual")

    provider_catalog.fill_missing_prices(engine, "openrouter", ["a/one", "a/two", None, "a/missing"])

    assert model_pricing.get_price(engine, "openrouter", "a/one") == (1.0, 2.0)
    assert model_pricing.get_price(engine, "openrouter", "a/two") == (5.0, 5.0)
    assert model_pricing.get_price(engine, "openrouter", "a/missing") is None


def test_provider_statuses_cover_every_type(engine):
    secrets_store.set_provider_api_key("fal", "fal-key-abcd")
    statuses = {s["provider_type"]: s for s in provider_catalog.list_provider_statuses(engine)}
    assert set(statuses) == set(provider_entries.PROVIDER_TYPES)
    assert statuses["fal"]["key_suffix"] == "abcd"
    assert statuses["fal"]["catalog_supported"] is False
    assert statuses["gemini"]["has_api_key"] is False
