"""Resource-monitor history tests (chat request 2026-07-25): the Settings ->
Performance CPU/memory/network chart's storage/query layer
(`app/resource_monitor_history.py`) and its endpoint
(`app/routers/resource_monitor_history.py`).
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

import app.db as db_module
from app import resource_monitor_history
from app.main import app


def test_get_history_returns_raw_points_when_under_the_bucket_threshold(engine):
    now = time.time()
    resource_monitor_history.record_sample(engine, now - 60, cpu_percent=10.0, memory_percent=20.0, network_bytes_per_sec=100.0)
    resource_monitor_history.record_sample(engine, now - 30, cpu_percent=15.0, memory_percent=25.0, network_bytes_per_sec=200.0)
    resource_monitor_history.record_sample(engine, now, cpu_percent=5.0, memory_percent=30.0, network_bytes_per_sec=50.0)

    result = resource_monitor_history.get_history(engine, resource_monitor_history.ALLOWED_RANGE_SECONDS["30m"])

    assert len(result["points"]) == 3
    assert result["network_scale_bytes_per_sec"] == 200.0
    # network_percent is normalized against the 24h max (200.0 here), not a fixed ceiling.
    assert result["points"][0]["network_percent"] == 50.0
    assert result["points"][1]["network_percent"] == 100.0
    assert result["points"][2]["cpu_percent"] == 5.0


def test_get_history_downsamples_with_max_not_average(engine):
    now = time.time()
    # 300 samples spread over the last hour -- comfortably over MAX_CHART_POINTS.
    for i in range(300):
        resource_monitor_history.record_sample(
            engine,
            now - 3600 + i * 12,
            cpu_percent=1.0 if i != 150 else 99.0,  # one sharp spike in the middle
            memory_percent=10.0,
            network_bytes_per_sec=1.0,
        )

    result = resource_monitor_history.get_history(engine, resource_monitor_history.ALLOWED_RANGE_SECONDS["4h"])

    assert len(result["points"]) <= resource_monitor_history.MAX_CHART_POINTS
    # Averaging would have smoothed the spike well below 99 -- max-aggregation must preserve it.
    assert max(p["cpu_percent"] for p in result["points"]) == 99.0


def test_record_sample_prunes_samples_older_than_24h(engine):
    now = time.time()
    resource_monitor_history.record_sample(engine, now - 25 * 3600, cpu_percent=1.0, memory_percent=1.0, network_bytes_per_sec=1.0)
    resource_monitor_history.record_sample(engine, now, cpu_percent=2.0, memory_percent=2.0, network_bytes_per_sec=2.0)

    result = resource_monitor_history.get_history(engine, resource_monitor_history.ALLOWED_RANGE_SECONDS["24h"])

    assert len(result["points"]) == 1
    assert result["points"][0]["cpu_percent"] == 2.0


def test_get_history_with_no_samples_returns_empty_points(engine):
    result = resource_monitor_history.get_history(engine, resource_monitor_history.ALLOWED_RANGE_SECONDS["24h"])

    assert result["points"] == []
    assert result["network_scale_bytes_per_sec"] == 0.0


def test_resource_monitor_history_over_http(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.get("/api/resource-monitor-history")
        assert r.status_code == 200
        assert r.json()["range_seconds"] == resource_monitor_history.ALLOWED_RANGE_SECONDS["24h"]

        r = client.get("/api/resource-monitor-history?range=30m")
        assert r.status_code == 200
        assert r.json()["range_seconds"] == resource_monitor_history.ALLOWED_RANGE_SECONDS["30m"]

        r = client.get("/api/resource-monitor-history?range=bogus")
        assert r.status_code == 422
