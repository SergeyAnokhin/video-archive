"""Per-call AI provider usage log (user request -- "see usage statistics for
model requests, which models were used across the whole app"). Every
tagging request (sync or batch) is logged here by
`app/providers/registry.py` right after the provider call returns or
raises, so failed attempts are counted too, not just successful ones.

Token counts are only as good as what the provider's response exposes:
Gemini/Mistral/OpenRouter return usage metadata the provider clients parse
(see `app/providers/{gemini,mistral,openrouter}.py`), FAL does not (no
fixed response schema -- see `app/providers/fal.py`), so its rows always
have `tokens_in`/`tokens_out` `NULL`. Cost is then estimated from the
editable, sourced per-model rate table in `app/model_pricing.py` -- treat
it as a rough estimate that can drift as vendors reprice, not a
billing-accurate figure -- and is `NULL` for any (provider_type,
model_name) pair with no price on file (including FAL's, always, since it
has no live pricing source and isn't seeded).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import text

from app import model_pricing


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def estimate_cost_usd(
    engine, provider_type: str | None, model_name: str | None, tokens_in: int | None, tokens_out: int | None
) -> float | None:
    if not provider_type or not model_name or tokens_in is None or tokens_out is None:
        return None
    rates = model_pricing.get_price(engine, provider_type, model_name)
    if rates is None:
        return None
    input_rate, output_rate = rates
    return round((tokens_in / 1_000_000) * input_rate + (tokens_out / 1_000_000) * output_rate, 6)


def log_usage(
    engine,
    *,
    provider_type: str,
    model_name: str | None,
    request_kind: str,
    success: bool,
    item_count: int = 1,
    tokens_in: int | None = None,
    tokens_out: int | None = None,
    error_message: str | None = None,
    job_id: str | None = None,
) -> None:
    """Records one provider call. Never raises on its own account -- callers
    (the fallback/batch dispatch in `app/providers/registry.py`) log this
    around a call that may itself be failing, so a logging bug must not mask
    or replace the real provider error."""
    cost = estimate_cost_usd(engine, provider_type, model_name, tokens_in, tokens_out)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO provider_usage_log (
                    id, provider_type, model_name, request_kind, success, item_count,
                    tokens_in, tokens_out, estimated_cost_usd, error_message, job_id, created_at
                ) VALUES (
                    :id, :provider_type, :model_name, :request_kind, :success, :item_count,
                    :tokens_in, :tokens_out, :estimated_cost_usd, :error_message, :job_id, :now
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "provider_type": provider_type,
                "model_name": model_name,
                "request_kind": request_kind,
                "success": success,
                "item_count": item_count,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "estimated_cost_usd": cost,
                "error_message": error_message,
                "job_id": job_id,
                "now": _now(),
            },
        )


def get_usage_summary(engine) -> list[dict]:
    """One row per (provider_type, model_name) actually used, aggregated
    across every logged call, newest-last-used-first -- for the Settings
    usage stats table."""
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT provider_type, model_name,
                       COUNT(*) AS call_count,
                       SUM(CASE WHEN success THEN 1 ELSE 0 END) AS success_count,
                       SUM(item_count) AS total_items,
                       SUM(tokens_in) AS total_tokens_in,
                       SUM(tokens_out) AS total_tokens_out,
                       SUM(estimated_cost_usd) AS total_estimated_cost_usd,
                       MAX(created_at) AS last_used_at
                FROM provider_usage_log
                GROUP BY provider_type, model_name
                ORDER BY last_used_at DESC
                """
            )
        ).all()
    return [
        {
            "provider_type": row.provider_type,
            "model_name": row.model_name,
            "call_count": row.call_count,
            "success_count": row.success_count,
            "total_items": row.total_items,
            "total_tokens_in": row.total_tokens_in,
            "total_tokens_out": row.total_tokens_out,
            "total_estimated_cost_usd": row.total_estimated_cost_usd,
            "last_used_at": row.last_used_at,
        }
        for row in rows
    ]
