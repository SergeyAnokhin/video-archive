"""`GET /api/health` and `GET /api/health/thread-dump`.

The thread dump is the diagnostic added after a `convert` job was observed
logging its `job_parameters` line and then going silent indefinitely, with
the SMB lock indicator reporting itself free -- the missing log lines narrow
the hang to a handful of statements, but only a stack names the blocking
call.
"""

from __future__ import annotations

import threading

from fastapi.testclient import TestClient

import app.db as db_module
from app.main import app


def _isolated_client(tmp_path, monkeypatch) -> TestClient:
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)
    return TestClient(app)


def test_health_ok(tmp_path, monkeypatch):
    with _isolated_client(tmp_path, monkeypatch) as client:
        assert client.get("/api/health").json() == {"status": "ok"}


def test_thread_dump_names_threads_and_their_stacks(tmp_path, monkeypatch):
    parked = threading.Event()
    release = threading.Event()

    def _parked_thread():
        parked.set()
        release.wait(timeout=10)

    thread = threading.Thread(target=_parked_thread, name="test-parked-thread", daemon=True)
    thread.start()
    try:
        assert parked.wait(timeout=5)
        with _isolated_client(tmp_path, monkeypatch) as client:
            body = client.get("/api/health/thread-dump").json()

        by_name = {entry["name"]: entry for entry in body["threads"]}
        assert "test-parked-thread" in by_name
        stack = "\n".join(by_name["test-parked-thread"]["stack"])
        # The frame the thread is actually blocked in, which is the whole
        # point of the endpoint.
        assert "release.wait" in stack
    finally:
        release.set()
        thread.join(timeout=5)
