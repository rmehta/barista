"""DockerManagerClient HTTP layer."""

import frappe  # injected by conftest
import pytest

from barista.dm_client import DockerManagerClient
from barista.exceptions import DockerManagerError


def _client(monkeypatch):
    monkeypatch.setitem(frappe.conf, "barista_docker_manager_url", "http://dm:8080")
    monkeypatch.setitem(frappe.conf, "barista_docker_manager_token", "secret")
    return DockerManagerClient()


def test_init_requires_url_and_token():
    frappe.conf.clear()
    with pytest.raises(DockerManagerError):
        DockerManagerClient()


def test_health_sends_token(monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200
        content = b'{"ok": true}'
        text = '{"ok": true}'
        def json(self): return {"ok": True}

    def fake_request(method, url, headers=None, timeout=None, **kw):
        captured["method"] = method
        captured["url"] = url
        captured["headers"] = headers
        return FakeResp()

    import requests
    monkeypatch.setattr(requests, "request", fake_request)

    c = _client(monkeypatch)
    assert c.health() == {"ok": True}
    assert captured["url"] == "http://dm:8080/v1/health"
    assert captured["headers"]["X-Auth-Token"] == "secret"


def test_4xx_raises(monkeypatch):
    class FakeResp:
        status_code = 400
        content = b"bad"
        text = "bad"
        def json(self): return {}

    import requests
    monkeypatch.setattr(requests, "request",
                         lambda *a, **k: FakeResp())

    c = _client(monkeypatch)
    with pytest.raises(DockerManagerError) as exc:
        c.start_bench("missing")
    assert "400" in str(exc.value)


def test_network_error_raises(monkeypatch):
    import requests

    def boom(*a, **k):
        raise requests.ConnectionError("nope")

    monkeypatch.setattr(requests, "request", boom)

    c = _client(monkeypatch)
    with pytest.raises(DockerManagerError) as exc:
        c.health()
    assert "unreachable" in str(exc.value)
