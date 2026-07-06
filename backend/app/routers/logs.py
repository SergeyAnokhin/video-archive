"""Log/event endpoints (API §12): recent events plus a near-real-time SSE
stream, both filterable by job, file, and level (UI Screens §4).
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query, Request
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import text

from app.db import get_engine

router = APIRouter()

_POLL_INTERVAL_SECONDS = 0.5


def _event_row_to_dict(row) -> dict:
    return {
        "id": row.id,
        "job_id": row.job_id,
        "file_id": row.file_id,
        "level": row.level,
        "event_type": row.event_type,
        "message": row.message,
        "payload": json.loads(row.payload) if row.payload else None,
        "created_at": row.created_at,
    }


def _filter_clauses(job_id: str | None, file_id: str | None, level: str | None) -> tuple[list[str], dict]:
    clauses = []
    params: dict = {}
    if job_id:
        clauses.append("job_id = :job_id")
        params["job_id"] = job_id
    if file_id:
        clauses.append("file_id = :file_id")
        params["file_id"] = file_id
    if level:
        clauses.append("level = :level")
        params["level"] = level
    return clauses, params


@router.get("/logs")
def get_logs(
    job_id: str | None = Query(default=None),
    file_id: str | None = Query(default=None),
    level: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
):
    clauses, params = _filter_clauses(job_id, file_id, level)
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    params["limit"] = limit

    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(f"SELECT rowid AS seq, * FROM app_events {where_sql} ORDER BY rowid DESC LIMIT :limit"),
            params,
        ).all()

    return {"events": [_event_row_to_dict(row) for row in reversed(rows)]}


@router.get("/logs/stream")
async def stream_logs(
    request: Request,
    job_id: str | None = Query(default=None),
    file_id: str | None = Query(default=None),
    level: str | None = Query(default=None),
):
    engine = get_engine()

    async def event_generator():
        with engine.connect() as conn:
            last_seq = conn.execute(text("SELECT COALESCE(MAX(rowid), 0) AS max_seq FROM app_events")).fetchone().max_seq

        while True:
            if await request.is_disconnected():
                break

            clauses, params = _filter_clauses(job_id, file_id, level)
            clauses.append("rowid > :after")
            params["after"] = last_seq
            where_sql = " AND ".join(clauses)

            with engine.connect() as conn:
                rows = conn.execute(
                    text(f"SELECT rowid AS seq, * FROM app_events WHERE {where_sql} ORDER BY rowid ASC"),
                    params,
                ).all()

            for row in rows:
                last_seq = row.seq
                yield {"event": "log", "data": json.dumps(_event_row_to_dict(row))}

            await asyncio.sleep(_POLL_INTERVAL_SECONDS)

    return EventSourceResponse(event_generator())
