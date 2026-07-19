"""`GET /api/system/stats` (backend resource indicator, chat request
2026-07-19): exposes CPU/memory via `psutil` and cumulative SMB bytes
transferred via `app.sources.smb_stats`, polled every 5s by the frontend
widget.

CPU/memory must cover the whole process tree, not just the uvicorn worker --
conversion/preview/tagging jobs shell out to ffmpeg as a child process,
where nearly all the CPU actually goes (chat request 2026-07-19 follow-up:
measuring only the worker process left the gauge sitting near 0% during a
real conversion, confirmed against `k9s`'s view of the Kubernetes pod)."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.db as db_module
import app.routers.system_stats as system_stats_module
from app.main import app


def _isolated_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)
    return TestClient(app)


class _FakeChildProcess:
    """Stands in for a real ffmpeg child process without spawning one --
    fixed memory/cpu readings, isolated from real system noise."""

    def __init__(self, pid: int, rss: int, cpu_percent: float):
        self.pid = pid
        self._rss = rss
        self._cpu_percent = cpu_percent

    def memory_info(self):
        return SimpleNamespace(rss=self._rss)

    def cpu_percent(self, interval=None):
        return self._cpu_percent


def test_system_stats_shape(tmp_path, monkeypatch):
    with _isolated_client(tmp_path, monkeypatch) as client:
        resp = client.get("/api/system/stats")

    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["cpu_percent"], (int, float))
    assert body["cpu_percent"] >= 0
    assert isinstance(body["memory_rss_bytes"], int)
    assert body["memory_rss_bytes"] > 0
    assert isinstance(body["memory_percent"], (int, float))
    assert body["memory_percent"] >= 0
    assert isinstance(body["smb_bytes_transferred_total"], int)
    assert body["smb_bytes_transferred_total"] >= 0
    assert isinstance(body["timestamp"], (int, float))


def test_system_stats_sums_child_process_memory_and_cpu(tmp_path, monkeypatch):
    real_process = system_stats_module._process
    monkeypatch.setattr(system_stats_module, "_tracked", {real_process.pid: real_process})

    fake_child = _FakeChildProcess(pid=999_999, rss=50_000_000, cpu_percent=42.0)
    monkeypatch.setattr(real_process, "children", lambda recursive=False: [fake_child])

    with _isolated_client(tmp_path, monkeypatch) as client:
        # First poll discovers and primes the child -- its cpu_percent() is
        # deliberately not read again in the same request (see
        # get_system_stats()'s `just_primed` guard), but memory is a
        # point-in-time read with no such priming quirk, so it counts
        # immediately.
        first = client.get("/api/system/stats").json()
        second = client.get("/api/system/stats").json()

    assert first["memory_rss_bytes"] >= fake_child._rss
    assert second["cpu_percent"] > 0
