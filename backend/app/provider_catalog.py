"""Cached per-provider model catalogs and the per-provider overview (user
request -- one API key per provider, entered once, and a model list that's
just there instead of a "Load models" click that needs the key every time).

Each provider type's model list is fetched with that provider's shared key
(`secrets_store.get_provider_api_key()`) and cached in
`provider_model_catalog`; `provider_catalog_status` records when it was last
fetched/attempted and the last error. A catalog is refreshed at most once
per `CATALOG_MAX_AGE` (user decision: once a day is enough) -- lazily, when
something asks for it -- or on demand (`force`), e.g. right after a key is
saved. A failed attempt keeps the previous catalog and also counts as a
check, so a bad key isn't retried on every settings open.

OpenRouter's catalog response carries pricing for every model, so its
refresh also overwrites prices of configured OpenRouter models
(`model_pricing.apply_openrouter_prices()`) -- that's the "prices update
daily" half of the same request. Gemini/Mistral publish no prices; FAL has
no catalog API at all (the frontend keeps a hand-picked list for it).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from app import model_pricing, provider_entries, secrets_store
from app.providers import openrouter, registry

CATALOG_MAX_AGE = timedelta(hours=24)
CATALOG_PROVIDER_TYPES = ("openrouter", "gemini", "mistral")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_status(engine, provider_type: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT fetched_at, checked_at, error FROM provider_catalog_status WHERE provider_type = :t"),
            {"t": provider_type},
        ).fetchone()
    return {"fetched_at": row.fetched_at, "checked_at": row.checked_at, "error": row.error} if row else None


def is_stale(status: dict | None, now: datetime | None = None) -> bool:
    if status is None:
        return True
    return (now or _now()) - datetime.fromisoformat(status["checked_at"]) >= CATALOG_MAX_AGE


def _write_status(conn, provider_type: str, checked_at: str, *, fetched_at: str | None, error: str | None) -> None:
    conn.execute(
        text(
            """
            INSERT INTO provider_catalog_status (provider_type, fetched_at, checked_at, error)
            VALUES (:t, :fetched_at, :checked_at, :error)
            ON CONFLICT(provider_type) DO UPDATE SET
                fetched_at = COALESCE(:fetched_at, fetched_at),
                checked_at = :checked_at,
                error = :error
            """
        ),
        {"t": provider_type, "fetched_at": fetched_at, "checked_at": checked_at, "error": error},
    )


def refresh_catalog(engine, provider_type: str) -> dict | None:
    """Fetches and caches `provider_type`'s catalog now. No-op (returns the
    current status) for a provider without a catalog API or without a key."""
    if provider_type not in CATALOG_PROVIDER_TYPES:
        return None
    api_key = secrets_store.get_provider_api_key(provider_type)
    if not api_key:
        return get_status(engine, provider_type)

    checked_at = _now().isoformat()
    try:
        if provider_type == "openrouter":
            catalog, all_rates = openrouter.fetch_catalog()
        else:
            catalog = [(model_id, None) for model_id in registry.list_models_for_provider_type(provider_type, api_key)]
            all_rates = None
    except registry.ProviderError as exc:
        # Gemini sends the key as a `?key=` query param and httpx errors
        # quote the URL -- never store/show it.
        error = str(exc).replace(api_key, "***")
        with engine.begin() as conn:
            _write_status(conn, provider_type, checked_at, fetched_at=None, error=error)
        return get_status(engine, provider_type)

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM provider_model_catalog WHERE provider_type = :t"), {"t": provider_type})
        for model_id, rates in catalog:
            conn.execute(
                text(
                    """
                    INSERT OR REPLACE INTO provider_model_catalog
                        (provider_type, model_id, input_per_million, output_per_million)
                    VALUES (:t, :model_id, :input_rate, :output_rate)
                    """
                ),
                {
                    "t": provider_type,
                    "model_id": model_id,
                    "input_rate": rates[0] if rates else None,
                    "output_rate": rates[1] if rates else None,
                },
            )
        _write_status(conn, provider_type, checked_at, fetched_at=checked_at, error=None)
    if all_rates is not None:
        model_pricing.apply_openrouter_prices(engine, all_rates)
    return get_status(engine, provider_type)


def refresh_stale(engine, *, force: bool = False) -> None:
    """Refreshes every keyed provider whose catalog is older than
    `CATALOG_MAX_AGE` (or all of them with `force`)."""
    for provider_type in CATALOG_PROVIDER_TYPES:
        if force or is_stale(get_status(engine, provider_type)):
            refresh_catalog(engine, provider_type)


def get_catalog(engine, provider_type: str, *, refresh_if_stale: bool = True) -> dict:
    if refresh_if_stale and is_stale(get_status(engine, provider_type)):
        refresh_catalog(engine, provider_type)
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM provider_model_catalog WHERE provider_type = :t ORDER BY model_id"),
            {"t": provider_type},
        ).all()
    status = get_status(engine, provider_type) or {"fetched_at": None, "checked_at": None, "error": None}
    return {
        "provider_type": provider_type,
        "models": [
            {
                "model_id": row.model_id,
                "input_per_million": row.input_per_million,
                "output_per_million": row.output_per_million,
            }
            for row in rows
        ],
        **status,
    }


def fill_missing_prices(engine, provider_type: str, model_ids: list[str | None]) -> None:
    """Gives a newly configured model the catalog's price when it has none
    yet (only OpenRouter's catalog carries prices). Doesn't refresh the
    catalog -- the daily refresh overwrites prices anyway."""
    for model_id in model_ids:
        if not model_id or model_pricing.get_price(engine, provider_type, model_id) is not None:
            continue
        with engine.connect() as conn:
            row = conn.execute(
                text(
                    "SELECT input_per_million, output_per_million FROM provider_model_catalog "
                    "WHERE provider_type = :t AND model_id = :model_id"
                ),
                {"t": provider_type, "model_id": model_id},
            ).fetchone()
        if row is not None and row.input_per_million is not None and row.output_per_million is not None:
            model_pricing.upsert_price(
                engine, provider_type, model_id, row.input_per_million, row.output_per_million, "openrouter_api"
            )


def list_provider_statuses(engine) -> list[dict]:
    """One row per provider type for the Settings "Providers" block: key
    presence/suffix, cached catalog size and freshness, and whether the
    one-key-per-provider migration left a different old key behind."""
    with engine.connect() as conn:
        counts = dict(
            conn.execute(
                text("SELECT provider_type, COUNT(*) FROM provider_model_catalog GROUP BY provider_type")
            ).all()
        )
    statuses = []
    for provider_type in provider_entries.PROVIDER_TYPES:
        status = get_status(engine, provider_type) or {"fetched_at": None, "checked_at": None, "error": None}
        statuses.append(
            {
                "provider_type": provider_type,
                "has_api_key": secrets_store.get_provider_api_key(provider_type) is not None,
                "key_suffix": secrets_store.get_provider_api_key_suffix(provider_type),
                "catalog_supported": provider_type in CATALOG_PROVIDER_TYPES,
                "catalog_count": counts.get(provider_type, 0),
                **status,
                "legacy_key_conflict": secrets_store.legacy_entry_keys_differ(
                    provider_type, provider_entries.entry_ids_by_type(engine, provider_type)
                ),
            }
        )
    return statuses
