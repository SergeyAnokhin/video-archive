"""Resource-monitor sampler tests (chat request 2026-07-25): `enabled` in
`app/resource_monitor_settings.py` was decoupled to only gate the extra
`backend.log` line -- history recording into `resource_monitor_samples`
(`app/resource_monitor_history.py`) must keep happening either way.
"""

from __future__ import annotations

import logging
import time

import app.resource_monitor as resource_monitor_module
from app import resource_monitor_history
from app.logging_config import RESOURCE_MONITOR_LOGGER_NAME
from app.resource_monitor import ResourceMonitor


def _fake_stats() -> dict:
    return {
        "cpu_percent": 12.5,
        "memory_rss_bytes": 100 * 1024 * 1024,
        "memory_percent": 4.0,
        "smb_bytes_transferred_total": 1000,
        "timestamp": time.time(),
    }


def test_sample_always_records_history_even_when_log_disabled(engine, monkeypatch, caplog):
    monkeypatch.setattr(resource_monitor_module, "get_system_stats", _fake_stats)
    monitor = ResourceMonitor()

    with caplog.at_level(logging.INFO, logger=RESOURCE_MONITOR_LOGGER_NAME):
        monitor._sample(engine, log_enabled=False)

    assert "cpu_percent" not in caplog.text
    history = resource_monitor_history.get_history(engine, resource_monitor_history.ALLOWED_RANGE_SECONDS["24h"])
    assert len(history["points"]) == 1
    assert history["points"][0]["cpu_percent"] == 12.5


def test_sample_logs_when_enabled(engine, monkeypatch, caplog):
    monkeypatch.setattr(resource_monitor_module, "get_system_stats", _fake_stats)
    monitor = ResourceMonitor()

    with caplog.at_level(logging.INFO, logger=RESOURCE_MONITOR_LOGGER_NAME):
        monitor._sample(engine, log_enabled=True)

    assert "cpu_percent=12.5" in caplog.text
    history = resource_monitor_history.get_history(engine, resource_monitor_history.ALLOWED_RANGE_SECONDS["24h"])
    assert len(history["points"]) == 1
