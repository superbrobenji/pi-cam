import pytest
import monitor as _monitor_module
from fastapi.testclient import TestClient
from monitor import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def reset_monitor_state():
    _monitor_module._state.app_online = False
    _monitor_module._state.last_health = {}
    _monitor_module._state.app_offline_since = None
    _monitor_module._state.last_poll_at = None
    yield


def test_status_has_required_keys(client):
    data = client.get("/api/status").json()
    assert "app_online" in data
    assert "app_offline_since" in data
    assert "last_poll_at" in data


def test_status_offline_by_default(client):
    data = client.get("/api/status").json()
    assert data["app_online"] is False


def test_status_reflects_cached_health(client):
    _monitor_module._state.app_online = True
    _monitor_module._state.last_health = {"count": 5, "camera_ok": True}
    data = client.get("/api/status").json()
    assert data["app_online"] is True
    assert data["count"] == 5
    assert data["camera_ok"] is True


def test_logs_returns_empty_list_when_offline(client):
    _monitor_module._state.app_online = False
    data = client.get("/api/logs/detector").json()
    assert data == []


def test_restart_component_returns_503_when_offline(client):
    _monitor_module._state.app_online = False
    resp = client.post("/api/restart/detector")
    assert resp.status_code == 503


def test_restart_service_calls_systemctl(client, monkeypatch):
    monkeypatch.setattr(
        _monitor_module.subprocess, "run",
        lambda *a, **kw: type("R", (), {"returncode": 0, "stderr": ""})(),
    )
    resp = client.post("/api/restart/service")
    assert resp.status_code == 200
    assert resp.json()["status"] == "restarting"


def test_restart_service_returns_500_on_failure(client, monkeypatch):
    monkeypatch.setattr(
        _monitor_module.subprocess, "run",
        lambda *a, **kw: type("R", (), {"returncode": 1, "stderr": "not allowed"})(),
    )
    resp = client.post("/api/restart/service")
    assert resp.status_code == 500


def test_reset_tracking_returns_503_when_offline(client):
    _monitor_module._state.app_online = False
    resp = client.post("/api/reset-tracking")
    assert resp.status_code == 503
