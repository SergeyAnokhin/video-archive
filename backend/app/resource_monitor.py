"""Periodic CPU/memory sampler (chat request): the backend was being
OOMKilled repeatedly on Kubernetes (`kubectl describe pod` showed a real
container restart, not a false positive from `app.jobs.service.
reap_orphaned_jobs`), silently killing whatever job was running. There was
no way to see the memory trend leading up to a restart without cluster disk
access, so this samples `app.routers.system_stats.get_system_stats()` (same
whole-process-tree CPU/memory figures the frontend gauge already uses) on a
user-configurable interval.

Every sample is written to `resource_monitor_samples`
(`app.resource_monitor_history`) for the Settings -> Performance history
chart, unconditionally -- the `enabled` setting only gates the extra
`backend.log` line (prefixed with 📊, downloadable via `app.routers.
log_files`), so history keeps recording at the configured interval even
when logging is turned off (chat request 2026-07-25: users wanted to quiet
the log without losing the chart data). `smb_bytes_transferred_total` is a
cumulative counter, so the per-second network rate is derived here from the
delta against the previous sample, mirroring how the frontend's own live
gauge derives it (`frontend/src/utils/backendStats.ts`).

Runs as a single daemon thread, mirroring `app.jobs.worker._Lane`'s
start/stop/loop shape. The interval and enabled flag are re-read from the
database every tick so a change made in Settings takes effect on the next
tick without a backend restart.
"""

from __future__ import annotations

import logging
import threading
import time

from app import resource_monitor_history as history_service
from app import resource_monitor_settings as settings_service
from app.db import get_engine
from app.logging_config import RESOURCE_MONITOR_LOGGER_NAME
from app.routers.system_stats import get_system_stats

_POLL_INTERVAL_SECONDS = 1.0

_logger = logging.getLogger(RESOURCE_MONITOR_LOGGER_NAME)


class ResourceMonitor:
    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._prev_smb_bytes: int | None = None
        self._prev_timestamp: float | None = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="resource-monitor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        engine = get_engine()
        last_sample = 0.0

        while not self._stop_event.is_set():
            settings = settings_service.get_settings(engine)
            now = time.monotonic()
            if now - last_sample >= settings["interval_seconds"]:
                self._sample(engine, log_enabled=settings["enabled"])
                last_sample = now
            self._stop_event.wait(_POLL_INTERVAL_SECONDS)

    def _sample(self, engine, log_enabled: bool) -> None:
        stats = get_system_stats()
        if log_enabled:
            _logger.info(
                "📊 cpu_percent=%.1f memory_rss_mb=%.1f memory_percent=%.1f smb_bytes_transferred_total=%d",
                stats["cpu_percent"],
                stats["memory_rss_bytes"] / (1024 * 1024),
                stats["memory_percent"],
                stats["smb_bytes_transferred_total"],
            )

        timestamp = stats["timestamp"]
        network_bytes_per_sec = 0.0
        if self._prev_timestamp is not None and self._prev_smb_bytes is not None:
            elapsed = timestamp - self._prev_timestamp
            delta = stats["smb_bytes_transferred_total"] - self._prev_smb_bytes
            # A backend restart resets the cumulative counter -- a negative
            # delta would otherwise read as a (nonsensical) negative rate.
            if elapsed > 0 and delta >= 0:
                network_bytes_per_sec = delta / elapsed
        self._prev_timestamp = timestamp
        self._prev_smb_bytes = stats["smb_bytes_transferred_total"]

        history_service.record_sample(
            engine,
            timestamp=timestamp,
            cpu_percent=stats["cpu_percent"],
            memory_percent=stats["memory_percent"],
            network_bytes_per_sec=network_bytes_per_sec,
        )
