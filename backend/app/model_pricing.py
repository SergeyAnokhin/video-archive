"""Per-model $/1M-token pricing (user request -- an editable, sourced cost
estimate for Tag Lab, since a hand-maintained constant couldn't cover
OpenRouter's hundreds of routed models). Replaces the static
`provider_usage._COST_PER_MILLION_TOKENS_USD` dict with a DB-backed table
keyed the same way `provider_usage_log` already is (`provider_type`,
`model_name`) -- shared across every provider entry pointing at the same
model.

Two ways a row gets its price: manually entered/edited from Settings
(`source='manual'`), or fetched live from OpenRouter's public, no-auth
`GET /api/v1/models` endpoint (`source='openrouter_api'`, see
`refresh_openrouter_prices()`) -- the only one of this app's four provider
types that publishes machine-readable pricing. Gemini/Mistral prices stay
manual, seeded once from what was previously hardcoded (`seed_default_prices()`,
current as of when that dict was last hand-updated).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text

from app.providers import openrouter

# (provider_type, model_name) -> (input $/1M tokens, output $/1M tokens).
# Seeded once into `model_pricing` by `seed_default_prices()` -- editable
# from Settings afterward, this is just the starting point.
_SEED_PRICES: dict[tuple[str, str], tuple[float, float]] = {
    ("gemini", "gemini-2.5-flash"): (0.30, 2.50),
    ("gemini", "gemini-2.5-flash-lite"): (0.10, 0.40),
    ("gemini", "gemini-2.0-flash"): (0.10, 0.40),
    ("gemini", "gemini-2.0-flash-lite"): (0.075, 0.30),
    ("mistral", "pixtral-12b-2409"): (0.15, 0.15),
    ("mistral", "mistral-large-latest"): (2.00, 6.00),
    ("mistral", "mistral-small-latest"): (0.20, 0.60),
    ("mistral", "pixtral-large-latest"): (2.00, 6.00),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_default_prices(conn) -> None:
    """Idempotently inserts `_SEED_PRICES`. Called once from `init_db()`
    right after migration 28 creates the table -- never overwrites a row a
    later migration run might already find there (`INSERT OR IGNORE`), so a
    price the user has since edited or refreshed is left alone."""
    now = _now()
    for (provider_type, model_name), (input_rate, output_rate) in _SEED_PRICES.items():
        conn.execute(
            text(
                """
                INSERT OR IGNORE INTO model_pricing
                    (provider_type, model_name, input_per_million, output_per_million, source, updated_at)
                VALUES (:provider_type, :model_name, :input_rate, :output_rate, 'manual', :now)
                """
            ),
            {
                "provider_type": provider_type,
                "model_name": model_name,
                "input_rate": input_rate,
                "output_rate": output_rate,
                "now": now,
            },
        )


def get_price(engine, provider_type: str, model_name: str | None) -> tuple[float, float] | None:
    if not model_name:
        return None
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT input_per_million, output_per_million FROM model_pricing "
                "WHERE provider_type = :provider_type AND model_name = :model_name"
            ),
            {"provider_type": provider_type, "model_name": model_name},
        ).fetchone()
    if row is None or row.input_per_million is None or row.output_per_million is None:
        return None
    return (row.input_per_million, row.output_per_million)


def list_prices(engine) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM model_pricing ORDER BY provider_type, model_name")
        ).all()
    return [
        {
            "provider_type": row.provider_type,
            "model_name": row.model_name,
            "input_per_million": row.input_per_million,
            "output_per_million": row.output_per_million,
            "source": row.source,
            "updated_at": row.updated_at,
        }
        for row in rows
    ]


def upsert_price(
    engine, provider_type: str, model_name: str, input_per_million: float, output_per_million: float, source: str
) -> dict:
    now = _now()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO model_pricing
                    (provider_type, model_name, input_per_million, output_per_million, source, updated_at)
                VALUES (:provider_type, :model_name, :input_rate, :output_rate, :source, :now)
                ON CONFLICT(provider_type, model_name) DO UPDATE SET
                    input_per_million = :input_rate,
                    output_per_million = :output_rate,
                    source = :source,
                    updated_at = :now
                """
            ),
            {
                "provider_type": provider_type,
                "model_name": model_name,
                "input_rate": input_per_million,
                "output_rate": output_per_million,
                "source": source,
                "now": now,
            },
        )
    return {
        "provider_type": provider_type,
        "model_name": model_name,
        "input_per_million": input_per_million,
        "output_per_million": output_per_million,
        "source": source,
        "updated_at": now,
    }


# Maps a third-party pricing export's "<source>:<model id>" key prefix (see
# `import_catalog_prices()`) to this app's own `provider_type` values. Only
# sources this app actually has a provider for are listed -- an unmapped
# prefix (e.g. a reseller or a provider this app doesn't integrate) is
# silently skipped rather than guessed at.
_CATALOG_SOURCE_TO_PROVIDER_TYPE: dict[str, str] = {
    "openrouter": "openrouter",
    "google": "gemini",
    "fal": "fal",
    "mistral": "mistral",
}


def import_catalog_prices(engine, catalog: dict) -> dict:
    """Bulk-updates `model_pricing` from a third-party pricing export (user
    request -- rather than hand-editing each row after a price change,
    import a JSON price list like the one a site such as versecraft exports:
    `{"models": {"<source>:<model id>": {"kind": "text", "input": ...,
    "output": ..., ...}}}`, $/1M-token rates in the same units this table
    already uses).

    Only `"kind": "text"` entries with both rates present are usable here --
    `model_pricing` has no column for FAL/image/video's per-image or
    per-second pricing. And only models this app already knows about (a
    `model_pricing` row already exists, or a `provider_entries` row
    currently points a `vision_model`/`text_model` at it) are touched --
    importing a full third-party catalog verbatim would flood the table with
    hundreds of irrelevant rows, the same reasoning `refresh_openrouter_prices()`
    above already applies to OpenRouter's own catalog.
    """
    models = catalog.get("models") if isinstance(catalog, dict) else None
    if not isinstance(models, dict):
        raise ValueError("Catalog JSON has no 'models' object.")

    catalog_prices: dict[tuple[str, str], tuple[float, float]] = {}
    for key, entry in models.items():
        if not isinstance(entry, dict) or entry.get("kind") != "text":
            continue
        input_rate = entry.get("input")
        output_rate = entry.get("output")
        if input_rate is None or output_rate is None:
            continue
        source, _, model_id = key.partition(":")
        provider_type = _CATALOG_SOURCE_TO_PROVIDER_TYPE.get(source)
        if provider_type is None or not model_id:
            continue
        catalog_prices[(provider_type, model_id)] = (float(input_rate), float(output_rate))

    with engine.connect() as conn:
        known_rows = conn.execute(text("SELECT provider_type, model_name FROM model_pricing")).all()
        configured_rows = conn.execute(
            text(
                "SELECT provider_type, vision_model AS model FROM provider_entries WHERE vision_model IS NOT NULL "
                "UNION "
                "SELECT provider_type, text_model AS model FROM provider_entries WHERE text_model IS NOT NULL"
            )
        ).all()
    known_models = {(row.provider_type, row.model_name) for row in known_rows}
    known_models.update((row.provider_type, row.model) for row in configured_rows)

    updated = []
    unchanged = 0
    for provider_type, model_name in known_models:
        rates = catalog_prices.get((provider_type, model_name))
        if rates is None:
            continue
        if get_price(engine, provider_type, model_name) == rates:
            unchanged += 1
            continue
        upsert_price(engine, provider_type, model_name, rates[0], rates[1], "catalog_import")
        updated.append(
            {
                "provider_type": provider_type,
                "model_name": model_name,
                "input_per_million": rates[0],
                "output_per_million": rates[1],
            }
        )

    return {
        "updated": updated,
        "unchanged": unchanged,
        "pricing_version": catalog.get("pricing_version"),
    }


def refresh_openrouter_prices(engine) -> dict:
    """Fetches live pricing for every OpenRouter model currently configured
    on an enabled-or-not `provider_entries` row (`vision_model`/`text_model`)
    and upserts matches with `source='openrouter_api'`. Scoped to configured
    models rather than OpenRouter's full catalog (hundreds of models,
    mostly irrelevant here)."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT vision_model, text_model FROM provider_entries WHERE provider_type = 'openrouter'")
        ).all()
    model_ids = sorted({model for row in rows for model in (row.vision_model, row.text_model) if model})

    if not model_ids:
        return {"updated": [], "not_found": []}

    prices = openrouter.fetch_pricing(model_ids)
    updated = []
    for model_id in model_ids:
        rates = prices.get(model_id)
        if rates is None:
            continue
        upsert_price(engine, "openrouter", model_id, rates[0], rates[1], "openrouter_api")
        updated.append(model_id)

    not_found = [model_id for model_id in model_ids if model_id not in updated]
    return {"updated": updated, "not_found": not_found}


__all__ = [
    "seed_default_prices",
    "get_price",
    "list_prices",
    "upsert_price",
    "import_catalog_prices",
    "refresh_openrouter_prices",
]
