import pytest
import main as _main_module
from fastapi.testclient import TestClient
from main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def _finite_stream(monkeypatch):
    """Replace _mjpeg_generator with a finite version so TestClient's
    sync transport doesn't block on the infinite production generator."""
    _FAKE_JPEG = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00"

    async def _finite():
        boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
        for _ in range(3):
            yield boundary + _FAKE_JPEG + b"\r\n"

    monkeypatch.setattr(_main_module, "_mjpeg_generator", _finite)


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


def test_stream_content_type(client, _finite_stream):
    with client.stream("GET", "/stream") as response:
        assert response.status_code == 200
        assert "multipart/x-mixed-replace" in response.headers["content-type"]
