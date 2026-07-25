"""Historical CPU/memory/network samples backing the Settings -> Performance
history chart (chat request 2026-07-25). `app/resource_monitor.py` writes one
row per sample (same cadence as its own `interval_seconds` setting) via
`record_sample()`, which also prunes anything older than `RETENTION_SECONDS`
so the table never grows past ~24h of data -- there's no UI need for more
than that, since the longest selectable chart range is 24h.

CPU/memory are already 0-100 percentages of a natural ceiling (see
`app/routers/system_stats.py`), but network throughput has no such ceiling,
so it's normalized here against the highest throughput seen in the last 24h
(`network_scale_bytes_per_sec` in `get_history()`'s response) rather than a
fixed cap.

A range with more raw samples than `MAX_CHART_POINTS` is downsampled into
fixed-width buckets, one point per bucket -- by request, this takes the max
of each parameter within the bucket rather than averaging, so a brief spike
stays visible instead of being smoothed away.
"""

from __future__ import annotations

import time

from sqlalchemy import text

RETENTION_SECONDS = 24 * 60 * 60
MAX_CHART_POINTS = 200

# Matches the range options offered in Settings -> Performance.
ALLOWED_RANGE_SECONDS = {
    "30m": 30 * 60,
    "4h": 4 * 60 * 60,
    "12h": 12 * 60 * 60,
    "24h": 24 * 60 * 60,
}


def record_sample(engine, timestamp: float, cpu_percent: float, memory_percent: float, network_bytes_per_sec: float) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO resource_monitor_samples "
                "(timestamp, cpu_percent, memory_percent, network_bytes_per_sec) "
                "VALUES (:timestamp, :cpu, :memory, :network)"
            ),
            {"timestamp": timestamp, "cpu": cpu_percent, "memory": memory_percent, "network": network_bytes_per_sec},
        )
        conn.execute(
            text("DELETE FROM resource_monitor_samples WHERE timestamp < :cutoff"),
            {"cutoff": timestamp - RETENTION_SECONDS},
        )


def _fetch_rows(conn, since: float) -> list[dict]:
    rows = conn.execute(
        text(
            "SELECT timestamp, cpu_percent, memory_percent, network_bytes_per_sec "
            "FROM resource_monitor_samples WHERE timestamp >= :since ORDER BY timestamp ASC"
        ),
        {"since": since},
    ).fetchall()
    return [
        {
            "timestamp": row.timestamp,
            "cpu_percent": row.cpu_percent,
            "memory_percent": row.memory_percent,
            "network_bytes_per_sec": row.network_bytes_per_sec,
        }
        for row in rows
    ]


def get_history(engine, range_seconds: int) -> dict:
    now = time.time()
    since = now - range_seconds
    day_ago = now - RETENTION_SECONDS

    with engine.connect() as conn:
        rows = _fetch_rows(conn, since)
        # Network is always scaled against the full last-24h max, not just
        # the currently-selected range, per request -- widen the query only
        # when the selected range is actually narrower than that.
        day_rows = rows if since <= day_ago else _fetch_rows(conn, day_ago)

    network_scale = max((row["network_bytes_per_sec"] for row in day_rows), default=0.0)

    def to_point(bucket_timestamp: float, cpu_percent: float, memory_percent: float, network_bytes_per_sec: float) -> dict:
        network_percent = (network_bytes_per_sec / network_scale * 100) if network_scale > 0 else 0.0
        return {
            "timestamp": bucket_timestamp,
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "network_percent": min(100.0, network_percent),
        }

    if len(rows) <= MAX_CHART_POINTS:
        points = [
            to_point(row["timestamp"], row["cpu_percent"], row["memory_percent"], row["network_bytes_per_sec"])
            for row in rows
        ]
        return {"range_seconds": range_seconds, "network_scale_bytes_per_sec": network_scale, "points": points}

    bucket_seconds = range_seconds / MAX_CHART_POINTS
    buckets: dict[int, list[dict]] = {}
    for row in rows:
        index = int((row["timestamp"] - since) // bucket_seconds)
        buckets.setdefault(index, []).append(row)

    points = []
    for index in sorted(buckets):
        bucket_rows = buckets[index]
        bucket_center = since + (index + 0.5) * bucket_seconds
        points.append(
            to_point(
                bucket_center,
                max(r["cpu_percent"] for r in bucket_rows),
                max(r["memory_percent"] for r in bucket_rows),
                max(r["network_bytes_per_sec"] for r in bucket_rows),
            )
        )

    return {"range_seconds": range_seconds, "network_scale_bytes_per_sec": network_scale, "points": points}
