"""Shared helper for browsing endpoints that require an active source."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text


def get_active_source_or_404(conn):
    row = conn.execute(text("SELECT * FROM sources WHERE is_active = 1 LIMIT 1")).fetchone()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": {"code": "no_source_configured", "message": "No active source is configured."}},
        )
    return row
