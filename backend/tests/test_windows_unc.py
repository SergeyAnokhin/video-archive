"""Tests for `app.sources.windows_unc`: the Windows-only capability probe
behind the SMB source's opt-in "direct access" fast path. Mirrors
`test_hardware_accel.py`'s convention of mocking the actual probe (here,
`net use`) so these don't depend on real OS/network state.
"""

from __future__ import annotations

from app.sources import windows_unc


def setup_function(_fn):
    windows_unc.reset_cache()


def teardown_function(_fn):
    windows_unc.reset_cache()


def test_is_supported_reflects_os_name(monkeypatch):
    monkeypatch.setattr(windows_unc.os, "name", "nt")
    assert windows_unc.is_supported() is True
    monkeypatch.setattr(windows_unc.os, "name", "posix")
    assert windows_unc.is_supported() is False


def test_available_false_on_non_windows(monkeypatch):
    monkeypatch.setattr(windows_unc.os, "name", "posix")
    monkeypatch.setattr(windows_unc, "_net_use", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not run")))
    assert windows_unc.available("nas", "share", "user", "pw") is False


def test_available_caches_result(monkeypatch):
    monkeypatch.setattr(windows_unc.os, "name", "nt")
    call_count = {"n": 0}

    def fake_net_use(host, share, username, password):
        call_count["n"] += 1
        return True

    monkeypatch.setattr(windows_unc, "_net_use", fake_net_use)

    assert windows_unc.available("nas", "share", "user", "pw") is True
    assert windows_unc.available("nas", "share", "user", "pw") is True
    assert call_count["n"] == 1  # served from cache the second time

    assert windows_unc.available("nas", "share", "user", "pw", force=True) is True
    assert call_count["n"] == 2


def test_available_false_when_net_use_fails(monkeypatch):
    # Covers the credential-conflict case (Windows error 1219) alongside any
    # other net use failure -- `_net_use` already collapses all of those to
    # a plain False, never raising.
    monkeypatch.setattr(windows_unc.os, "name", "nt")
    monkeypatch.setattr(windows_unc, "_net_use", lambda *a, **k: False)
    assert windows_unc.available("nas", "share", "user", "pw") is False


def test_report_failure_forces_immediate_recheck(monkeypatch):
    monkeypatch.setattr(windows_unc.os, "name", "nt")
    results = iter([True, False])
    monkeypatch.setattr(windows_unc, "_net_use", lambda *a, **k: next(results))

    assert windows_unc.available("nas", "share", "user", "pw") is True
    windows_unc.report_failure("nas", "user")
    # Cache entry invalidated -- the very next call re-probes rather than
    # trusting the cached positive for up to `_RECHECK_OK_SECONDS`.
    assert windows_unc.available("nas", "share", "user", "pw") is False


def test_available_recheck_cadence_differs_for_ok_vs_fail(monkeypatch):
    monkeypatch.setattr(windows_unc.os, "name", "nt")
    fake_now = {"t": 0.0}
    monkeypatch.setattr(windows_unc.time, "monotonic", lambda: fake_now["t"])
    call_count = {"n": 0}

    def fake_net_use(host, share, username, password):
        call_count["n"] += 1
        return False

    monkeypatch.setattr(windows_unc, "_net_use", fake_net_use)

    assert windows_unc.available("nas", "share", "user", "pw") is False
    assert call_count["n"] == 1

    # Still within the failure TTL -- served from cache.
    fake_now["t"] += windows_unc._RECHECK_FAIL_SECONDS - 1
    windows_unc.available("nas", "share", "user", "pw")
    assert call_count["n"] == 1

    # Past the failure TTL -- re-probes.
    fake_now["t"] += 2
    windows_unc.available("nas", "share", "user", "pw")
    assert call_count["n"] == 2


def test_net_use_never_raises_on_subprocess_failure(monkeypatch):
    def fake_run(*args, **kwargs):
        raise OSError("net use not found")

    monkeypatch.setattr(windows_unc.subprocess, "run", fake_run)
    assert windows_unc._net_use("nas", "share", "user", "pw") is False
