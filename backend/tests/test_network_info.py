"""Network-access info tests (post-V1, user request -- "connect from a phone
on the same network / phone hotspot"): the `GET /api/app/network-info`
endpoint and its underlying `app.network_info.get_lan_addresses()` helper.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.db as db_module
from app.main import app
from app.network_info import get_lan_addresses


def test_get_lan_addresses_returns_ipv4_strings():
    addresses = get_lan_addresses()
    assert isinstance(addresses, list)
    for address in addresses:
        assert isinstance(address, str)
        assert not address.startswith("127.")
        # Four dot-separated octets -- a cheap IPv4 shape check.
        assert len(address.split(".")) == 4


def test_network_info_over_http(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DATABASE_PATH", tmp_path / "test.db")
    monkeypatch.setattr(db_module, "_engine", None)

    with TestClient(app) as client:
        r = client.get("/api/app/network-info")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["lan_addresses"], list)
        assert body["frontend_port"] == 5173
        assert isinstance(body["backend_port"], int)
