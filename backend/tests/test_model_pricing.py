"""Tests for `app/model_pricing.py` (user request -- editable, sourced
per-model $/1M-token pricing) and its OpenRouter-refresh integration with
`app/providers/openrouter.py::fetch_pricing`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app import model_pricing
from app.providers import openrouter


def test_seed_prices_are_present(engine):
    prices = model_pricing.list_prices(engine)
    by_model = {(row["provider_type"], row["model_name"]): row for row in prices}
    row = by_model[("gemini", "gemini-2.5-flash")]
    assert row["input_per_million"] == 0.30
    assert row["output_per_million"] == 2.50
    assert row["source"] == "manual"


def test_get_price_unknown_model_returns_none(engine):
    assert model_pricing.get_price(engine, "gemini", "no-such-model") is None
    assert model_pricing.get_price(engine, "gemini", None) is None


def test_upsert_price_overwrites_and_updates_source(engine):
    model_pricing.upsert_price(engine, "gemini", "gemini-2.5-flash", 1.0, 2.0, "manual")
    assert model_pricing.get_price(engine, "gemini", "gemini-2.5-flash") == (1.0, 2.0)

    row = next(
        r for r in model_pricing.list_prices(engine)
        if r["provider_type"] == "gemini" and r["model_name"] == "gemini-2.5-flash"
    )
    assert row["source"] == "manual"


def test_upsert_price_new_pair(engine):
    model_pricing.upsert_price(engine, "openrouter", "xiaomi/mimo-v2.5", 0.1, 0.3, "openrouter_api")
    assert model_pricing.get_price(engine, "openrouter", "xiaomi/mimo-v2.5") == (0.1, 0.3)


def test_refresh_openrouter_prices_no_entries_returns_empty(engine):
    assert model_pricing.refresh_openrouter_prices(engine) == {"updated": [], "not_found": []}


def _insert_openrouter_entry(engine, vision_model: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO provider_entries
                    (id, provider_type, display_name, enabled, vision_model, text_model,
                     batch_enabled, sort_order, created_at, updated_at)
                VALUES (:id, 'openrouter', 'OR', 1, :model, NULL, 0, 0, :now, :now)
                """
            ),
            {"id": str(uuid.uuid4()), "model": vision_model, "now": now},
        )


def test_refresh_openrouter_prices_updates_configured_models(engine, monkeypatch):
    _insert_openrouter_entry(engine, "xiaomi/mimo-v2.5")
    _insert_openrouter_entry(engine, "some/unknown-model")

    def fake_fetch_pricing(model_ids):
        assert set(model_ids) == {"xiaomi/mimo-v2.5", "some/unknown-model"}
        return {"xiaomi/mimo-v2.5": (0.05, 0.15)}

    monkeypatch.setattr(openrouter, "fetch_pricing", fake_fetch_pricing)

    result = model_pricing.refresh_openrouter_prices(engine)
    assert result == {"updated": ["xiaomi/mimo-v2.5"], "not_found": ["some/unknown-model"]}
    assert model_pricing.get_price(engine, "openrouter", "xiaomi/mimo-v2.5") == (0.05, 0.15)

    row = next(
        r for r in model_pricing.list_prices(engine)
        if r["provider_type"] == "openrouter" and r["model_name"] == "xiaomi/mimo-v2.5"
    )
    assert row["source"] == "openrouter_api"


def test_openrouter_fetch_pricing_parses_response(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "data": [
                    {"id": "xiaomi/mimo-v2.5", "pricing": {"prompt": "0.0000001", "completion": "0.0000003"}},
                    {"id": "other/model", "pricing": {"prompt": "0.000001", "completion": "0.000002"}},
                ]
            }

    monkeypatch.setattr(openrouter.httpx, "get", lambda url, timeout: FakeResponse())

    prices = openrouter.fetch_pricing(["xiaomi/mimo-v2.5"])
    assert prices == {"xiaomi/mimo-v2.5": (0.1, 0.3)}
