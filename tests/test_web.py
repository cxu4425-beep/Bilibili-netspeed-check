"""The read-only dashboard a phone on the same network can open."""

import json
import urllib.error
import urllib.request

import pytest

from lagscope import web
from lagscope.web import DashboardServer, dashboard_urls, local_addresses


@pytest.fixture
def server():
    instance = DashboardServer(port=0, bind_host="127.0.0.1")
    assert instance.start()
    # Port 0 lets the OS pick a free one; read it back for the requests.
    instance.port = instance._server.server_address[1]
    yield instance
    instance.stop()


def _get(port, path, key=None):
    url = f"http://127.0.0.1:{port}{path}"
    if key is not None:
        url += f"?key={key}"
    with urllib.request.urlopen(url, timeout=3) as response:
        return response.status, response.headers, response.read()


# ------------------------------------------------------------------ addresses
def test_local_addresses_are_usable_lan_addresses():
    for address in local_addresses():
        assert not address.startswith("127.")
        assert address.count(".") == 3


def test_urls_carry_the_access_code_so_the_link_just_works(monkeypatch):
    monkeypatch.setattr(web, "local_addresses", lambda: ["192.168.1.20"])
    assert dashboard_urls(23125, "4321") == ["http://192.168.1.20:23125/?key=4321"]
    assert dashboard_urls(23125) == ["http://192.168.1.20:23125/"]


# --------------------------------------------------------------------- pages
def test_the_page_is_self_contained(server):
    status, headers, body = _get(server.port, "/")
    page = body.decode("utf-8")

    assert status == 200 and "text/html" in headers["Content-Type"]
    # A phone may be on a network with no internet at all; nothing may be fetched.
    assert "http://" not in page.replace("http://127.0.0.1", "")
    assert "<script" in page and "fetch(" in page


def test_state_is_served_as_json(server):
    server.publish({"ok": True, "total_ms": 42.0, "rows": [], "stats": []})
    status, headers, body = _get(server.port, "/api/state")
    data = json.loads(body)

    assert status == 200 and "application/json" in headers["Content-Type"]
    assert data["total_ms"] == 42.0


def test_state_is_never_cached(server):
    _status, headers, _body = _get(server.port, "/api/state")
    assert headers["Cache-Control"] == "no-store"


def test_an_unknown_path_is_a_404(server):
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        _get(server.port, "/admin")
    assert excinfo.value.code == 404


# ------------------------------------------------------------------ the code
def test_the_access_code_gates_the_data():
    instance = DashboardServer(port=0, access_code="4321", bind_host="127.0.0.1")
    assert instance.start()
    instance.port = instance._server.server_address[1]
    try:
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _get(instance.port, "/api/state")
        assert excinfo.value.code == 403

        with pytest.raises(urllib.error.HTTPError):
            _get(instance.port, "/api/state", key="wrong")

        status, _headers, body = _get(instance.port, "/api/state", key="4321")
        assert status == 200 and json.loads(body) == {"ok": False}
    finally:
        instance.stop()


# ------------------------------------------------------------------ lifecycle
def test_publish_replaces_the_whole_snapshot(server):
    server.publish({"ok": True, "total_ms": 1.0})
    server.publish({"ok": True, "total_ms": 2.0})
    _status, _headers, body = _get(server.port, "/api/state")
    assert json.loads(body)["total_ms"] == 2.0


def test_starting_twice_is_harmless_and_stopping_twice_too(server):
    assert server.start()          # already running
    assert server.running
    server.stop()
    server.stop()
    assert not server.running


def test_a_taken_port_is_reported_not_raised(server):
    clash = DashboardServer(port=server.port, bind_host="127.0.0.1")
    assert clash.start() is False
    assert not clash.running
