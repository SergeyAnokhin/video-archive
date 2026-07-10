"""Small, local accounting ledger for AI tagging calls.

It deliberately records request/file/batch counts, not API keys, prompts or
image bytes.  The same table also makes the configured model choice visible
after a provider entry has been edited or deleted.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import text


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record(engine, provider_name: str, model_name: str | None, *, requests: int, files: int, batches: int = 0) -> None:
    model = model_name or "(provider default)"
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO model_usage (provider_name, model_name, request_count, file_count, batch_count, last_used_at)
                VALUES (:provider, :model, :requests, :files, :batches, :now)
                ON CONFLICT(provider_name, model_name) DO UPDATE SET
                  request_count = request_count + excluded.request_count,
                  file_count = file_count + excluded.file_count,
                  batch_count = batch_count + excluded.batch_count,
                  last_used_at = excluded.last_used_at
                """
            ),
            {"provider": provider_name, "model": model, "requests": requests, "files": files, "batches": batches, "now": _now()},
        )


def list_usage(engine) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM model_usage ORDER BY last_used_at DESC")).all()
    return [dict(row._mapping) for row in rows]
