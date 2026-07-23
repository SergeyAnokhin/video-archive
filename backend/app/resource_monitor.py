"""Periodic CPU/memory sampler (chat request): the backend was being
OOMKilled repeatedly on Kubernetes (`kubectl describe pod` showed a real
container restart, not a false positive from `app.jobs.service.
reap_orphaned_jobs`), silently killing whatever job was running. There was
no way to see the memory trend leading up to a restart without cluster disk
access, so this samples `app.routers.system_stats.get_system_stats()` (same
whole-process-tree CPU/memory figures the frontend gauge already uses) on a
user-configurable interval and writes it to its own rotating log file
(`RESOURCE_LOG_FILE`, downloadable via `app.routers.log_files`).

Runs as a single daemon thread, mirroring `app.jobs.worker._Lane`'s
start/stop/loop shape. The interval (and enabled flag) are re-read from the
database every tick so a change made in Settings takes effect on the next
tick without a backend restart.
"""

from __future__ import annotations

import logging
import threading
import time

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
            if settings["enabled"] and now - last_sample >= settings["interval_seconds"]:
                self._sample()
                last_sample = now
            self._stop_event.wait(_POLL_INTERVAL_SECONDS)

    def _sample(self) -> None:
        stats = get_system_stats()
        _logger.info(
            "cpu_percent=%.1f memory_rss_mb=%.1f memory_percent=%.1f smb_bytes_transferred_total=%d",
            stats["cpu_percent"],
            stats["memory_rss_bytes"] / (1024 * 1024),
            stats["memory_percent"],
            stats["smb_bytes_transferred_total"],
        )
