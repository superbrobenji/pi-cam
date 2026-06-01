import pytest
import main as _main_module
from fastapi.testclient import TestClient
from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def _finite_stream(request, monkeypatch):
    """Patch get_frame to return None after a few calls so the MJPEG
    generator terminates cleanly inside TestClient's sync transport."""
    if request.node.name != "test_stream_content_type":
        return
    call_count = [0]
    real_get_frame = _main_module.state.get_frame

    def _limited():
        call_count[0] += 1
        if call_count[0] > 4:
            return None
        return real_get_frame()

    monkeypatch.setattr(_main_module.state, "get_frame", _limited)


def test_health_returns_200(client):
    response = client.get("/health")
    assert response.status_code == 200


def test_health_returns_expected_keys(client):
    data = client.get("/health").json()
    expected = {"count", "camera_ok", "model_ok", "ws_clients", "cpu_percent", "ram_used", "ram_total"}
    assert expected.issubset(data.keys())


def test_health_value_types(client):
    data = client.get("/health").json()
    assert isinstance(data["count"], int)
    assert isinstance(data["camera_ok"], bool)
    assert isinstance(data["model_ok"], bool)
    assert isinstance(data["ws_clients"], int)
    assert isinstance(data["cpu_percent"], float)
    assert isinstance(data["ram_used"], int)
    assert isinstance(data["ram_total"], int)


def test_websocket_emits_count(client):
    with client.websocket_connect("/ws") as ws:
        data = ws.receive_json()
        assert "count" in data
        assert isinstance(data["count"], int)


def test_websocket_increments_ws_clients(client):
    before = client.get("/health").json()["ws_clients"]
    with client.websocket_connect("/ws"):
        during = client.get("/health").json()["ws_clients"]
    assert during >= before + 1


def test_stream_content_type(client):
    with client.stream("GET", "/stream") as response:
        assert response.status_code == 200
        assert "multipart/x-mixed-replace" in response.headers["content-type"]
